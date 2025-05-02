import os
import logging
import datetime
import io
import uuid

import usbackup.libraries.cmd_exec as cmd_exec
from usbackup.libraries.aio_files import afwrite
from usbackup.models.remote import RemoteModel
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.models.host import UsBackupHostModel
from usbackup.models.handler_base import UsBackupHandlerBaseModel
from usbackup.models.result import UsBackupResultModel
from usbackup.models.retention_policy import UsBackupRetentionPolicyModel
from usbackup.models.version import UsBackupVersionModel
from usbackup.exceptions import UsbackupRuntimeError
from usbackup.handlers import handler_factory
from usbackup.handlers.backup import BackupHandler, BackupHandlerError

__all__ = ['UsBackupHost']

class UsBackupHost:
    def __init__(self, model: UsBackupHostModel, *, cleanup: CleanupQueue, logger: logging.Logger) -> None:
        self._cleanup: CleanupQueue = cleanup
        self._logger: logging.Logger = logger
        
        self._name: str = model.name
        self._host: RemoteModel = model.host
        self._dest: str = model.dest
        
        self._handlers: list[BackupHandler] = self._gen_handlers_list(model.handlers)
        
        self._log_stream: io.StringIO = io.StringIO()
        self._id: str = str(uuid.uuid4())
        self._version_format: str = '%Y_%m_%d-%H_%M_%S'
        
        self._bind_stream_to_logger()
        
    @property
    def name(self) -> str:
        return self._name
    
    async def backup(self, retention_policy: UsBackupRetentionPolicyModel) -> None:
        run_time = datetime.datetime.now()
        
        if await self._lock_file_exists():
            raise UsbackupRuntimeError(f'Backup already running')
        
        # reset log stream
        self._log_stream.seek(0)
        self._log_stream.truncate(0)
        
        # test connection to host
        if not await cmd_exec.is_host_reachable(self._host):
            raise UsbackupRuntimeError(f'Host" {self._host}" is not reachable')

        self._logger.info(f'Backup started at {run_time}')
        
        # create backup directory
        if not os.path.isdir(self._dest):
            self._logger.info(f'Creating host directory {self._dest}')
            await cmd_exec.mkdir(self._dest)
            
        await self._create_lock_file()
        self._cleanup.add_job(f'remove_lock_{self._id}', self._remove_lock_file)
    
        version_dest = os.path.join(self._dest, datetime.datetime.now().strftime(self._version_format))
        version_dest_link = self._get_dest_link()

        # create backup directory
        if not os.path.isdir(version_dest):
            self._logger.info(f'Creating version directory {version_dest}')
            await cmd_exec.mkdir(version_dest)

        error = None

        for handler in self._handlers:
            handler_dest = os.path.join(version_dest, handler.handler)
            handler_dest_link = None
            
            if version_dest_link:
                self._logger.info(f'Using "{version_dest_link}" as dest link for "{handler.handler}" handler')
                handler_dest_link = os.path.join(version_dest_link, handler.handler)
                
            try:
                if not os.path.isdir(handler_dest):
                    self._logger.info(f'Creating handler directory "{handler_dest}"')
                    await cmd_exec.mkdir(handler_dest)
                
                self._logger.info(f'Performing backup via "{handler.handler}" handler')
                await handler.backup(handler_dest, handler_dest_link)
            except (Exception) as e:
                self._logger.exception(e, exc_info=True)
                error = e
                break
                
        await self._apply_retention_policy(retention_policy)

        await self._cleanup.run_job(f'remove_lock_{self._id}')

        finish_time = datetime.datetime.now()

        elapsed_time = finish_time - run_time
        elapsed_time_s = elapsed_time.total_seconds()

        self._logger.info(f'Backup finished at {finish_time}. Elapsed time: {elapsed_time_s:.2f} seconds')
        
        return UsBackupResultModel(self._name, message=self._log_stream.getvalue(), error=error, elapsed_time=elapsed_time, dest=self._dest)
 
    def get_versions(self) -> list[UsBackupVersionModel]:
        versions = []
        
        # get all backup directories
        for d in os.listdir(self._dest):
            abs_path = os.path.join(self._dest, d)
            
            if not os.path.isdir(abs_path):
                continue
            
            try:
                directory_date = datetime.datetime.strptime(d, self._version_format)
            except ValueError:
                # skip directories that don't match the version format
                continue
            
            versions.append(UsBackupVersionModel(d, abs_path, directory_date))
            
        if not versions:
            return []
        
        # sort the directories by date asc
        versions.sort(key=lambda x: x.date)
        
        return versions
    
    def _gen_handlers_list(self, handlers_models: list[UsBackupHandlerBaseModel]) -> list[BackupHandler]:
        handlers = []
        
        for handler_model in handlers_models:
            handler_logger = self._logger.getChild(handler_model.handler)
            handler_class = handler_factory('backup', name=handler_model.handler, entity='handler')
            
            handlers.append(handler_class(self._host, handler_model, cleanup=self._cleanup, logger=handler_logger))
            
        return handlers
    
    def _bind_stream_to_logger(self) -> None:
        stream_handler = logging.StreamHandler(self._log_stream)
        stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        
        self._logger.addHandler(stream_handler)

    def _get_dest_link(self) -> str:
        versions = self.get_versions()
        
        if not versions:
            self._logger.warning(f'No backup versions found when trying to find dest link')
            return None
        
        # get the latest version path
        return os.path.join(self._dest, versions[-1].version)
    
    # this function will delete backup versions according to the retention policy: e.g. {'last': 3, 'daily': 7, 'weekly': 4, 'monthly': 12, 'yearly': 1}
    async def _apply_retention_policy(self, retention_policy: UsBackupRetentionPolicyModel) -> int:
        if not retention_policy:
            return -1
        
        self._logger.info(f'Applying retention policy: {retention_policy}')
        
        versions = self.get_versions()
        
        if not versions:
            self._logger.info(f'No backup versions found. Nothing to prune')
            return 0
        
        protected = self._get_protected_versions(versions, retention_policy)
        versions_cnt = len(protected)
        
        if not versions_cnt:
            raise UsbackupRuntimeError(f'No protected versions generated. Pruning not possible')
        
        # exclude protected versions from the list
        prune = [version.version for version in versions if version.version not in protected]
        
        for version in prune:
            version_path = os.path.join(self._dest, version)
            if os.path.isdir(version_path):
                self._logger.info(f'Removing {version_path} based on retention policy')
                await cmd_exec.remove(version_path)
            else:
                self._logger.warning(f'Backup version "{version_path}" does not exist. Can\'t remove it')
            
        return versions_cnt
        
    def _get_protected_versions(self, versions: list[UsBackupVersionModel], retention_policy: UsBackupRetentionPolicyModel) -> list:
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
            policy = getattr(retention_policy, category)
            if not policy:
                continue
    
            for version in versions:
                # stop processing if we reach the current date for given filter
                if attr['filter'] and version.date.strftime(attr['filter']) == date_now.strftime(attr['filter']):
                    break
                
                if not attr['prev']:
                    # always add first version
                    categories[category]['versions'].append(version.version)
                else:
                    if attr['filter'] and version.date.strftime(attr['filter']) == attr['prev'].strftime(attr['filter']):
                        # remove last version if it is the same as previous for given filter
                        categories[category]['versions'].pop()
                    
                    # add current version
                    categories[category]['versions'].append(version.version)
                        
                if len(categories[category]['versions']) > policy:
                    # remove oldest version if we have more than retention policy
                    categories[category]['versions'].pop(0)
                
                categories[category]['prev'] = version.date
                
        protected = []
        
        for category, attr in categories.items():
            self._logger.debug(f'{category} protected versions: {attr["versions"]}')
            protected += attr['versions']
            
        # always protect latest version
        protected.append(versions[-1].version)
        self._logger.debug(f'Last version protected: {versions[-1].version}')
        
        protected = list(set(protected))
        protected.sort()
                
        return protected

    async def _lock_file_exists(self) -> bool:
        lock_file = os.path.join(self._dest, 'backup.lock')

        return os.path.isfile(lock_file)

    async def _create_lock_file(self) -> None:
        lock_file = os.path.join(self._dest, 'backup.lock')

        await afwrite(lock_file, '')

    async def _remove_lock_file(self) -> None:
        lock_file = os.path.join(self._dest, 'backup.lock')

        await cmd_exec.remove(lock_file)
        
    def __str__(self) -> str:
        return self._name