import logging
import datetime
from usbackup.libraries.cmd_exec import CmdExec
from usbackup.libraries.fs_adapter import FsAdapter
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.models.version import BackupVersionModel
from usbackup.models.retention_policy import RetentionPolicyModel
from usbackup.models.result import ResultModel
from usbackup.models.path import PathModel
from usbackup.services.runner import Runner
from usbackup.services.context import ContextService
from usbackup.exceptions import UsbackupRuntimeError
from usbackup.handlers import handler_factory

__all__ = ['Runner']

class BackupRunner(Runner):
    def __init__(self, context: ContextService, retention_policy: RetentionPolicyModel, *, cleanup: CleanupQueue, logger: logging.Logger) -> None:
        super().__init__(context, retention_policy, cleanup=cleanup, logger=logger)
        
    async def run(self) -> None:
        run_time = datetime.datetime.now()
        
        if await self._context.lock_file_exists():
            raise UsbackupRuntimeError(f'Backup already running')
        
        # test connection to host
        if not await CmdExec.is_host_reachable(self._context.host):
            raise UsbackupRuntimeError(f'Host" {self._context.host}" is not reachable')
        
        self._logger.info(f'Backup started at {run_time}')
        
        await self._context.ensure_destination()
        
        latest_version = await self._context.get_latest_version()
        version = await self._context.generate_version()
            
        await self._context.create_lock_file()
        self._cleanup.add_job(f'remove_lock_{self._id}', self._context.remove_lock_file)
        
        dest = version.path
        dest_link = latest_version.path if latest_version else None
        error = None
        
        try:
            await self._run_backup_handlers(dest, dest_link)
        except Exception as e:
            self._logger.exception(e)
            self._logger.warning(f'Deleting inconsistent backup version')
            await self._context.remove_version(version)
            error = e
        
        if not error:
            try:
                await self.apply_retention_policy()
            except Exception as e:
                self._logger.exception(f'Failed to apply retention policy. {e}')
                error = e

        await self._cleanup.run_job(f'remove_lock_{self._id}')

        finish_time = datetime.datetime.now()

        elapsed = finish_time - run_time
        elapsed_s = elapsed.total_seconds()

        self._logger.info(f'Backup finished at {finish_time}. Elapsed time: {elapsed_s:.2f} seconds')
        
        return ResultModel(self._context, message=self._log_stream.getvalue(), error=error, elapsed=elapsed)
    
    async def _run_backup_handlers(self, dest: PathModel, dest_link: PathModel = None) -> None:
        for handler_model in self._context.handlers:
            handler_logger = self._logger.getChild(handler_model.handler)
            
            handler = handler_factory('backup', handler_model.handler, handler_model, self._context.host, cleanup=self._cleanup, logger=handler_logger)
           
            handler_dest = dest.join(handler.handler)
            handler_dest_link = None
            
            if dest_link:
                self._logger.info(f'Using "{dest_link}" as dest link for "{handler.handler}" handler')
                handler_dest_link = dest_link.join(handler.handler)
                
            if not await FsAdapter.exists(handler_dest, 'd'):
                self._logger.info(f'Creating handler directory "{handler_dest}"')
                await FsAdapter.mkdir(handler_dest)
            
            self._logger.info(f'Performing backup via "{handler.handler}" handler')
            await handler.backup(handler_dest, handler_dest_link)