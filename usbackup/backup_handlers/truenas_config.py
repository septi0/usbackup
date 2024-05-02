import os
import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import UsbackupConfigError, HandlerError

class TruenasConfigHandler(BackupHandler):
    def __init__(self, src_host: Remote, snapshot_name: str, config: dict):
        self._name: str = 'truenas-config'
        self._snapshot_name: str = snapshot_name
        
        self._src_host: Remote = src_host
        
        self._use_handler: bool = bool(config.get("backup.truenas-config", ''))

    async def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> None:
        if not self._use_handler:
            raise HandlerError(f'Handler "{self._name}" not configured')
        
        logger = logger.getChild('truenas-config')

        truenas_config_dst = os.path.join(backup_dst, 'truenas-config')

        if not os.path.isdir(truenas_config_dst):
            logger.info(f'Creating truenas-config backup folder "{truenas_config_dst}"')
            await cmd_exec.mkdir(truenas_config_dst)

        if backup_dst_link:
            backup_dst_link = os.path.join(backup_dst_link, 'truenas')

        logger.info(f'Copying config files from "{self._src_host.host}" to "{truenas_config_dst}"')
        
        await cmd_exec.rsync('/data/freenas-v1.db', truenas_config_dst, host=self._src_host)
        await cmd_exec.rsync('/data/pwenc_secret', truenas_config_dst, host=self._src_host)
    
    def __bool__(self) -> bool:
        return self._use_handler
    
    @property
    def name(self) -> str:
        return self._name