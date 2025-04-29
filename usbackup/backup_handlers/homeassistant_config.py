import os
import logging
import json
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler, BackupHandlerError
from usbackup.remote import Remote

class HomeassistantConfigHandler(BackupHandler):
    handler: str = 'homeassistant-config'
    lexicon: dict = {}
    
    def __init__(self, src_host: Remote, config: dict, *, logger: logging.Logger = None):
        self._src_host: Remote = src_host
        
        self._logger: logging.Logger = logger

    async def backup(self, dest: str, dest_link: str = None) -> None:
        self._logger.info(f'Generating backup archive on "{self._src_host.host}"')
        
        try:
            result = await cmd_exec.exec_cmd(['ha', 'backups', 'new', '--name', 'usbackup', '--raw-json', '--no-progress'], host=self._src_host)
        except Exception as e:
            raise BackupHandlerError(f'Failed to create backup: {e}', 1020)
        
        # convert result to json
        try:
            result = json.loads(result)
        except json.JSONDecodeError as e:
            raise BackupHandlerError(f'Failed to parse JSON: {e}', 1021)
        
        # make sure result exists and is ok
        if 'result' not in result or 'data' not in result or result['result'] != 'ok':
            raise BackupHandlerError(f'Invalid backup result: {result}', 1022)
        
        slug = result['data']['slug']

        self._logger.info(f'Copying backup from "{self._src_host.host}" to "{dest}"')
        
        await cmd_exec.scp(f'/root/backup/{slug}.tar', os.path.join(dest, 'backup.tar'), host=self._src_host)
        
        self._logger.info(f'Deleting backup archive on "{self._src_host.host}"')
        
        try:
            await cmd_exec.exec_cmd(['ha', 'backups', 'remove', slug], host=self._src_host)
        except Exception as e:
            raise BackupHandlerError(f'Failed to delete backup: {e}', 1023)