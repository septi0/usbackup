import logging
import os
import datetime
import usbackup.libraries.cmd_exec as cmd_exec
from usbackup.libraries.aio_files import afwrite
from usbackup.models.source import SourceModel
from usbackup.models.storage import StorageModel
from usbackup.models.host import HostModel
from usbackup.models.handler_base import HandlerBaseModel
from usbackup.models.version import BackupVersionModel

__all__ = ['ContextService']

class ContextService:
    def __init__(self, source: SourceModel, storage: StorageModel, *, logger: logging.Logger):
        self._logger: logging.Logger = logger
        
        self._name: str = source.name
        self._host: HostModel = source.host
        self._handlers: list[HandlerBaseModel] = source.handlers
        self._destination: str = os.path.join(storage.path, source.name)
        self._version_format: str = '%Y_%m_%d-%H_%M_%S'
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def host(self) -> HostModel:
        return self._host
    
    @property
    def handlers(self) -> list[HandlerBaseModel]:
        return self._handlers
    
    @property
    def destination(self) -> str:
        return self._destination
        
    def get_versions(self) -> list[BackupVersionModel]:
        versions = []
        
        # get all backup directories
        for version in os.listdir(self._destination):
            version_path = os.path.join(self._destination, version)
            
            if not os.path.isdir(version_path):
                continue
            
            try:
                version_date = datetime.datetime.strptime(version, self._version_format)
            except ValueError:
                # skip directories that don't match the version format
                continue
            
            versions.append(BackupVersionModel(version, version_path, version_date))
            
        if not versions:
            return []
        
        # sort the directories by date asc
        versions.sort(key=lambda x: x.date)
        
        return versions
    
    def get_latest_version(self) -> BackupVersionModel:
        versions = self.get_versions()
        
        if not versions:
            return None
        
        # get the latest version
        latest_version = versions[-1]
        
        return latest_version
    
    async def generate_version(self) -> BackupVersionModel:
        version_date = datetime.datetime.now()
        version = version_date.strftime(self._version_format)
        version_path = os.path.join(self._destination, version)
        
        # create backup directory
        if not os.path.isdir(version_path):
            self._logger.info(f'Creating version directory {version_path}')
            await cmd_exec.mkdir(version_path)
            
        return BackupVersionModel(version, version_path, version_date)
    
    async def remove_version(self, version: BackupVersionModel) -> None:
        if not os.path.exists(version.path):
            self._logger.warning(f'Version "{version}" does not exist')
            return
        
        # remove the version directory
        await cmd_exec.remove(version.path)
        
        self._logger.info(f'Removed version path "{version.path}"')
        
    async def lock_file_exists(self) -> bool:
        lock_file = os.path.join(self._destination, 'backup.lock')

        return os.path.isfile(lock_file)

    async def create_lock_file(self) -> None:
        lock_file = os.path.join(self._destination, 'backup.lock')

        await afwrite(lock_file, '')

    async def remove_lock_file(self) -> None:
        lock_file = os.path.join(self._destination, 'backup.lock')

        await cmd_exec.remove(lock_file)