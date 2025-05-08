import logging
import datetime
import io
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.libraries.fs_adapter import FsAdapter
from usbackup.models.retention_policy import RetentionPolicyModel
from usbackup.models.result import ResultModel
from usbackup.models.path import PathModel
from usbackup.services.runner import Runner
from usbackup.services.context import ContextService
from usbackup.exceptions import UsbackupRuntimeError

__all__ = ['Runner']

class ReplicationRunner(Runner):
    def __init__(self, context: ContextService, retention_policy: RetentionPolicyModel, *, cleanup: CleanupQueue, logger: logging.Logger) -> None:
        super().__init__(context, retention_policy, cleanup=cleanup, logger=logger)
        
    async def run(self, replicate_context: ContextService) -> None:
        run_time = datetime.datetime.now()
        
        if await self._context.lock_file_exists():
            raise UsbackupRuntimeError(f'Replication already running')
        
        replicate_version = await replicate_context.get_latest_version()
        
        if not replicate_version:
            raise UsbackupRuntimeError(f'No backup version found to replicate')
        
        self._logger.info(f'Replication started at {run_time}')
        
        await self._context.ensure_destination()
            
        await self._context.create_lock_file()
        self._cleanup.push(f'remove_lock_{self._id}', self._context.remove_lock_file)

        src = replicate_version.path
        dest = self._context.destination
        error = None
        
        try:
            await self._run_replication(src, dest)
        except Exception as e:
            self._logger.exception(e)
            error = e
        
        if not error:
            try:
                await self.apply_retention_policy()
            except Exception as e:
                self._logger.exception(f'Failed to apply retention policy. {e}')
                error = e

        await self._cleanup.consume(f'remove_lock_{self._id}')

        finish_time = datetime.datetime.now()

        elapsed = finish_time - run_time
        elapsed_s = elapsed.total_seconds()

        self._logger.info(f'Replication finished at {finish_time}. Elapsed time: {elapsed_s:.2f} seconds')
        
        return ResultModel(self._context, message=self._log_stream.getvalue(), error=error, elapsed=elapsed)
    
    async def _run_replication(self, source: PathModel, dest: PathModel) -> None:
        options = [
            'archive',
            'hard-links',
            'acls',
            'xattrs',
            'delete',
            'delete-during',
        ]
        
        self._logger.info(f'Replicating "{source}" to "{dest}"')
        
        stats = await FsAdapter.rsync(source, dest, options=options)
        self._logger.debug(stats)