import json
from usbackup.libraries.remote_cmd import RemoteCmd
from usbackup.libraries.remote_sync import RemoteSync
from usbackup.models.path import PathModel
from usbackup.handlers.backup import HandlerBaseModel, BackupHandler, BackupHandlerError

class HomeassistantHandlerModel(HandlerBaseModel):
    handler: str = 'homeassistant'

class HomeassistantHandler(BackupHandler):
    handler: str = 'homeassistant'

    def __init__(self, model: HomeassistantHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)

    async def backup(self, dest: PathModel, dest_link: PathModel | None = None) -> None:
        self._logger.info(f'Generating backup archive on "{self._host}"')
        
        result = await RemoteCmd.exec(['ha', 'backups', 'new', '--name', 'usbackup', '--raw-json', '--no-progress'], self._host)
        
        # convert result to json
        try:
            result = json.loads(result)
        except json.JSONDecodeError as e:
            raise BackupHandlerError(f'Failed to parse JSON: {e}', 1021)
        
        # make sure result exists and is ok
        if 'result' not in result or 'data' not in result or result['result'] != 'ok':
            raise BackupHandlerError(f'Invalid backup result: {result}', 1022)
        
        slug = result['data']['slug']
        
        self._cleanup.push(f'remove_backup_archive_{self._id}', RemoteCmd.exec, ['ha', 'backups', 'remove', slug], self._host)

        archive_path = PathModel(path=f'/root/backup/{slug}.tar', host=self._host)

        self._logger.info(f'Copying "{archive_path}" to "{dest.path}"')
        
        await RemoteSync.scp(archive_path, dest.join('archive.tar'))
        
        self._logger.info(f'Deleting backup archive on "{self._host}"')
        
        await self._cleanup.consume(f'remove_backup_archive_{self._id}')