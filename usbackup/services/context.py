import logging
import datetime
from usbackup.libraries.fs_adapter import FsAdapter
from usbackup.models.source import SourceModel
from usbackup.models.storage import StorageModel
from usbackup.models.host import HostModel
from usbackup.models.handler_base import HandlerBaseModel
from usbackup.models.version import BackupVersionModel
from usbackup.models.path import PathModel

__all__ = ['ContextService']

class ContextService:
    def __init__(self, source: SourceModel, storage: StorageModel, *, logger: logging.Logger):
        self._logger: logging.Logger = logger
        
        self._name: str = source.name
        self._host: HostModel = source.host
        self._handlers: list[HandlerBaseModel] = source.handlers
        self._destination: PathModel = storage.path.join(source.name)
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
    def destination(self) -> PathModel:
        return self._destination
        
    async def get_versions(self) -> list[BackupVersionModel]:
        versions = []
        
        # get all backup directories
        for version in await FsAdapter.ls(self._destination):
            try:
                version_date = datetime.datetime.strptime(version, self._version_format)
            except ValueError:
                # skip directories that don't match the version format
                continue
            
            version_path = self._destination.join(version)
            versions.append(BackupVersionModel(version, version_path, version_date))
            
        if not versions:
            return []
        
        # sort the directories by date asc
        versions.sort(key=lambda x: x.date)
        
        return versions
    
    async def get_latest_version(self) -> BackupVersionModel:
        versions = await self.get_versions()
        
        if not versions:
            return None
        
        # get the latest version
        latest_version = versions[-1]
        
        return latest_version
    
    async def generate_version(self) -> BackupVersionModel:
        version_date = datetime.datetime.now()
        version = version_date.strftime(self._version_format)
        version_path = self._destination.join(version)
        
        # create backup directory
        if not await FsAdapter.exists(version_path, 'd'):
            self._logger.info(f'Creating version directory {version_path}')
            await FsAdapter.mkdir(version_path)
            
        return BackupVersionModel(version, version_path, version_date)
    
    async def remove_version(self, version: BackupVersionModel) -> None:
        if not await FsAdapter.exists(version.path, 'd'):
            self._logger.warning(f'Version "{version}" does not exist')
            return
        
        # remove the version directory
        await FsAdapter.rm(version.path)
        
        self._logger.info(f'Removed version path "{version.path}"')
        
    async def lock_file_exists(self) -> bool:
        lock_file = self._destination.join('backup.lock')

        return await FsAdapter.exists(lock_file, 'f')

    async def create_lock_file(self) -> None:
        lock_file = self._destination.join('backup.lock')

        await FsAdapter.touch(lock_file)

    async def remove_lock_file(self) -> None:
        lock_file = self._destination.join('backup.lock')

        await FsAdapter.rm(lock_file)