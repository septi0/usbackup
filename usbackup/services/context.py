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
        self._versions: list[BackupVersionModel] = []
        self._cache_generated: bool = False
    
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
        await self._ensure_versions_cache()
        
        return self._versions
    
    async def get_latest_version(self) -> BackupVersionModel:
        await self._ensure_versions_cache()
        
        if not self._versions:
            return None
        
        # get the latest version
        return self._versions[-1]
    
    async def generate_version(self) -> BackupVersionModel:
        await self._ensure_versions_cache()
        
        version_date = datetime.datetime.now()
        version = version_date.strftime(self._version_format)
        version_path = self._destination.join(version)
        
        # create backup directory
        self._logger.info(f'Creating version directory {version_path}')
        await FsAdapter.mkdir(version_path)
            
        version_model = BackupVersionModel(version, version_path, version_date)
        
        self._versions.append(version_model)
        
        return version_model
    
    async def remove_version(self, version: BackupVersionModel) -> None:
        await self._ensure_versions_cache()
        
        if not await FsAdapter.exists(version.path, 'd'):
            self._logger.warning(f'Version "{version}" does not exist')
            return
        
        self._versions.remove(version)
        
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
        
    async def ensure_destination(self) -> None:
        if not await FsAdapter.exists(self._destination, 'd'):
            self._logger.info(f'Creating context directory "{self._destination}"')
            await FsAdapter.mkdir(self._destination)
        
    async def _ensure_versions_cache(self) -> None:
        if self._cache_generated:
            return
        
        versions = []
        
        # get all backup directories
        for version in await FsAdapter.ls(self._destination):
            try:
                version_date = datetime.datetime.strptime(version, self._version_format)
            except ValueError:
                continue
            
            version_path = self._destination.join(version)
            versions.append(BackupVersionModel(version, version_path, version_date))
            
        if not versions:
            self._cache_generated = True
            self._versions = []
            return
        
        # sort the directories by date asc
        versions.sort(key=lambda x: x.date)
        
        self._cache_generated = True
        self._versions = versions