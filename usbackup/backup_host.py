import os
import logging
import datetime
import io
import uuid
import usbackup.cmd_exec as cmd_exec
from usbackup.aio_files import afwrite
from usbackup.remote import Remote
from usbackup.cleanup_queue import CleanupQueue
from usbackup.exceptions import UsbackupRuntimeError
from usbackup.backup_result import UsbackupResult
from usbackup.backup_handlers.base import BackupHandler, BackupHandlerError

__all__ = ['UsBackupHost']

class UsBackupHost:
    def __init__(self, name: str, remote: Remote, handlers: list[BackupHandler], *, cleanup: CleanupQueue, logger: logging.Logger) -> None:
        self._name: str = name
        self._remote: Remote = remote
        self._handlers: list[BackupHandler] = handlers
        
        self._cleanup: CleanupQueue = cleanup
        self._logger: logging.Logger = logger
        
        self._log_stream: io.StringIO = io.StringIO()
        self._id: str = str(uuid.uuid4())
        self._version_format: str = '%Y_%m_%d-%H_%M_%S'
        
        self._bind_stream_to_logger()
        
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def remote(self) -> Remote:
        return self._remote
    
    async def backup(self, host_dest: str, retention_policy: dict) -> None:
        run_time = datetime.datetime.now()
        
        if await self._lock_file_exists(host_dest):
            raise UsbackupRuntimeError(f'Backup already running')
        
        # reset log stream
        self._log_stream.seek(0)
        self._log_stream.truncate(0)
        
        # test connection to host
        if not await cmd_exec.is_host_reachable(self._remote):
            raise UsbackupRuntimeError(f'Host {self._name} is not reachable')

        self._logger.info(f'Backup started at {run_time}')
        
        # create backup directory
        if not os.path.isdir(host_dest):
            self._logger.info(f'Creating host directory {host_dest}')
            await cmd_exec.mkdir(host_dest)
    
        dest = os.path.join(host_dest, datetime.datetime.now().strftime(self._version_format))
        dest_link = self._get_dest_link(host_dest)

        # create backup directory
        if not os.path.isdir(dest):
            self._logger.info(f'Creating version directory {dest}')
            await cmd_exec.mkdir(dest)

        await self._create_lock_file(host_dest)
        self._cleanup.add_job(f'remove_lock_{self._id}', self._remove_lock_file, host_dest)

        error = None

        for handler in self._handlers:
            handler_dest = os.path.join(dest, handler.name)
            handler_dest_link = None
            
            if dest_link:
                self._logger.info(f'Using "{dest_link}" as dest link for "{handler.name}" handler')
                handler_dest_link = os.path.join(dest_link, handler.name)
                
            try:
                if not os.path.isdir(handler_dest):
                    self._logger.info(f'Creating handler directory "{handler_dest}"')
                    await cmd_exec.mkdir(handler_dest)
                
                self._logger.info(f'Performing backup via "{handler.name}" handler')
                await handler.backup(handler_dest, handler_dest_link)
            except (BackupHandlerError) as e:
                self._logger.error(f'{handler.name} backup handler error: {e}', exc_info=True)
                error = e
            except (Exception) as e:
                self._logger.exception(f'{handler.name} backup handler exception: {e}', exc_info=True)
                error = e
                
        await self._apply_retention_policy(host_dest, retention_policy)

        await self._cleanup.run_job(f'remove_lock_{self._id}')

        finish_time = datetime.datetime.now()

        elapsed_time = finish_time - run_time
        elapsed_time_s = elapsed_time.total_seconds()

        self._logger.info(f'Backup finished at {finish_time}. Elapsed time: {elapsed_time_s:.2f} seconds')
        
        return UsbackupResult(self._name, message=self._log_stream.getvalue(), error=error, elapsed_time=elapsed_time, dest=host_dest)
    
    def _bind_stream_to_logger(self) -> None:
        stream_handler = logging.StreamHandler(self._log_stream)
        stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        
        self._logger.addHandler(stream_handler)
        
    def _get_versions(self, dest: str) -> list[str]:
        # get all backup directories
        versions = [d for d in os.listdir(dest) if os.path.isdir(os.path.join(dest, d))]
        # sort the directories by filename
        versions.sort()
        
        return versions

    def _get_dest_link(self, dest: str) -> str:
        versions = self._get_versions(dest)
        
        if not versions:
            self._logger.warning(f'No backup versions found when trying to find dest link')
            return None
        
        # get the latest version path
        return os.path.join(dest, versions[-1])
    
    # this function will delete backup versions according to the retention policy: e.g. {'last': 3, 'daily': 7, 'weekly': 4, 'monthly': 12, 'yearly': 1}
    async def _apply_retention_policy(self, dest: str, retention_policy: dict) -> int:
        if not retention_policy:
            return -1
        
        self._logger.info(f'Applying retention policy: {retention_policy}')
        
        versions = self._get_versions(dest)
        
        if not versions:
            self._logger.info(f'No backup directories found in {dest}')
            return 0
        
        protected = self._get_protected_versions(versions, retention_policy)
        versions_cnt = len(protected)
        
        if not versions_cnt:
            raise UsbackupRuntimeError(f'No backup versions found in {dest}')
        
        prune = list(set(versions) - set(protected))
        
        for version in prune:
            version_path = os.path.join(dest, version)
            if os.path.isdir(version_path):
                self._logger.info(f'Removing {version_path} based on retention policy')
                await cmd_exec.remove(version_path)
            else:
                self._logger.warning(f'Backup version "{version_path}" does not exist. Can\'t remove it')
            
        return versions_cnt
        
    def _get_protected_versions(self, versions: list, retention_policy: dict) -> list:
        categories = {
            'last': {'prev': None, 'filter': None, 'versions': []},
            'hourly': {'prev': None, 'filter': '%Y-%m-%d %H', 'versions': []},
            'daily': {'prev': None, 'filter': '%Y-%m-%d', 'versions': []},
            'weekly': {'prev': None, 'filter': '%Y-%W', 'versions': []},
            'monthly': {'prev': None, 'filter': '%Y-%m', 'versions': []},
            'yearly': {'prev': None, 'filter': '%Y', 'versions': []},
        }
        
        date_now = datetime.datetime.now()
        
        for category, attr in categories.items():
            if not retention_policy.get(category):
                continue
    
            for version in versions:
                version_date = datetime.datetime.strptime(version, self._version_format)
                
                if attr['filter'] and version_date.strftime(attr['filter']) == date_now.strftime(attr['filter']):
                    break
                
                if not attr['prev']:
                    categories[category]['versions'].append(version)
                else:
                    if attr['filter'] and version_date.strftime(attr['filter']) == attr['prev'].strftime(attr['filter']):
                        categories[category]['versions'].pop()
                            
                    categories[category]['versions'].append(version)
                        
                if len(categories[category]['versions']) > retention_policy[category]:
                    categories[category]['versions'].pop(0)
                
                categories[category]['prev'] = version_date
                
        protected = []
        
        for category, attr in categories.items():
            self._logger.debug(f'{category} protected versions: {attr["versions"]}')
            protected += attr['versions']
            
        # always protect latest version
        protected += versions[-1:]
        self._logger.debug(f'Last version protected: {protected[-1]}')
            
        protected = list(set(protected))
        protected.sort()
                
        return protected

    async def _lock_file_exists(self, dest: str) -> bool:
        lock_file = os.path.join(dest, 'backup.lock')

        return os.path.isfile(lock_file)

    async def _create_lock_file(self, dest: str) -> None:
        lock_file = os.path.join(dest, 'backup.lock')

        await afwrite(lock_file, '')

    async def _remove_lock_file(self, dest: str) -> None:
        lock_file = os.path.join(dest, 'backup.lock')

        await cmd_exec.remove(lock_file)
        
    def __str__(self) -> str:
        return self._name