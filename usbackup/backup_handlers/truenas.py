import os
import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import UsbackupConfigError, HandlerError

class TruenasHandler(BackupHandler):
    def __init__(self, snapshot_name: str, config: dict):
        self._name: str = 'truenas'
        self._snapshot_name: str = snapshot_name
        
        self._truenas_hosts: list[Remote] = []

        try:
            for truenas_host in shlex.split(config.get("backup_truenas", '')):
                self._truenas_hosts.append(Remote(truenas_host, 'root', 22))
        except ValueError:
            raise UsbackupConfigError("Invalid truenas host provided for truenas")

    async def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> list:
        if not bool(self._truenas_hosts):
            raise HandlerError(f'Handler "{self._name}" not configured')
        
        logger = logger.getChild('truenas')
        
        logger.info("* Backing up truenas instances")

        truenas_dst = os.path.join(backup_dst, 'truenas-config')

        if not os.path.isdir(truenas_dst):
            logger.info(f'Creating truenas backup folder "{truenas_dst}"')
            await cmd_exec.mkdir(truenas_dst)

        if backup_dst_link:
            backup_dst_link = os.path.join(backup_dst_link, 'truenas')

        report = []

        for truenas_host in self._truenas_hosts:
            report += [f'* "{str(truenas_host)}" -> "{truenas_dst}"', '']

            kwargs = {}
            kwargs['port'] = truenas_host.port

            if truenas_host.password:
                kwargs['password'] = truenas_host.password

            logger.info(f'Moving config files from "{str(truenas_host)}" to backup folder "{truenas_dst}"')

            scp_out = []
            scp_out.append(await cmd_exec.scp(f'{str(truenas_host)}:/data/freenas-v1.db', truenas_dst, **kwargs))
            scp_out.append(await cmd_exec.scp(f'{str(truenas_host)}:/data/pwenc_secret', truenas_dst, **kwargs))

            report += [str('\n'.join(scp_out)), '']

        return report
    
    def __bool__(self) -> bool:
        return bool(self._truenas_hosts)
    
    @property
    def name(self) -> str:
        return self._name