import logging
import os
import datetime
import usbackup.libraries.cmd_exec as cmd_exec
from usbackup.libraries.aio_files import afwrite
from usbackup.models.source import UsBackupSourceModel
from usbackup.models.version import UsBackupVersionModel

__all__ = ['UsBackupContext']

class UsBackupContext:
    def __init__(self, source: UsBackupSourceModel, destination: str, *, logger: logging.Logger):
        self._source: UsBackupSourceModel = source
        self._destination: str = destination
        
        self._logger: logging.Logger = logger
        
        self._name: str = source.name
        self._version_format: str = '%Y_%m_%d-%H_%M_%S'
    
    @property    
    def source(self) -> UsBackupSourceModel:
        return self._source
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def destination(self) -> str:
        return self._destination
        
    def get_versions(self) -> list[UsBackupVersionModel]:
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
            
            versions.append(UsBackupVersionModel(version, version_path, version_date))
            
        if not versions:
            return []
        
        # sort the directories by date asc
        versions.sort(key=lambda x: x.date)
        
        return versions
    
    def get_latest_version(self) -> UsBackupVersionModel:
        versions = self.get_versions()
        
        if not versions:
            return None
        
        # get the latest version
        latest_version = versions[-1]
        
        return latest_version
    
    async def generate_version(self) -> UsBackupVersionModel:
        version_date = datetime.datetime.now()
        version = version_date.strftime(self._version_format)
        version_path = os.path.join(self._destination, version)
        
        # create backup directory
        if not os.path.isdir(version_path):
            self._logger.info(f'Creating version directory {version_path}')
            await cmd_exec.mkdir(version_path)
            
        return UsBackupVersionModel(version, version_path, version_date)
    
    async def remove_version(self, version: UsBackupVersionModel) -> None:
        if not os.path.exists(version.path):
            self._logger.warning(f'Version "{version}" does not exist')
            return
        
        # remove the version directory
        await cmd_exec.remove(version.path)
        
        self._logger.info(f'Removed version "{version}"')
        
    async def lock_file_exists(self) -> bool:
        lock_file = os.path.join(self._destination, 'backup.lock')

        return os.path.isfile(lock_file)

    async def create_lock_file(self) -> None:
        lock_file = os.path.join(self._destination, 'backup.lock')

        await afwrite(lock_file, '')

    async def remove_lock_file(self) -> None:
        lock_file = os.path.join(self._destination, 'backup.lock')

        await cmd_exec.remove(lock_file)