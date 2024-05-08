import os
import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import HandlerError, UsbackupConfigError

class MysqlHandler(BackupHandler):
    handler: str = 'mysql'
    
    def __init__(self, src_host: Remote, snapshot_name: str, config: dict):
        super().__init__(src_host, snapshot_name, config)
        
        self._mysql_hosts: list[Remote] = []
        self._credentials_file: str = config.get("backup.mysql.credentials-file", '')
        
        try:
            for mysql_host in shlex.split(config.get("backup.mysql", '')):
                self._mysql_hosts.append(Remote(mysql_host, 'root', 3306))
        except ValueError:
            raise UsbackupConfigError("Invalid mysql host provided for mysql")
        
        self._use_handler = bool(self._mysql_hosts)

    async def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> None:
        if not self._use_handler:
            raise HandlerError(f'"mysql" handler not configured')
        
        logger = logger.getChild('mysql')

        mysql_dst = os.path.join(backup_dst, 'mysql')

        if not os.path.isdir(mysql_dst):
            logger.info(f'Creating "mysql" backup folder "{mysql_dst}"')
            await cmd_exec.mkdir(mysql_dst)

        if backup_dst_link:
            backup_dst_link = os.path.join(backup_dst_link, 'mysql')
            
        for mysql_host in self._mysql_hosts:
            dump_filename = f'database_{mysql_host.host}.sql'
            dump_temp_filepath = os.path.join('/tmp', dump_filename)
            dump_final_filepath = os.path.join(mysql_dst, dump_filename)
            
            options = []
            
            # NOTE! defaults-file must be the first parameter!
            if self._credentials_file:
                options.append(('defaults-file', self._credentials_file))
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
                ('result-file', dump_temp_filepath)
            ]

            cmd_options = cmd_exec.parse_cmd_options(options)

            logger.info(f'Generating mysql dump "{dump_temp_filepath}" on "{self._src_host.host}"')
            
            await cmd_exec.exec_cmd(['mysqldump', *cmd_options], host=self._src_host)
            
            logger.info(f'Copying mysql dump from "{self._src_host.host}" to "{mysql_dst}"')
            
            await cmd_exec.rsync(dump_temp_filepath, dump_final_filepath, host=self._src_host)