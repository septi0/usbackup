import logging
import asyncio
import datetime
import io
from usbackup.libraries.cmd_exec import CmdExec
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.libraries.datastore import Datastore
from usbackup.models.job import JobModel
from usbackup.models.retention_policy import RetentionPolicyModel
from usbackup.models.result import ResultModel
from usbackup.models.storage import StorageModel
from usbackup.models.source import SourceModel
from usbackup.services.context import ContextService
from usbackup.services.backup_runner import BackupRunner
from usbackup.services.replication_runner import ReplicationRunner
from usbackup.services.notifier import NotifierService
from usbackup.exceptions import UsBackupRuntimeError
from usbackup.utils.logging import NoExceptionFormatter

__all__ = ['JobService']

class JobService:
    def __init__(self, job: JobModel, sources: list[SourceModel], replication_src: StorageModel | None, dest: StorageModel, *, cleanup: CleanupQueue, datastore: Datastore, notifier: NotifierService, logger: logging.Logger):
        self._sources: list[SourceModel] = sources
        self._replication_src: StorageModel | None = replication_src
        self._dest: StorageModel = dest
        
        self._cleanup: CleanupQueue = cleanup
        self._datastore: Datastore = datastore
        self._notifier: NotifierService = notifier
        self._logger: logging.Logger = logger
        
        self._name: str = job.name
        self._type: str = job.type
        self._schedule: str = job.schedule
        self._retention_policy: RetentionPolicyModel | None = job.retention_policy
        self._concurrency: int = job.concurrency
        self._pre_run_cmd: list | None = job.pre_run_cmd
        self._post_run_cmd: list | None = job.post_run_cmd

    @property
    def name(self) -> str:
        return self._name
        
    async def run(self) -> None:
        tasks = []
        results = []
        
        run_time = datetime.datetime.now()
        
        self._logger.info(f'{self._type.capitalize()} job "{self._name}"  started at {run_time}')
        
        if self._pre_run_cmd:
            self._logger.info(f"Running pre run command")
            await CmdExec.exec(self._pre_run_cmd)
        
        semaphore = asyncio.Semaphore((self._concurrency))
        
        for source in self._sources:
            tasks.append(asyncio.create_task(self._semaphore_task_runner(source, semaphore), name=source.name))
                
        # wait for all tasks to finish
        await asyncio.gather(*tasks, return_exceptions=True)
        
        for task in tasks:
            if isinstance(task.exception(), Exception):
                try: raise task.exception()
                except Exception as e: self._logger.exception(e)
            else:
                results.append(task.result())
                
        if self._post_run_cmd:
            self._logger.info(f"Running post run command")
            await CmdExec.exec(self._post_run_cmd)
            
        finish_time = datetime.datetime.now()
 
        elapsed = finish_time - run_time
        elapsed_s = elapsed.total_seconds()
                
        self._logger.info(f'{self._type.capitalize()} job "{self._name}" finished at {finish_time}. Elapsed time: {elapsed_s:.2f} seconds')
        
        # handle reporting
        await self._notifier.notify(results, elapsed=elapsed)
    
    async def _semaphore_task_runner(self, source: SourceModel, semaphore: asyncio.Semaphore) -> ResultModel:
        async with semaphore:
            logger = self._logger.getChild(source.name)
            
            log_stream = io.StringIO()
            # bind stream to logger
            stream_handler = logging.StreamHandler(log_stream)
            stream_handler.setFormatter(NoExceptionFormatter('%(asctime)s - %(message)s'))
            
            logger.addHandler(stream_handler)
            
            context = ContextService(source, self._dest, logger=logger)
            
            try:
                if self._type == 'backup':
                    runner = BackupRunner(context, self._retention_policy, cleanup=self._cleanup, logger=logger)
                    
                    result = await runner.run()
                elif self._type == 'replication':
                    runner = ReplicationRunner(context, self._retention_policy, cleanup=self._cleanup, logger=logger)
                    
                    if not self._replication_src:
                        raise UsBackupRuntimeError(f"Replication source is not set for job {self._name}")
                    
                    replicate_context = ContextService(source, self._replication_src, logger=logger)
                    result = await runner.run(replicate_context)
            except Exception as e:
                self._logger.exception(e)
                result = ResultModel(context, error=e)
            
            if self._type == 'backup':
                backups = self._datastore.get('backups', {})
                backups[context.name] = result
                
                self._datastore.set('backups', backups)
                
            result.set_message(log_stream.getvalue())
                
            logger.removeHandler(stream_handler)
            log_stream.close()
            
            return result
    
    def is_job_due(self) -> bool:
        cron_schedule = self._schedule
        
        self._logger.debug(f"Checking if job {self._name} is due with schedule {cron_schedule}")
        
        if not cron_schedule:
            self._logger.debug(f"Job {self._name} has no cron schedule, running job")
            return True
        
        schedule = cron_schedule.split()
        
        minute, hour, day, month, weekday = schedule
        now = datetime.datetime.now()
        
        if not self._is_cron_field_due(minute, now.minute):
            return False
        
        if not self._is_cron_field_due(hour, now.hour):
            return False
        
        if not self._is_cron_field_due(day, now.day):
            return False
        
        if not self._is_cron_field_due(month, now.month):
            return False
        
        if not self._is_cron_field_due(weekday, now.weekday()):
            return False
        
        self._logger.debug(f"Job {self._name} is due with schedule {cron_schedule}")
        
        return True
    
    def _is_cron_field_due(self, field: str, value: int) -> bool:
        if field == '*':
            return True
        
        if '-' in field:
            start, end = field.split('-')
            start = int(start)
            end = int(end)
            
            if start <= value <= end:
                return True
            else:
                return False
        
        if '/' in field:
            step = int(field.split('/')[1])
            
            if value % step == 0:
                return True
            else:
                return False
        
        if field.isdigit():
            if int(field) == value:
                return True
            else:
                return False

        return False