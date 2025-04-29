import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler, BackupHandlerError
from usbackup.remote import Remote

class OpenwrtConfigHandler(BackupHandler):
    handler: str = 'openwrt-config'
    lexicon: dict = {}
    
    def __init__(self, src_host: Remote, config: dict, *, logger: logging.Logger = None):
        self._src_host: Remote = src_host
        
        self._logger: logging.Logger = logger

    async def backup(self, dest: str, dest_link: str = None) -> None:
        self._logger.info(f'Generating backup archive "/tmp/backup-openwrt.tar.gz" on "{self._src_host.host}"')
        
        await cmd_exec.exec_cmd(['sysupgrade', '-b', '/tmp/backup-openwrt.tar.gz'], host=self._src_host)

        self._logger.info(f'Copying backup from "{self._src_host.host}" to "{dest}"')
        
        await cmd_exec.rsync(f'/tmp/backup-openwrt.tar.gz', dest, host=self._src_host, options=['remove-source-files'])