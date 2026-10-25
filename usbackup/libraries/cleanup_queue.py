import os
import re
import uuid
import fcntl
import socket
import asyncio
import logging
from typing import Any, Callable
from usbackup.libraries.cmd_exec import CmdExec
from usbackup.libraries.datastore import Datastore
from usbackup.libraries.fs_adapter import FsAdapter
from usbackup.models.host import HostModel
from usbackup.models.path import PathModel

__all__ = ['CleanupQueue']

class CleanupQueue:
    _key_prefix: str = 'cleanup_queue:'
    # entries of dead processes that keep failing are retried on later starts up to this many times
    _max_attempts: int = 5
    
    def __init__(self, *, datastore: Datastore, lock_dir: str):
        self._queue: list = []

        self._datastore: Datastore = datastore
        self._lock_dir: str = lock_dir
        
        # entries belong to this process, which holds the owner lock for as long as it is alive
        self._owner: str = uuid.uuid4().hex
        self._owner_lock: int | None = None
        
        self._retry_lock: asyncio.Lock = asyncio.Lock()

    def has_items(self) -> bool:
        return bool(self._queue)

    def push(self, id: str, action: str, **params: Any) -> None:
        """
        Queue a cleanup action. Params must be plain data, so entries stay readable across versions.
        """
        if self._get_index(id) is not None:
            raise ValueError(f"Job with id {id} already exists")
        
        if not hasattr(self, f'_action_{action}'):
            raise ValueError(f'Unknown cleanup action "{action}"')
        
        # lock before persisting so the entries are never seen without a live owner
        self.claim()
        
        self._queue.append((id, action, params, 0))
        
        self._persist()
        
    def pop(self, id: str) -> None:
        index = self._get_index(id)
        
        if index is None:
            raise ValueError(f"Job with id {id} not found")
        
        self._queue.pop(index)
        
        self._persist()
        
    def clear(self) -> None:
        self._queue.clear()
        
        self._persist()
    
    async def consume(self, id: str) -> None:
        index = self._get_index(id)
        
        if index is None:
            raise ValueError(f"Job with id {id} not found")
        
        try:
            await self._execute(self._queue[index])
        except Exception:
            # the entry stays queued as abandoned, so it is retried later, on exit or after a crash
            self.abandon(id)
            raise
        
        self._queue.pop(self._get_index(id))
        
        self._persist()
    
    def abandon(self, id: str) -> None:
        """
        Mark an entry its owner gave up on after a failure, so it is retried later and no longer considered in use.
        """
        index = self._get_index(id)
        
        if index is None:
            raise ValueError(f"Job with id {id} not found")
        
        (id, action, params, attempts) = self._queue[index]
        self._queue[index] = (id, action, params, attempts + 1)
        
        self._persist()
    
    async def retry_abandoned(self) -> None:
        """
        Retry the abandoned entries of this process. Entries failing too many times are dropped.
        """
        async with self._retry_lock:
            for entry in [entry for entry in self._queue if entry[3] > 0]:
                try:
                    await self._execute(entry)
                    retried = None
                except Exception as e:
                    logging.warning(f'Cleanup action "{entry[0]}" failed again: {e}')
                    retried = self._count_attempt(entry)
                
                index = self._get_index(entry[0])
                
                if index is None:
                    continue
                
                if retried:
                    self._queue[index] = retried
                else:
                    self._queue.pop(index)
                
                self._persist()

    async def consume_all(self) -> None:
        error = None
        
        for entry in reversed(list(self._queue)):
            try:
                await self._execute(entry)
            except Exception as e:
                error = error or e
                continue
            
            self._queue.remove(entry)
            
            self._persist()
        
        if error:
            raise error
    
    def claim(self) -> str:
        """
        Take the owner lock of this process. Returns the holder id used to mark resources held by this process.
        """
        if self._owner_lock is None:
            self._owner_lock = self._lock_owner(self._owner)
        
        return f'{socket.gethostname()}:{self._owner}'
    
    def is_holder_dead(self, holder: str) -> bool:
        """
        Check if holder (<host>:<owner>/<run>) is known to no longer use what it holds. Holders of other hosts are never known to be dead.
        """
        process, _, run = holder.partition('/')
        host, _, owner = process.rpartition(':')
        
        if host != socket.gethostname() or not re.fullmatch(r'[0-9a-f]{32}', owner):
            return False
        
        # a lock of this process is in use only while its entry is pending, an abandoned or missing entry means its run gave up on it
        if owner == self._owner:
            return not any(action == 'remove_lock' and params.get('holder') == holder and attempts == 0 for (_, action, params, attempts) in self._queue)
        
        try:
            lock = os.open(self._get_lock_path(owner), os.O_RDWR)
        except FileNotFoundError:
            return True
        
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        finally:
            os.close(lock)
        
        return True
    
    def close(self) -> None:
        """
        Release the queue ownership. Entries still queued are left for crash recovery.
        """
        if self._owner_lock is None:
            return

        if self._queue:
            os.close(self._owner_lock)
        else:
            self._delete_queue(self._owner)
            self._unlock_owner(self._owner, self._owner_lock, remove=True)

        self._owner_lock = None
    
    def has_orphans(self) -> bool:
        """
        Check for entries left behind by processes that are no longer alive.
        """
        for owner in self._other_owners():
            lock = self._lock_owner(owner)
            
            if lock is None:
                continue
            
            try:
                if self._datastore.get(self._get_key(owner), []):
                    return True
            finally:
                self._unlock_owner(owner, lock, remove=False)
        
        return False
    
    async def consume_orphans(self) -> None:
        """
        Run the entries left behind by processes that are no longer alive. Failing entries are kept for a later retry.
        """
        error = None
        
        for owner in self._other_owners():
            lock = self._lock_owner(owner)
            
            # owner still alive or being recovered by another process
            if lock is None:
                continue
            
            key = self._get_key(owner)
            pending = self._datastore.get(key, [])
            retry = []
            
            try:
                while pending:
                    entry = pending.pop()
                    
                    try:
                        await self._execute(entry)
                    except Exception as e:
                        error = error or e
                        entry = self._count_attempt(entry)
                        
                        if entry:
                            retry.insert(0, entry)
                    
                    self._datastore.set(key, pending + retry)
            except BaseException:
                self._unlock_owner(owner, lock, remove=False)
                raise
            
            if retry:
                self._unlock_owner(owner, lock, remove=False)
            else:
                self._delete_queue(owner)
                self._unlock_owner(owner, lock, remove=True)
        
        if error:
            raise error

    def _get_index(self, id: str) -> int | None:
        for index, job in enumerate(self._queue):
            if job[0] == id:
                return index
        
        return None
    
    async def _execute(self, entry: tuple) -> None:
        (id, action, params, attempts) = entry

        handler: Callable | None = getattr(self, f'_action_{action}', None)
        
        if handler is None:
            raise ValueError(f'Unknown cleanup action "{action}"')
        
        await handler(**params)
    
    def _count_attempt(self, entry: tuple) -> tuple | None:
        (id, action, params, attempts) = entry
        
        if attempts + 1 >= self._max_attempts:
            logging.error(f'Cleanup action "{id}" failed too many times and is dropped')
            return None
        
        return (id, action, params, attempts + 1)
    
    async def _action_exec(self, cmd: list, host: dict | None = None) -> None:
        await CmdExec.exec(cmd, host=HostModel(**host) if host else None)
    
    async def _action_remove_version(self, path: dict, staging: dict) -> None:
        await FsAdapter.remove_atomically(PathModel(**path), PathModel(**staging))
    
    async def _action_remove_lock(self, path: dict, holder: str) -> None:
        await FsAdapter.remove_if_content(PathModel(**path), holder)
    
    async def _action_datastore_set(self, key: str, value: Any) -> None:
        self._datastore.set(key, value)
    
    def _persist(self) -> None:
        # without the owner lock nothing was ever pushed, so there is nothing to persist
        if self._owner_lock is None:
            return
        
        self._datastore.set(self._get_key(self._owner), self._queue)
    
    def _get_key(self, owner: str) -> str:
        return f'{self._key_prefix}{owner}'
    
    def _get_lock_path(self, owner: str) -> str:
        return os.path.join(self._lock_dir, f'{owner}.lock')
    
    def _other_owners(self) -> list[str]:
        owners = []
        
        for key in self._datastore.keys():
            if key.startswith(self._key_prefix) and key != self._get_key(self._owner):
                owners.append(key[len(self._key_prefix):])
        
        return owners
    
    def _delete_queue(self, owner: str) -> None:
        try:
            self._datastore.delete(self._get_key(owner))
        except KeyError:
            pass
    
    def _lock_owner(self, owner: str) -> int | None:
        """
        Take the owner lock without waiting. Returns the lock descriptor, or None if another process holds it.
        """
        os.makedirs(self._lock_dir, exist_ok=True)
        
        lock = os.open(self._get_lock_path(owner), os.O_RDWR | os.O_CREAT, 0o600)
        
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(lock)
            return None
        
        return lock
    
    def _unlock_owner(self, owner: str, lock: int, *, remove: bool) -> None:
        if remove:
            try:
                os.unlink(self._get_lock_path(owner))
            except FileNotFoundError:
                pass
        
        # closing the descriptor releases the lock
        os.close(lock)
