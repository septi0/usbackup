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

    def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> list:
        if not bool(self._openwrt_hosts):
            raise HandlerError(f'Handler "{self._name}" not configured')
        
        logger = logger.getChild('openwrt')
        
        logger.info("* Backing up openwrt instance")

        openwrt_dst = os.path.join(backup_dst, 'openwrt')

        if not os.path.isdir(openwrt_dst):
            logger.info(f'Creating openwrt backup folder "{openwrt_dst}"')
            cmd_exec.mkdir(openwrt_dst)

        if backup_dst_link:
            backup_dst_link = os.path.join(backup_dst_link, 'openwrt')

        report = []

        for openwrt_host in self._openwrt_hosts:
            logger.info(f'Generating backup archive "/tmp/backup-openwrt.tar.gz" on "{openwrt_host.host}"')

            report += [f'* "{openwrt_host.user}@{openwrt_host.host}" -> "{openwrt_dst}"', '']

            cmd_prefix = []

            if openwrt_host.password:
                cmd_prefix += ['sshpass', '-p', str(openwrt_host.password)]

            ssh_out = cmd_exec.exec_cmd([*cmd_prefix, 'ssh', '-p', str(openwrt_host.port), f'{openwrt_host.user}@{openwrt_host.host}', 'sysupgrade', '-b', '/tmp/backup-openwrt.tar.gz'])

            logger.debug(f'ssh output: {ssh_out}')

            logger.info(f'Moving backup from "{openwrt_host.user}@{openwrt_host.host}" to backup folder "{openwrt_dst}"')

            scp_out = cmd_exec.exec_cmd([*cmd_prefix, 'scp', '-P', str(openwrt_host.port), f'{openwrt_host.user}@{openwrt_host.host}:/tmp/backup-openwrt.tar.gz', openwrt_dst])

            logger.debug(f'scp output: {scp_out}')

            report += [str(ssh_out), str(scp_out), '']

        return report

    def __bool__(self) -> bool:
        return bool(self._openwrt_hosts)
    
    @property
    def name(self) -> str:
        return self._name
