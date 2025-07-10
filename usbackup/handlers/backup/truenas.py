from usbackup.libraries.remote_sync import RemoteSync
from usbackup.models.path import PathModel
from usbackup.handlers.backup import HandlerBaseModel, BackupHandler, BackupHandlerError

class TruenasHandlerModel(HandlerBaseModel):
    handler: str = 'truenas'

class TruenasHandler(BackupHandler):
    handler: str = 'truenas'
    
    def __init__(self, model: TruenasHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)

    async def backup(self, dest: PathModel, dest_link: PathModel | None = None) -> None:
        self._logger.info(f'Copying config files from "{self._host}" to "{dest.path}"')
        
        db_path = PathModel(path='/data/freenas-v1.db', host=self._host)
        secret_path = PathModel(path='/data/pwenc_secret', host=self._host)
        
        await RemoteSync.rsync(db_path, dest)
        await RemoteSync.rsync(secret_path, dest)