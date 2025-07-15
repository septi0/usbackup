import asyncio
from typing import Callable
from usbackup.libraries.datastore import Datastore

__all__ = ['CleanupQueue']

class CleanupQueue:
    def __init__(self, *, datastore: Datastore):
        self._queue: list = []

        self._datastore: Datastore = datastore
        
        self._init_queue()

    def has_items(self) -> bool:
        return bool(self._queue)

    def push(self, id: str, handler: Callable, *args, **kwargs) -> None:
        if self._get_index(id):
            raise ValueError(f"Job with id {id} already exists")
        
        self._queue.append((id, handler, args, kwargs))
        
        self._datastore.set('cleanup_queue', self._queue)
        
    def pop(self, id: str) -> None:
        index = self._get_index(id)
        
        if not index:
            raise ValueError(f"Job with id {id} not found")
        
        self._queue.pop(index)
        
        self._datastore.set('cleanup_queue', self._queue)
    
    async def consume(self, id: str) -> None:
        index = self._get_index(id)
        
        if index is None:
            raise ValueError(f"Job with id {id} not found")
        
        (id, handler, args, kwargs) = self._queue.pop(index)
        await self._execute(handler, *args, **kwargs)
        
        self._datastore.set('cleanup_queue', self._queue)

    async def consume_all(self) -> None:
        if not self._queue:
            return

        while self._queue:
            (id, handler, args, kwargs) = self._queue.pop()
            await self._execute(handler, *args, **kwargs)

            self._datastore.set('cleanup_queue', self._queue)

    def _get_index(self, id: str) -> int | None:
        for index, job in enumerate(self._queue):
            if job[0] == id:
                return index
        
        return None
    
    async def _execute(self, handler: Callable, *args, **kwargs) -> None:
        if asyncio.iscoroutinefunction(handler):
            await handler(*args, **kwargs)
        else:
            handler(*args, **kwargs)

    def _init_queue(self) -> None:
        self._queue = self._datastore.get('cleanup_queue', [])