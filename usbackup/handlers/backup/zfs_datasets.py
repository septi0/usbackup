from usbackup.libraries.cmd_exec import CmdExec
from usbackup.libraries.fs_adapter import FsAdapter
from usbackup.models.path import PathModel
from usbackup.handlers.backup import HandlerBaseModel, BackupHandler, BackupHandlerError

class ZfsDatasetsHandlerModel(HandlerBaseModel):
    handler: str = 'zfs_datasets'
    limit: list[str] = []
    exclude: list[str] = []

class ZfsDatasetsHandler(BackupHandler):
    handler: str = 'zfs_datasets'

    def __init__(self, model: ZfsDatasetsHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)

        self._limit: list[str] = model.limit
        self._exclude: list[str] = model.exclude

    async def backup(self, dest: PathModel, dest_link: PathModel | None = None) -> None:
        self._logger.info(f'Fetching datasets from "{self._host}"')

        exec_ret = await CmdExec.exec(["zfs", "list", "-H", "-o", "name"], host=self._host)

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

            await CmdExec.exec(['zfs', 'snapshot', zfs_snapshot_name], host=self._host)
            self._cleanup.push(f'destroy_snapshot_{self._id}', CmdExec.exec, ['zfs', 'destroy', zfs_snapshot_name], host=self._host)

            with FsAdapter.open(dest.join(file_name), 'wb') as f:
                self._logger.info(f'Streaming snapshot "{zfs_snapshot_name}" from "{self._host}" to "{dest.path}"')

                await CmdExec.exec(['zfs', 'send', zfs_snapshot_name], host=self._host, stdout=f)

            self._logger.info(f'Deleting snapshot "{zfs_snapshot_name}" on "{self._host}"')

            await self._cleanup.consume(f'destroy_snapshot_{self._id}')
