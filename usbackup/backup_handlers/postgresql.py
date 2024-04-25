import os
import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import UsbackupConfigError, HandlerError

class PostgreSqlHandler(BackupHandler):
    def __init__(self, snapshot_name: str, config: dict):
        self._name: str = 'postgresql'
        self._snapshot_name: str = snapshot_name
        
        self._postgresql_credentials_file: str = config.get("backup_postgresql.credentials_file", '')
        self._postgresql_hosts: list[Remote] = []

        try:
            for postgresql_host in shlex.split(config.get("backup_postgresql", '')):
                self._postgresql_hosts.append(Remote(postgresql_host, 'root', 5432))
        except ValueError:
            raise UsbackupConfigError("Invalid postgresql host provided for postgresql")

    async def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> list:
        if not bool(self._postgresql_hosts):
            raise HandlerError(f'Handler "{self._name}" not configured')
        
        logger = logger.getChild('postgresql')
        
        logger.info("* Backing up postgresql instances")

        postgresql_dst = os.path.join(backup_dst, 'postgresql')

        if not os.path.isdir(postgresql_dst):
            logger.info(f'Creating postgresql backup folder "{postgresql_dst}"')
            await cmd_exec.mkdir(postgresql_dst)

        if backup_dst_link:
            backup_dst_link = os.path.join(backup_dst_link, 'postgresql')

        report = []
        
        for postgresql_host in self._postgresql_hosts:
            dump_filename = f'database_{postgresql_host.host}.sql'
            dump_filepath = os.path.join(postgresql_dst, dump_filename)

            logger.info(f'Dumping postgresql databases for "{postgresql_host.user}@{postgresql_host.host}" to "{postgresql_dst}", filename "{dump_filename}"')
            report += [f'* "{postgresql_host.user}@{postgresql_host.host}" -> "{postgresql_dst}"', '']
            
            options = []
            env = {}
            
            if self._postgresql_credentials_file:
                env['PGPASSFILE'] = self._postgresql_credentials_file
            else:
                env['PGPASSWORD'] = postgresql_host.password
                options.append(('user', postgresql_host.user))

            options = [
                *options,
                ('host', postgresql_host.host),
                ('port', str(postgresql_host.port)),
                ('file', dump_filepath),
            ]

            cmd_options = cmd_exec.parse_cmd_options(options)
            
            with open(dump_filepath, 'w') as stdout:
                report_line = await cmd_exec.exec_cmd(['pg_dumpall', *cmd_options], stdout=stdout, env=env)

            report += [str(report_line), '']

        return report
    
    def __bool__(self) -> bool:
        return bool(self._postgresql_hosts)
    
    @property
    def name(self) -> str:
        return self._name