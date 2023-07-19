import os
import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import UsbackupConfigError, HandlerError

class MysqlHandler(BackupHandler):
    def __init__(self, snapshot_name: str, config: dict):
        self._name: str = 'mysql'
        self._snapshot_name: str = snapshot_name
        
        self._mysql_defaults_file: str = config.get("backup_mysql.defaults_file", '')
        self._mysql_hosts: list[Remote] = []

        try:
            for mysql_host in shlex.split(config.get("backup_mysql", '')):
                self._mysql_hosts.append(Remote(mysql_host, 'root', 3306))
        except ValueError:
            raise UsbackupConfigError("Invalid mysql host provided for mysql")

    def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> list:
        if not bool(self._mysql_hosts):
            raise HandlerError(f'Handler "{self._name}" not configured')
        
        logger = logger.getChild('mysql')
        
        logger.info("* Backing up mysql instances")

        mysql_dst = os.path.join(backup_dst, 'mysql')

        if not os.path.isdir(mysql_dst):
            logger.info(f'Creating mysql backup folder "{mysql_dst}"')
            cmd_exec.mkdir(mysql_dst)

        if backup_dst_link:
            backup_dst_link = os.path.join(backup_dst_link, 'mysql')

        report = []
        
        for mysql_host in self._mysql_hosts:
            dump_filename = f'database_{mysql_host.host}.sql'
            dump_filepath = os.path.join(mysql_dst, dump_filename)

            logger.info(f'Dumping mysql databases for "{mysql_host.user}@{mysql_host.host}" to "{mysql_dst}", filename "{dump_filename}"')
            report += [f'* "{mysql_host.user}@{mysql_host.host}" -> "{mysql_dst}"', '']
            
            options = []
            
            # NOTE! defaults-file must be the first parameter!!!
            if self._mysql_defaults_file:
                options.append(('defaults-file', self._mysql_defaults_file))
            else:
                options.append(('user', mysql_host.user))
                options.append(('password', mysql_host.password))

            options = [
                *options,
                ('host', mysql_host.host),
                ('port', str(mysql_host.port)),
                ('column-statistics', '0'),
                'no-tablespaces',
                'all-databases',
                'single-transaction',
                'routines',
                'triggers',
                ('lock-tables', 'false'),
            ]

            cmd_options = cmd_exec.parse_cmd_options(options)
            
            with open(dump_filepath, 'w') as stdout:
                report_line = cmd_exec.exec_cmd(['mysqldump', *cmd_options], stdout=stdout)

            logger.debug(f'mysqldump output: {report_line}')
            report += [str(report_line), '']

        return report
    
    def __bool__(self) -> bool:
        return bool(self._mysql_hosts)
    
    @property
    def name(self) -> str:
        return self._name