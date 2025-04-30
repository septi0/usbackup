import os
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler, BackupHandlerError

class ZfsDatasetsHandler(BackupHandler):
    handler: str = 'zfs-datasets'
    lexicon: dict = {
        'limit': {'type': list},
        'exclude': {'type': list},
    }
    
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        
        self._limit: list[str] = self._config.get("limit")
        self._exclude: list[str] = self._config.get("exclude")

    async def backup(self, dest: str, dest_link: str = None) -> None:
        self._logger.info(f'Fetching datasets from "{self._src_host.host}"')
        
        exec_ret = await cmd_exec.exec_cmd(['zfs', 'list', '-H', '-o', 'name'], host=self._src_host)
        
        datasets = [line.strip() for line in exec_ret.splitlines() if line.strip()]
        
        if not datasets:
            self._logger.info(f'No datasets found on "{self._src_host.host}"')
            return
        
        # Filter datasets based on limit/exclude lists
        if self._limit:
            datasets = [dataset for dataset in datasets if str(dataset) in self._limit]
            
        if self._exclude:
            datasets = [dataset for dataset in datasets if str(dataset) not in self._exclude]
            
        if not datasets:
            self._logger.info(f'No datasets left to backup after limit/exclude filters')
            return
        
        self._logger.info(f'Backing up datasets "{datasets}"')
        
        for dataset in datasets:
            zfs_snapshot_name = f'{dataset}@backup-{self._id}'
            # zfs dataset without /
            file_name = dataset.replace('/', '_') + '.zfs'
            
            self._logger.info(f'Creating snapshot "{zfs_snapshot_name}" on "{self._src_host.host}"')
            
            await cmd_exec.exec_cmd(['zfs', 'snapshot', zfs_snapshot_name], host=self._src_host)
            self._cleanup.add_job(f'destroy_snapshot_{self._id}', cmd_exec.exec_cmd, ['zfs', 'destroy', zfs_snapshot_name], host=self._src_host)
            
            with open(os.path.join(dest, file_name), 'wb') as f:
                self._logger.info(f'Streaming snapshot "{zfs_snapshot_name}" from "{self._src_host.host}" to "{dest}"')
                
                await cmd_exec.exec_cmd(['zfs', 'send', zfs_snapshot_name], stdout=f, host=self._src_host)
                
            self._logger.info(f'Deleting snapshot "{zfs_snapshot_name}" on "{self._src_host.host}"')
            
            await self._cleanup.run_job(f'destroy_snapshot_{self._id}')