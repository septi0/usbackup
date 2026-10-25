from usbackup.libraries.remote_cmd import RemoteCmd
from usbackup.libraries.remote_sync import RemoteSync
from usbackup.models.path import PathModel
from usbackup.handlers.backup import HandlerBaseModel, BackupHandler, BackupHandlerError

class OpenwrtHandlerModel(HandlerBaseModel):
    handler: str = 'openwrt'

class OpenwrtHandler(BackupHandler):
    handler: str = 'openwrt'
    
    def __init__(self, model: OpenwrtHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)

    async def backup(self, dest: PathModel, dest_link: PathModel | None = None) -> None:
        self._logger.info(f'Generating backup archive "/tmp/archive.tar.gz" on "{self._host}"')

        await RemoteCmd.exec(['sysupgrade', '-b', '/tmp/archive.tar.gz'], self._host)

        archive_path = PathModel(path='/tmp/archive.tar.gz', host=self._host)

        self._cleanup.push(f'remove_backup_archive_{self._id}', 'exec', cmd=['rm', archive_path.path], host=self._host.model_dump())

        # the archive is removed even if copying fails, instead of lingering until the process exits
        try:
            self._logger.info(f'Copying "{archive_path}" to "{dest.path}"')

            await RemoteSync.scp(archive_path, dest)
        finally:
            self._logger.info(f'Deleting backup archive on "{self._host}"')

            await self._cleanup.consume(f'remove_backup_archive_{self._id}')