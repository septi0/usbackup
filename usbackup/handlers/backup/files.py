import os
import datetime
import usbackup.libraries.cmd_exec as cmd_exec
from typing import Literal
from usbackup.handlers.backup import UsBackupHandlerBaseModel, BackupHandler, BackupHandlerError
from usbackup.models.remote import RemoteModel

class FilesHandlerModel(UsBackupHandlerBaseModel):
    handler: str = 'files'
    limit: list[str] = []
    exclude: list[str] = []
    bwlimit: int = None
    mode: Literal['incremental', 'archive', 'full'] = 'incremental'

class FilesHandler(BackupHandler):
    handler: str = 'files'
    
    def __init__(self, host: RemoteModel, model: FilesHandlerModel, *args, **kwargs) -> None:
        super().__init__(host, model, *args, **kwargs)
        
        self._host: RemoteModel = host
        
        self._src_paths: list[str] = self._gen_backup_src(model.limit)
        self._exclude: list[str] = model.exclude
        self._bwlimit: str = model.bwlimit
        self._mode: str = model.mode

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

            self._logger.info(f'Copying "{dir_src}" from "{self._host}" to "{dest}"')
            start_time = datetime.datetime.now()
            
            stats = await cmd_exec.rsync(dir_src, dest, host=self._host, options=options)
            
            self._logger.debug(stats)
            
            end_time = datetime.datetime.now()
            elapsed_time = end_time - start_time
            elapsed_time_s = elapsed_time.total_seconds()
            
            self._logger.info(f'Finished copying "{dir_src}" from "{self._host}" in {elapsed_time_s:.2f} seconds')
    
    async def _backup_tar(self, dest: str) -> None:
        destination_archive = os.path.join(dest, f'{self._host}.tar.gz')
        sources = []

        for src in self._src_paths:
            if not self._host.local:
                raise BackupHandlerError('Archive mode does not support remote backup', 1032)

            sources.append(src)

        if not sources:
            raise BackupHandlerError('No sources to archive', 1033)
        
        self._logger.info(f'Archiving "{sources}" to "{destination_archive}"')

        stats = await cmd_exec.tar(destination_archive, sources)

        self._logger.debug(stats)