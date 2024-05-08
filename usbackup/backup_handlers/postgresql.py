import os
import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import HandlerError

class PostgreSqlHandler(BackupHandler):
    handler: str = 'postgresql'
    
    def __init__(self, src_host: Remote, snapshot_name: str, config: dict):
        super().__init__(src_host, snapshot_name, config)
        
        self._credentials_file: str = config.get("backup.postgresql.credentials-file", '')
        
        self._use_handler: bool = bool(config.get("backup.postgresql", ''))

    async def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> None:
        if not self._use_handler:
            raise HandlerError(f'"postgresql" handler not configured')
        
        logger = logger.getChild('postgresql')

        postgresql_dst = os.path.join(backup_dst, 'postgresql')

        if not os.path.isdir(postgresql_dst):
            logger.info(f'Creating postgresql backup folder "{postgresql_dst}"')
            await cmd_exec.mkdir(postgresql_dst)

        if backup_dst_link:
            backup_dst_link = os.path.join(backup_dst_link, 'postgresql')
        
        dump_filename = f'database_{self._src_host.host}.sql'
        dump_filepath = os.path.join(postgresql_dst, dump_filename)

        logger.info(f'Dumping postgresql databases for "{self._src_host.host}" to "{postgresql_dst}", filename "{dump_filename}"')
        
        options = []
        env = {}
        
        if self._credentials_file:
            env['PGPASSFILE'] = self._credentials_file
        else:
            env['PGPASSWORD'] = self._src_host.password
            options.append(('user', self._src_host.user))

        options = [
            *options,
            ('host', self._src_host.host),
            ('port', str(self._src_host.port)),
            ('file', dump_filepath),
        ]

        cmd_options = cmd_exec.parse_cmd_options(options)
        
        await cmd_exec.exec_cmd(['pg_dumpall', *cmd_options], env=env)