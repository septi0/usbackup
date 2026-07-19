import logging
import datetime
import io
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.libraries.remote_sync import RemoteSync
from usbackup.libraries.cmd_exec import CmdExec
from usbackup.libraries.fs_adapter import FsAdapter
from usbackup.models.version import BackupVersionModel
from usbackup.models.retention_policy import RetentionPolicyModel
from usbackup.models.result import ResultModel
from usbackup.models.path import PathModel
from usbackup.services.runner import Runner
from usbackup.services.context import ContextService
from usbackup.exceptions import UsBackupRuntimeError

__all__ = ['Runner']

class ReplicationRunner(Runner):
    def __init__(self, context: ContextService, retention_policy: RetentionPolicyModel | None, *, mode: str = 'incremental', cleanup: CleanupQueue, logger: logging.Logger) -> None:
        super().__init__(context, retention_policy, cleanup=cleanup, logger=logger)
        self._mode: str = mode
        
    async def run(self, replicate_context: ContextService) -> ResultModel:
        run_time = datetime.datetime.now()
        
        if await self._context.lock_file_exists():
            raise UsBackupRuntimeError(f'Replication already running')
        
        replicate_version = await replicate_context.get_latest_version()
        
        if not replicate_version:
            raise UsBackupRuntimeError(f'No backup version found to replicate')
        
        self._logger.info(f'Replication started at {run_time} (mode: {self._mode})')
        
        await self._context.ensure_destination()
            
        await self._context.create_lock_file()
        self._cleanup.push(f'remove_lock_{self._id}', self._context.remove_lock_file)

        src = replicate_version.path
        latest_version = await self._context.get_latest_version()
        version = await self._context.generate_version()
        dest = version.path
        dest_link = latest_version.path if latest_version and self._mode == 'incremental' else None
        error = None

        self._cleanup.push(f'remove_inconsistent_version_{self._id}', self._remove_inconsistent_version, version)

        try:
            if self._mode == 'archive':
                await self._run_replication_archive(src, dest)
            else:
                await self._run_replication(src, dest, dest_link)
            self._cleanup.pop(f'remove_inconsistent_version_{self._id}')
        except Exception as e:
            self._logger.exception(e)
            await self._cleanup.consume(f'remove_inconsistent_version_{self._id}')
            error = e
        
        if not error:
            try:
                await self.apply_retention_policy()
            except Exception as e:
                self._logger.exception(f'Failed to apply retention policy. {e}')
                error = e

        if not error:
            try:
                await self._context.update_latest_symlink()
            except Exception as e:
                self._logger.exception(f'Failed to update latest symlink. {e}')

        await self._cleanup.consume(f'remove_lock_{self._id}')

        finish_time = datetime.datetime.now()

        elapsed = finish_time - run_time
        elapsed_s = elapsed.total_seconds()

        self._logger.info(f'Replication finished at {finish_time}. Elapsed time: {elapsed_s:.2f} seconds')
        
        return ResultModel(self._context, error=error, elapsed=elapsed)
    
    async def _run_replication(self, source: PathModel, dest: PathModel, dest_link: PathModel | None = None) -> None:
        options: list[str | tuple] = [
            'archive',
            'hard-links',
            'acls',
            'xattrs',
        ]

        if dest_link:
            self._logger.info(f'Using "{dest_link}" as link-dest for replication')
            options.append(('link-dest', dest_link.path))

        # add trailing slash to source path to copy the contents of the directory instead of the directory itself
        source_trailing = source.model_copy()
        source_trailing.path = source.path.rstrip('/') + '/'

        self._logger.info(f'Replicating "{source}" to "{dest}"')
        
        stats = await RemoteSync.rsync(source_trailing, dest, options=options)
        self._logger.debug(stats)

    async def _run_replication_archive(self, source: PathModel, dest: PathModel) -> None:
        archive_path = dest.join('archive.tar.gz')

        self._logger.info(f'Archiving "{source}" to "{archive_path}"')

        with FsAdapter.open(archive_path, 'wb') as f:
            await CmdExec.exec(['tar', 'czf', '-', '-C', source.path, '.'], stdout=f)