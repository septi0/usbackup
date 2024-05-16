import os
import shlex
import logging
import uuid
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

    async def backup(self, dest: str, dest_link: str = None, *, logger: logging.Logger = None) -> None:
        if not self._use_handler:
            raise HandlerError(f'"mysql" handler not configured')
        
        logger = logger.getChild('mysql')
            
        tmp_dest = os.path.join('/tmp', str(uuid.uuid4()))
        
        # backup mysql for all connections
        for mysql_host in self._mysql_hosts:
            mysql_opts = self._gen_mysql_opts(mysql_host)
            
            # get databases
            databases = await self._get_databases(mysql_opts)
            
            if not databases:
                logger.info(f'No databases found for "{mysql_host}"')
                continue
            
            tmp_conn_dest = os.path.join(tmp_dest, mysql_host.host)
            
            # create tmp folder
            logger.info(f'Creating tmp folder "{tmp_conn_dest}" on "{self._src_host.host}"')
            
            await cmd_exec.mkdir(tmp_conn_dest, host=self._src_host)
            
            for database in databases:
                logger.info(f'Generating mysql dump for database "{database}" in "{tmp_conn_dest}" on "{self._src_host.host}"')
                
                # generate mysql dump for database
                await self._mysqldump(database, tmp_conn_dest, mysql_opts)
                
            logger.info(f'Copying mysql dump from "{self._src_host.host}" to "{dest}"')
        
            # copy connection dumps to local backup folder
            await cmd_exec.rsync(tmp_conn_dest, dest, host=self._src_host, options=['recursive'])

        logger.info(f'Deleting tmp folder "{tmp_dest}" on "{self._src_host.host}"')

        # remove tmp folder
        await cmd_exec.remove(tmp_dest, host=self._src_host)

    def _gen_mysql_opts(self, mysql_host: Remote) -> list:
        mysql_opts = []

        if self._credentials_file:
            with open(self._credentials_file, 'r') as f:
                line = f.readline().strip()
                
            # extract user/password from file
            user, password = line.split(':')
            
            mysql_opts.append(('user', user))
            mysql_opts.append(('password', password))
        else:
            mysql_opts.append(('user', mysql_host.user))
            mysql_opts.append(('password', mysql_host.password))

        mysql_opts.append(('host', mysql_host.host))
        mysql_opts.append(('port', str(mysql_host.port)))

        return mysql_opts
    
    async def _get_databases(self, mysql_opts: list) -> list:
        databases = []
        
        cmd_options = [
            *mysql_opts,
            'silent',
            'raw',
            ('execute', 'SHOW DATABASES'),
        ]
        
        cmd_options = cmd_exec.parse_cmd_options(cmd_options, arg_separator='=')
        
        result = await cmd_exec.exec_cmd(['mysql', *cmd_options], host=self._src_host)
        
        for database in result.splitlines():
            # exclude system databases
            if database not in ('information_schema', 'performance_schema', 'sys'):
                databases.append(database)
        
        return databases
    
    async def _mysqldump(self, database: str, dump_dst: str, mysql_opts: list) -> None:
        dump_filepath = os.path.join(dump_dst, f'{database}.sql')
        
        cmd_options = [
            *mysql_opts,
            ('column-statistics', '0'),
            'no-tablespaces',
            'single-transaction',
            'routines',
            'triggers',
            ('lock-tables', 'false'),
            ('result-file', dump_filepath)
        ]

        cmd_options = cmd_exec.parse_cmd_options(cmd_options, arg_separator='=')
        
        await cmd_exec.exec_cmd(['mysqldump', *cmd_options, database], host=self._src_host)
