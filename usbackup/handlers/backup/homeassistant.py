import os
import json
import usbackup.libraries.cmd_exec as cmd_exec
from usbackup.models.remote import RemoteModel
from usbackup.handlers.backup import UsBackupHandlerBaseModel, BackupHandler, BackupHandlerError

class HomeassistantHandlerModel(UsBackupHandlerBaseModel):
    handler: str = 'homeassistant'

class HomeassistantHandler(BackupHandler):
    handler: str = 'homeassistant'

    def __init__(self, host: RemoteModel, model: HomeassistantHandlerModel, *args, **kwargs) -> None:
        super().__init__(host, model, *args, **kwargs)
        
        self._host: RemoteModel = host

    async def backup(self, dest: str, dest_link: str = None) -> None:
        self._logger.info(f'Generating backup archive on "{self._host}"')
        
        result = await cmd_exec.exec_cmd(['ha', 'backups', 'new', '--name', 'usbackup', '--raw-json', '--no-progress'], host=self._host)
        
        # convert result to json
        try:
            result = json.loads(result)
        except json.JSONDecodeError as e:
            raise BackupHandlerError(f'Failed to parse JSON: {e}', 1021)
        
        # make sure result exists and is ok
        if 'result' not in result or 'data' not in result or result['result'] != 'ok':
            raise BackupHandlerError(f'Invalid backup result: {result}', 1022)
        
        slug = result['data']['slug']
        
        self._cleanup.add_job(f'remove_ha_backup_{self._id}', cmd_exec.exec_cmd, ['ha', 'backups', 'remove', slug], host=self._host)

        self._logger.info(f'Copying backup from "{self._host}" to "{dest}"')
        
        await cmd_exec.scp(f'/root/backup/{slug}.tar', os.path.join(dest, 'backup.tar'), host=self._host)
        
        self._logger.info(f'Deleting backup archive on "{self._host}"')
        
        await self._cleanup.run_job(f'remove_ha_backup_{self._id}')