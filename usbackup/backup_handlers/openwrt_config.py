import os
import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import HandlerError

class OpenwrtConfigHandler(BackupHandler):
    handler: str = 'openwrt-config'
    
    def __init__(self, src_host: Remote, snapshot_name: str, config: dict):
        super().__init__(src_host, snapshot_name, config)
        
        self._use_handler: bool = bool(config.get("backup.openwrt-config", ''))

    async def backup(self, dest: str, dest_link: str = None, *, logger: logging.Logger = None) -> None:
        if not bool(self._use_handler):
            raise HandlerError(f'"openwrt-config" handler not configured')
        
        logger = logger.getChild('openwrt-config')

        logger.info(f'Generating backup archive "/tmp/backup-openwrt.tar.gz" on "{self._src_host.host}"')
        
        await cmd_exec.exec_cmd(['sysupgrade', '-b', '/tmp/backup-openwrt.tar.gz'], host=self._src_host)

        logger.info(f'Copying backup from "{self._src_host.host}" to "{dest}"')
        
        await cmd_exec.rsync(f'/tmp/backup-openwrt.tar.gz', dest, host=self._src_host, options=['remove-source-files'])