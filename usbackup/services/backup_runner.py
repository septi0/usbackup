import os
import logging
import datetime
import uuid
import io
import usbackup.libraries.cmd_exec as cmd_exec
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.models.version import BackupVersionModel
from usbackup.models.retention_policy import RetentionPolicyModel
from usbackup.models.result import ResultModel
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
        if not await cmd_exec.is_host_reachable(self._context.host):
            raise UsbackupRuntimeError(f'Host" {self._context.host}" is not reachable')
        
        self._logger.info(f'Backup started at {run_time}')
            
        await self._context.create_lock_file()
        self._cleanup.add_job(f'remove_lock_{self._id}', self._context.remove_lock_file)
    
        version = await self._context.generate_version()
        latest_version = self._context.get_latest_version()
        
        error = None
        
        try:
            await self._run_backup_handlers(version, latest_version)
        except Exception as e:
            self._logger.exception(e, exc_info=True)
            self._logger.warning(f'Deleting inconsistent backup version')
            self._context.remove_version(version)
            
            error = e
        
        if not error:
            await self.apply_retention_policy()

        await self._cleanup.run_job(f'remove_lock_{self._id}')

        finish_time = datetime.datetime.now()

        elapsed = finish_time - run_time
        elapsed_s = elapsed.total_seconds()

        self._logger.info(f'Backup finished at {finish_time}. Elapsed time: {elapsed_s:.2f} seconds')
        
        return ResultModel(self._context, message=self._log_stream.getvalue(), error=error, elapsed=elapsed)
    
    async def _run_backup_handlers(self, version: BackupVersionModel, latest_version: BackupVersionModel) -> None:
        for handler_model in self._context.handlers:
            handler_logger = self._logger.getChild(handler_model.handler)
            
            handler = handler_factory('backup', handler_model.handler, handler_model, self._context.host, cleanup=self._cleanup, logger=handler_logger)
           
            handler_dest = os.path.join(version.path, handler.handler)
            handler_dest_link = None
            
            if latest_version:
                self._logger.info(f'Using "{latest_version.path}" as dest link for "{handler.handler}" handler')
                handler_dest_link = os.path.join(latest_version.path, handler.handler)
                
            if not os.path.isdir(handler_dest):
                self._logger.info(f'Creating handler directory "{handler_dest}"')
                await cmd_exec.mkdir(handler_dest)
            
            self._logger.info(f'Performing backup via "{handler.handler}" handler')
            await handler.backup(handler_dest, handler_dest_link)