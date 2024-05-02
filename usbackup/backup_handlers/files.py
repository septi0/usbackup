import os
import shlex
import logging
import datetime
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import UsbackupConfigError, HandlerError

class FilesHandler(BackupHandler):
    def __init__(self, src_host: Remote, snapshot_name: str, config: dict):
        self._name: str = 'files'
        self._snapshot_name:str = snapshot_name
        
        self._src_host: Remote = src_host
        self._src: list[str] = self._gen_backup_src(config.get("backup.files", ''))
        self._exclude: list[str] = shlex.split(config.get("backup.files.exclude", ''))
        self._bwlimit: str = config.get("backup.files.bwlimit")
        self._mode: str = self._gen_backup_mode(config)
        
        self._use_handler = bool(self._src)

    async def backup(self, dest: str, dest_link: str = None, *, logger: logging.Logger = None) -> list:
        if not self._use_handler:
            raise HandlerError(f'Handler "{self._name}" not configured')
        
        logger = logger.getChild('files')

        dest = os.path.join(dest, 'files')

        if not os.path.isdir(dest):
            logger.info(f'Creating files backup folder "{dest}"')
            await cmd_exec.mkdir(dest)

        if dest_link:
            dest_link = os.path.join(dest_link, 'files')

        if self._mode == 'incremental':
            logger.info('Using incremental backup mode')

            await self._backup_rsync(dest, dest_link, logger=logger)
        elif self._mode == 'full':
            logger.info(f'Using full backup mode')

            await self._backup_rsync(dest, None, logger=logger)
        elif self._mode == 'archive':
            logger.info(f'Using archive backup mode')
            
            await self._backup_tar(dest, logger=logger)
        else:
            raise HandlerError('Invalid backup mode')
    
    def _gen_backup_src(self, backup_src: str) -> list[str]:
        backup_src = shlex.split(backup_src)
        result = []

        for src in backup_src:
            # make sure all sources are absolute paths
            if not os.path.isabs(src):
                raise UsbackupConfigError(f'Invalid backup_files source: "{src}"')

            # make sure paths end with a slash
            if not src.endswith('/'):
                src += '/'

            result.append(src)

        return result
    
    def _gen_backup_mode(self, config: dict) -> str:
        backup_mode = config.get("backup_files.mode", 'incremental')

        if backup_mode not in ['incremental', 'archive', 'full']:
            raise UsbackupConfigError(f'Invalid backup_files.mode: "{backup_mode}"')
        
        return backup_mode
    
    async def _backup_rsync(self, dest: str, dest_link: str, *, logger: logging.Logger) -> None:
        for dir_src in self._src:
            options = [
                'archive',
                'hard-links',
                'acls',
                'xattrs',
                'delete',
                'delete-during',
                'stats',
                'relative',
                ('out-format', "%t %i %f"),
            ]

            if self._exclude:
                for exclude in self._exclude:
                    # append exclude path if it starts with the source path
                    if exclude.startswith(dir_src):
                        options.append(('exclude', exclude))

            if self._bwlimit:
                options.append(('bwlimit', str(self._bwlimit)))

            if dest_link:
                options.append(('link-dest', dest_link))

            logger.info(f'Copying "{dir_src}" from "{self._src_host.host}" to "{dest}"')
            start_time = datetime.datetime.now()
            
            stats = await cmd_exec.rsync(dir_src, dest, host=self._src_host, options=options)
            
            logger.debug(stats)
            
            end_time = datetime.datetime.now()
            elapsed_time = end_time - start_time
            elapsed_time_s = elapsed_time.total_seconds()
            
            logger.info(f'Finished copying "{dir_src}" from "{self._src_host.host}" in {elapsed_time_s:.2f} seconds')
    
    async def _backup_tar(self, dest: str, *, logger: logging.Logger) -> None:
        destination_archive = os.path.join(dest, f'{self._snapshot_name}.tar.gz')
        sources = []

        for src in self._src:
            if not self._src_host.local:
                raise HandlerError('Archive mode does not support remote backup')

            sources.append(src)

        if not sources:
            raise HandlerError('No sources to archive')
        
        logger.info(f'Archiving "{sources}" to "{destination_archive}"')

        stats = await cmd_exec.tar(destination_archive, sources)

        logger.debug(stats)
    
    def __bool__(self) -> bool:
        return self._use_handler
    
    @property
    def name(self) -> str:
        return self._name