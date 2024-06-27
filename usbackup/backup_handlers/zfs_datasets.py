import os
import shlex
import logging
import uuid
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import HandlerError

class ZfsDatasetsHandler(BackupHandler):
    handler: str = 'zfs-datasets'
    
    def __init__(self, src_host: Remote, snapshot_name: str, config: dict):
        super().__init__(src_host, snapshot_name, config)
        
        self._zfs_datasets: list[str] = []
        
        for zfs_dataset in shlex.split(config.get("backup.zfs-datasets", '')):
            self._zfs_datasets.append(zfs_dataset)
        
        self._use_handler: bool = bool(self._zfs_datasets)

    async def backup(self, dest: str, dest_link: str = None, *, logger: logging.Logger = None) -> None:
        if not self._use_handler:
            raise HandlerError(f'"zfs-datasets" handler not configured')
        
        logger = logger.getChild('zfs-datasets')

        for zfs_dataset in self._zfs_datasets:
            zfs_snapshot_name = f'{zfs_dataset}@backup-{str(uuid.uuid4())}'
            # zfs dataset without /
            file_name = zfs_dataset.replace('/', '_') + '.zfs'
            
            logger.info(f'Creating snapshot "{zfs_snapshot_name}" on "{self._src_host.host}"')
            
            await cmd_exec.exec_cmd(['zfs', 'snapshot', zfs_snapshot_name], host=self._src_host)
            
            with open(os.path.join(dest, file_name), 'wb') as f:
                logger.info(f'Copying snapshot "{zfs_snapshot_name}" from "{self._src_host.host}" to "{dest}"')
                
                await cmd_exec.exec_cmd(['zfs', 'send', zfs_snapshot_name], stdout=f, host=self._src_host)
                
            logger.info(f'Deleting snapshot "{zfs_snapshot_name}" on "{self._src_host.host}"')
            
            await cmd_exec.exec_cmd(['zfs', 'destroy', zfs_snapshot_name], host=self._src_host)