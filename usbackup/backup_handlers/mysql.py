import os
import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import UsbackupConfigError, HandlerError

class MysqlHandler(BackupHandler):
    def __init__(self, src_host: Remote, snapshot_name: str, config: dict):
        self._name: str = 'mysql'
        self._snapshot_name: str = snapshot_name
        
        self._src_host: Remote = src_host
        self._credentials_file: str = config.get("backup.mysql.credentials-file", '')
        
        self._use_handler = bool(config.get("backup.mysql", ''))

    async def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> None:
        if not self._use_handler:
            raise HandlerError(f'Handler "{self._name}" not configured')
        
        logger = logger.getChild('mysql')

        mysql_dst = os.path.join(backup_dst, 'mysql')

        if not os.path.isdir(mysql_dst):
            logger.info(f'Creating mysql backup folder "{mysql_dst}"')
            await cmd_exec.mkdir(mysql_dst)

        if backup_dst_link:
            backup_dst_link = os.path.join(backup_dst_link, 'mysql')
        
        dump_filename = f'database_{self._src_host.host}.sql'
        dump_filepath = os.path.join(mysql_dst, dump_filename)
        
        options = []
        
        # NOTE! defaults-file must be the first parameter!
        if self._credentials_file:
            options.append(('defaults-file', self._credentials_file))
        else:
            options.append(('user', self._src_host.user))
            options.append(('password', self._src_host.password))

        options = [
            *options,
            ('host', self._src_host.host),
            ('port', str(self._src_host.port)),
            ('column-statistics', '0'),
            'no-tablespaces',
            'all-databases',
            'single-transaction',
            'routines',
            'triggers',
            ('lock-tables', 'false'),
        ]

        cmd_options = cmd_exec.parse_cmd_options(options)

        logger.info(f'Dumping mysql databases from "{self._src_host.host}" to "{mysql_dst}"')     
           
        with open(dump_filepath, 'w') as stdout:
            await cmd_exec.exec_cmd(['mysqldump', *cmd_options], stdout=stdout)
    
    def __bool__(self) -> bool:
        return self._use_handler
    
    @property
    def name(self) -> str:
        return self._name