import os
import logging
import json
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import HandlerError

class HomeAssistantConfigHandler(BackupHandler):
    handler: str = 'homeassistant-config'
    
    def __init__(self, src_host: Remote, snapshot_name: str, config: dict):
        super().__init__(src_host, snapshot_name, config)
        
        self._use_handler: bool = bool(config.get("backup.homeassistant-config", ''))

    async def backup(self, dest: str, dest_link: str = None, *, logger: logging.Logger = None) -> None:
        if not bool(self._use_handler):
            raise HandlerError(f'"homeassistant-config" handler not configured')
        
        logger = logger.getChild('homeassistant-config')

        logger.info(f'Generating backup archive on "{self._src_host.host}"')
        
        result = await cmd_exec.exec_cmd(['ha', 'backups', 'new', '--name', 'usbackup', '--raw-json', '--no-progress'], host=self._src_host)
        
        # convert result to json
        try:
            result = json.loads(result)
        except json.JSONDecodeError as e:
            raise HandlerError(f'Failed to parse JSON: {e}')
        
        # make sure result exists and is ok
        if 'result' not in result or 'data' not in result or result['result'] != 'ok':
            raise HandlerError(f'Invalid backup result: {result}')
        
        slug = result['data']['slug']

        logger.info(f'Copying backup from "{self._src_host.host}" to "{dest}"')
        
        await cmd_exec.scp(f'/root/backup/{slug}.tar', os.path.join(dest, 'backup.tar'), host=self._src_host)
        
        logger.info(f'Deleting backup archive on "{self._src_host.host}"')
        
        await cmd_exec.exec_cmd(['ha', 'backups', 'remove', slug], host=self._src_host)