import os
import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import HandlerError

class TruenasConfigHandler(BackupHandler):
    handler: str = 'truenas-config'
    
    def __init__(self, src_host: Remote, snapshot_name: str, config: dict):
        super().__init__(src_host, snapshot_name, config)
        
        self._use_handler: bool = bool(config.get("backup.truenas-config", ''))

    async def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> None:
        if not self._use_handler:
            raise HandlerError(f'"truenas-config" handler not configured')
        
        logger = logger.getChild('truenas-config')

        truenas_config_dst = os.path.join(backup_dst, 'truenas-config')

        if not os.path.isdir(truenas_config_dst):
            logger.info(f'Creating "truenas-config" backup folder "{truenas_config_dst}"')
            await cmd_exec.mkdir(truenas_config_dst)

        if backup_dst_link:
            backup_dst_link = os.path.join(backup_dst_link, 'truenas')

        logger.info(f'Copying config files from "{self._src_host.host}" to "{truenas_config_dst}"')
        
        await cmd_exec.rsync('/data/freenas-v1.db', truenas_config_dst, host=self._src_host)
        await cmd_exec.rsync('/data/pwenc_secret', truenas_config_dst, host=self._src_host)