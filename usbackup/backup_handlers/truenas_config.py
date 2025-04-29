import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler, BackupHandlerError
from usbackup.remote import Remote

class TruenasConfigHandler(BackupHandler):
    handler: str = 'truenas-config'
    lexicon: dict = {}
    
    def __init__(self, src_host: Remote, config: dict, *, logger: logging.Logger = None):
        self._src_host: Remote = src_host
        
        self._logger: logging.Logger = logger

    async def backup(self, dest: str, dest_link: str = None) -> None:
        self._logger.info(f'Copying config files from "{self._src_host.host}" to "{dest}"')
        
        await cmd_exec.rsync('/data/freenas-v1.db', dest, host=self._src_host)
        await cmd_exec.rsync('/data/pwenc_secret', dest, host=self._src_host)