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
        # versions are renamed with this prefix before removal, so an interrupted removal never looks like a version
        self._removed_version_prefix: str = 'deleting-'
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
    
    async def get_completed_version(self) -> BackupVersionModel | None:
        await self._ensure_versions_cache()
        
        # the latest symlink only moves after a successful run, so it never points to a running or failed version
        target = await FsAdapter.readlink(self._destination.join('latest'))
        
        return next((version for version in self._versions if version.version == target), None)
    
    async def get_latest_version(self) -> BackupVersionModel | None:
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
        
        # rename first so an interrupted removal never leaves a partial version behind
        await FsAdapter.remove_atomically(version.path, self.get_removed_version_path(version))
        
        self._logger.info(f'Removed version path "{version.path}"')
        
    def get_removed_version_path(self, version: BackupVersionModel) -> PathModel:
        return self._destination.join(f'{self._removed_version_prefix}{version.version}')

    async def purge_removed_versions(self) -> None:
        for entry in await FsAdapter.ls(self._destination):
            if not entry.startswith(self._removed_version_prefix):
                continue

            self._logger.warning(f'Purging interrupted version removal "{entry}"')
            await FsAdapter.rm(self._destination.join(entry))

    @property
    def lock_path(self) -> PathModel:
        return self._destination.join('backup.lock')

    async def acquire_lock(self, holder: str) -> bool:
        # exclusive creation makes checking and creating the lock a single atomic operation
        return await FsAdapter.create_exclusive(self.lock_path, holder)

    async def get_lock_holder(self) -> str | None:
        return await FsAdapter.read_text(self.lock_path)
    
    async def remove_lock_file(self, holder: str) -> None:
        # only the given holder's lock is removed, never one taken over by another process meanwhile
        await FsAdapter.remove_if_content(self.lock_path, holder)
        
    async def update_latest_symlink(self) -> None:
        latest_version = await self.get_latest_version()
        latest_link = self._destination.join('latest')

        if latest_version:
            self._logger.info(f'Updating "latest" symlink to "{latest_version.version}"')
            await FsAdapter.symlink(latest_link, latest_version.version)
        else:
            if await FsAdapter.exists(latest_link):
                await FsAdapter.rm(latest_link)

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