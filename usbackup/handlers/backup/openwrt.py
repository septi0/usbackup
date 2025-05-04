from usbackup.libraries.cmd_exec import CmdExec
from usbackup.libraries.fs_adapter import FsAdapter
from usbackup.models.path import PathModel
from usbackup.handlers.backup import HandlerBaseModel, BackupHandler, BackupHandlerError

class OpenwrtHandlerModel(HandlerBaseModel):
    handler: str = 'openwrt'

class OpenwrtHandler(BackupHandler):
    handler: str = 'openwrt'
    
    def __init__(self, model: OpenwrtHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)

    async def backup(self, dest: PathModel, dest_link: PathModel = None) -> None:
        self._logger.info(f'Generating backup archive "/tmp/archive.tar.gz" on "{self._host}"')
        
        await CmdExec.exec(['sysupgrade', '-b', '/tmp/archive.tar.gz'], host=self._host)
        
        archive_path = PathModel(path='/tmp/archive.tar.gz', host=self._host)
        
        self._cleanup.add_job(f'remove_backup_archive_{self._id}', FsAdapter.rm, archive_path)

        self._logger.info(f'Copying "{archive_path}" to "{dest.path}"')
        
        await FsAdapter.rsync(archive_path, dest)
        
        self._logger.info(f'Deleting backup archive on "{self._host}"')
        
        await self._cleanup.run_job(f'remove_backup_archive_{self._id}')