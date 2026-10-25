from usbackup.libraries.cmd_exec import CmdExec
from usbackup.libraries.fs_adapter import FsAdapter
from usbackup.models.path import PathModel
from usbackup.handlers.backup import HandlerBaseModel, BackupHandler, BackupHandlerError

class ZfsDatasetsHandlerModel(HandlerBaseModel):
    handler: str = 'zfs_datasets'
    limit: list[str] = []
    exclude: list[str] = []
    compressed: bool = True

class ZfsDatasetsHandler(BackupHandler):
    handler: str = 'zfs_datasets'

    def __init__(self, model: ZfsDatasetsHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)

        self._limit: list[str] = model.limit
        self._exclude: list[str] = model.exclude
        self._compressed: bool = model.compressed

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
            self._cleanup.push(f'destroy_snapshot_{self._id}', 'exec', cmd=['zfs', 'destroy', zfs_snapshot_name], host=self._host.model_dump())

            # the snapshot is destroyed even if streaming fails, instead of lingering until the process exits
            try:
                with FsAdapter.open(dest.join(file_name), 'wb') as f:
                    self._logger.info(f'Streaming snapshot "{zfs_snapshot_name}" from "{self._host}" to "{dest.path}"')

                    # compressed blocks are sent as they are stored, so the stream is smaller and nothing is decompressed on the host
                    await CmdExec.exec(['zfs', 'send', *(['-c'] if self._compressed else []), zfs_snapshot_name], host=self._host, stdout=f)
            finally:
                self._logger.info(f'Deleting snapshot "{zfs_snapshot_name}" on "{self._host}"')

                await self._cleanup.consume(f'destroy_snapshot_{self._id}')
