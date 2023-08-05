import os
import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import UsbackupConfigError, HandlerError

class OpenWrtHandler(BackupHandler):
    def __init__(self, snapshot_name: str, config: dict):
        self._name: str = 'openwrt'
        self._snapshot_name: str = snapshot_name
        
        self._openwrt_hosts: list[Remote] = []

        try:
            for openwrt_host in shlex.split(config.get("backup_openwrt", "")):
                self._openwrt_hosts.append(Remote(openwrt_host, 'root', 22))
        except ValueError:
            raise UsbackupConfigError("Invalid remote provided for openwrt")

    async def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> list:
        if not bool(self._openwrt_hosts):
            raise HandlerError(f'Handler "{self._name}" not configured')
        
        logger = logger.getChild('openwrt')
        
        logger.info("* Backing up openwrt instance")

        openwrt_dst = os.path.join(backup_dst, 'openwrt')

        if not os.path.isdir(openwrt_dst):
            logger.info(f'Creating openwrt backup folder "{openwrt_dst}"')
            await cmd_exec.mkdir(openwrt_dst)

        if backup_dst_link:
            backup_dst_link = os.path.join(backup_dst_link, 'openwrt')

        report = []

        for openwrt_host in self._openwrt_hosts:
            logger.info(f'Generating backup archive "/tmp/backup-openwrt.tar.gz" on "{openwrt_host.host}"')

            report += [f'* "{str(openwrt_host)}" -> "{openwrt_dst}"', '']

            kwargs = {}
            kwargs['port'] = openwrt_host.port

            if openwrt_host.password:
                kwargs['password'] = openwrt_host.password
                logger.warning('Using password in plain is insecure. Consider using ssh keys instead')

            ssh_out = await cmd_exec.ssh(['sysupgrade', '-b', '/tmp/backup-openwrt.tar.gz'], openwrt_host.host, openwrt_host.user, **kwargs)

            # logger.debug(f'ssh output: {ssh_out}')

            logger.info(f'Moving backup from "{str(openwrt_host)}" to backup folder "{openwrt_dst}"')

            scp_out = await cmd_exec.scp(f'{str(openwrt_host)}:/tmp/backup-openwrt.tar.gz', openwrt_dst, **kwargs)

            # logger.debug(f'scp output: {scp_out}')

            report += [str(ssh_out), str(scp_out), '']

        return report

    def __bool__(self) -> bool:
        return bool(self._openwrt_hosts)
    
    @property
    def name(self) -> str:
        return self._name
