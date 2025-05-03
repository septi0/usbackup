import os
import usbackup.libraries.cmd_exec as cmd_exec
from usbackup.handlers.backup import UsBackupHandlerBaseModel, BackupHandler, BackupHandlerError

class ZfsDatasetsHandlerModel(UsBackupHandlerBaseModel):
    handler: str = 'zfs_datasets'
    limit: list[str] = []
    exclude: list[str] = []

class ZfsDatasetsHandler(BackupHandler):
    handler: str = 'zfs_datasets'
    
    def __init__(self, model: ZfsDatasetsHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)
        
        self._limit: list[str] = model.limit
        self._exclude: list[str] = model.exclude

    async def backup(self, dest: str, dest_link: str = None) -> None:
        self._logger.info(f'Fetching datasets from "{self._host}"')
        
        exec_ret = await cmd_exec.exec_cmd(['zfs', 'list', '-H', '-o', 'name'], host=self._host)
        
        datasets = [line.strip() for line in exec_ret.splitlines() if line.strip()]
        
        if not datasets:
            self._logger.info(f'No datasets found on "{self._host}"')
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
            
            self._logger.info(f'Creating snapshot "{zfs_snapshot_name}" on "{self._host}"')
            
            await cmd_exec.exec_cmd(['zfs', 'snapshot', zfs_snapshot_name], host=self._host)
            self._cleanup.add_job(f'destroy_snapshot_{self._id}', cmd_exec.exec_cmd, ['zfs', 'destroy', zfs_snapshot_name], host=self._host)
            
            with open(os.path.join(dest, file_name), 'wb') as f:
                self._logger.info(f'Streaming snapshot "{zfs_snapshot_name}" from "{self._host}" to "{dest}"')
                
                await cmd_exec.exec_cmd(['zfs', 'send', zfs_snapshot_name], stdout=f, host=self._host)
                
            self._logger.info(f'Deleting snapshot "{zfs_snapshot_name}" on "{self._host}"')
            
            await self._cleanup.run_job(f'destroy_snapshot_{self._id}')