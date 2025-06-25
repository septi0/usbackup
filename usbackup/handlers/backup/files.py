import os
import datetime
from typing import Literal
from usbackup.libraries.cmd_exec import CmdExec
from usbackup.libraries.fs_adapter import FsAdapter
from usbackup.models.path import PathModel
from usbackup.models.host import HostModel
from usbackup.handlers.backup import HandlerBaseModel, BackupHandler, BackupHandlerError

class FilesHandlerModel(HandlerBaseModel):
    handler: str = 'files'
    limit: list[str] = []
    exclude: list[str] = []
    bwlimit: int | None = None
    mode: Literal['incremental', 'archive', 'full'] = 'incremental'

class FilesHandler(BackupHandler):
    handler: str = 'files'
    
    def __init__(self, model: FilesHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)
        
        self._src_paths: list[PathModel] = self._gen_backup_src(model.limit, self._host)
        self._exclude: list[str] = model.exclude
        self._bwlimit: int | None = model.bwlimit
        self._mode: str = model.mode

    async def backup(self, dest: PathModel, dest_link: PathModel | None = None) -> None:
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
    
    def _gen_backup_src(self, limit: list, host: HostModel) -> list[PathModel]:
        src_paths = []

        if limit:
            for src in limit:
                # make sure all sources are absolute paths
                if not os.path.isabs(src):
                    raise BackupHandlerError(f'Invalid limit "{src}". Path must be absolute', 1031)

                # make sure paths end with a slash
                if not src.endswith('/'):
                    src += '/'

                src_paths.append(PathModel(path=src, host=host))
        else:
            src_paths = [PathModel(path='/', host=host)]

        return src_paths
    
    async def _backup_rsync(self, dest: PathModel, dest_link: PathModel | None = None) -> None:
        for src in self._src_paths:
            options: list[str | tuple] = [
                'archive',
                'hard-links',
                'acls',
                'xattrs',
                'relative',
            ]

            if self._exclude:
                for exclude in self._exclude:
                    options.append(('exclude', exclude))

            if self._bwlimit:
                options.append(('bwlimit', str(self._bwlimit)))

            if dest_link:
                options.append(('link-dest', dest_link.path))

            self._logger.info(f'Copying "{src}" to "{dest.path}"')
            start_time = datetime.datetime.now()
            
            stats = await FsAdapter.rsync(src, dest, options=options)
            
            self._logger.debug(stats)
            
            end_time = datetime.datetime.now()
            elapsed_time = end_time - start_time
            elapsed_time_s = elapsed_time.total_seconds()
            
            self._logger.info(f'Finished copying "{src}" in {elapsed_time_s:.2f} seconds')
    
    async def _backup_tar(self, dest: PathModel) -> None:
        sources = []

        for src in self._src_paths:
            sources.append(src.path)

        if not sources:
            raise BackupHandlerError('No sources to archive', 1033)
        
        async with FsAdapter.open(dest.join('archive.tar.gz'), 'wb') as f:
            self._logger.info(f'Streaming archive from "{self._host}" to "{dest.path}"')
            
            await CmdExec.exec(['tar', 'czf', '-', *sources], host=self._host, stdout=f)