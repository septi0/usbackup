import usbackup.libraries.cmd_exec as cmd_exec
from usbackup.handlers.backup import HandlerBaseModel, BackupHandler, BackupHandlerError

class TruenasHandlerModel(HandlerBaseModel):
    handler: str = 'truenas'

class TruenasHandler(BackupHandler):
    handler: str = 'truenas'
    
    def __init__(self, model: TruenasHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)

    async def backup(self, dest: str, dest_link: str = None) -> None:
        self._logger.info(f'Copying config files from "{self._host}" to "{dest}"')
        
        await cmd_exec.rsync('/data/freenas-v1.db', dest, host=self._host)
        await cmd_exec.rsync('/data/pwenc_secret', dest, host=self._host)