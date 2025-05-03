import usbackup.libraries.cmd_exec as cmd_exec
from usbackup.handlers.backup import UsBackupHandlerBaseModel, BackupHandler, BackupHandlerError

class OpenwrtHandlerModel(UsBackupHandlerBaseModel):
    handler: str = 'openwrt'

class OpenwrtHandler(BackupHandler):
    handler: str = 'openwrt'
    
    def __init__(self, model: OpenwrtHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)

    async def backup(self, dest: str, dest_link: str = None) -> None:
        self._logger.info(f'Generating backup archive "/tmp/backup-openwrt.tar.gz" on "{self._host}"')
        
        await cmd_exec.exec_cmd(['sysupgrade', '-b', '/tmp/backup-openwrt.tar.gz'], host=self._host)

        self._logger.info(f'Copying backup from "{self._host}" to "{dest}"')
        
        await cmd_exec.rsync(f'/tmp/backup-openwrt.tar.gz', dest, host=self._host, options=['remove-source-files'])