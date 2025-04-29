import os
import logging
import datetime
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler, BackupHandlerError
from usbackup.remote import Remote

class FilesHandler(BackupHandler):
    handler: str = 'files'
    lexicon: dict = {
        'limit': {'type': list},
        'exclude': {'type': list},
        'bwlimit': {'type': int},
        'mode': {'type': str, 'default': 'incremental', 'allowed': ['incremental', 'archive', 'full']},
    }
    
    def __init__(self, src_host: Remote, config: dict, *, logger: logging.Logger) -> None:
        self._src_host: Remote = src_host
        
        self._src_paths: list[str] = self._gen_backup_src(config.get("limit"))
        self._exclude: list[str] = config.get("exclude", [])
        self._bwlimit: str = config.get("bwlimit")
        self._mode: str = config["mode"]
        
        self._logger = logger

    async def backup(self, dest: str, dest_link: str = None) -> list:
        if self._mode == 'incremental':
            self._logger.info('Using incremental backup mode')

            await self._backup_rsync(dest, dest_link)
        elif self._mode == 'full':
            self._logger.info(f'Using full backup mode')

            await self._backup_rsync(dest, None)
        elif self._mode == 'archive':
            self._logger.info(f'Using archive backup mode')
            
            await self._backup_tar(dest)
        else:
            raise BackupHandlerError('Invalid backup mode', 1030)
    
    def _gen_backup_src(self, limit: list) -> list[str]:
        src_paths = []

        if limit:
            for src in limit:
                # make sure all sources are absolute paths
                if not os.path.isabs(src):
                    raise BackupHandlerError(f'Invalid limit "{src}". Path must be absolute', 1031)

                # make sure paths end with a slash
                if not src.endswith('/'):
                    src += '/'

                src_paths.append(src)
        else:
            src_paths = ['/']

        return src_paths
    
    async def _backup_rsync(self, dest: str, dest_link: str) -> None:
        for dir_src in self._src_paths:
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
                    options.append(('exclude', exclude))

            if self._bwlimit:
                options.append(('bwlimit', str(self._bwlimit)))

            if dest_link:
                options.append(('link-dest', dest_link))

            self._logger.info(f'Copying "{dir_src}" from "{self._src_host.host}" to "{dest}"')
            start_time = datetime.datetime.now()
            
            stats = await cmd_exec.rsync(dir_src, dest, host=self._src_host, options=options)
            
            self._logger.debug(stats)
            
            end_time = datetime.datetime.now()
            elapsed_time = end_time - start_time
            elapsed_time_s = elapsed_time.total_seconds()
            
            self._logger.info(f'Finished copying "{dir_src}" from "{self._src_host.host}" in {elapsed_time_s:.2f} seconds')
    
    async def _backup_tar(self, dest: str) -> None:
        destination_archive = os.path.join(dest, f'{self._src_host.host}.tar.gz')
        sources = []

        for src in self._src_paths:
            if not self._src_host.local:
                raise BackupHandlerError('Archive mode does not support remote backup', 1032)

            sources.append(src)

        if not sources:
            raise BackupHandlerError('No sources to archive', 1033)
        
        self._logger.info(f'Archiving "{sources}" to "{destination_archive}"')

        stats = await cmd_exec.tar(destination_archive, sources)

        self._logger.debug(stats)