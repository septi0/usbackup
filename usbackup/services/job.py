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
from usbackup.services.prune_runner import PruneRunner
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
        self._sources_retention_policy: dict[str, RetentionPolicyModel] = job.sources_retention_policy
        self._concurrency: int = job.concurrency
        self._replication_mode: str = job.replication_mode
        self._pre_run_cmd: list | None = job.pre_run_cmd
        self._post_run_cmd: list | None = job.post_run_cmd

        self._running: bool = False
    
    @property
    def name(self) -> str:
        return self._name
        
    @property
    def is_running(self) -> bool:
        return self._running
    
    async def run(self) -> bool:
        """
        Run the job. Returns True if every source completed successfully.
        """
        self._running = True
        
        try:
            return await self._run()
        finally:
            self._running = False
    
    async def _run(self) -> bool:
        tasks = []
        results = []
        errors = []
        
        run_time = datetime.datetime.now()
        
        self._logger.info(f'{self._type.capitalize()} job "{self._name}"  started at {run_time}')
        
        # cleanups that failed earlier in this process (e.g. a remote that was briefly unreachable) are retried before new work starts
        await self._cleanup.retry_abandoned()
        
        if self._pre_run_cmd:
            self._logger.info(f"Running pre run command")
        
            try:
                await CmdExec.exec(self._pre_run_cmd)
            except Exception as e:
                # the sources may depend on what the pre run command prepares, so they are skipped
                self._logger.exception(f'Pre run command failed, skipping all sources. {e}')
                errors.append(f'Pre run command failed, all sources were skipped: {e}')
        
        if not errors:
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
        
        # runs even after a failed pre run command, since it usually undoes what the pre run command did
        if self._post_run_cmd:
            self._logger.info(f"Running post run command")
            
            try:
                await CmdExec.exec(self._post_run_cmd)
            except Exception as e:
                self._logger.exception(f'Post run command failed. {e}')
                errors.append(f'Post run command failed: {e}')
            
        finish_time = datetime.datetime.now()
 
        elapsed = finish_time - run_time
        elapsed_s = elapsed.total_seconds()
                
        self._logger.info(f'{self._type.capitalize()} job "{self._name}" finished at {finish_time}. Elapsed time: {elapsed_s:.2f} seconds')
        
        # handle reporting
        await self._notifier.notify(results, elapsed=elapsed, errors=errors)
        
        # sources whose task crashed have no result, so they count as failed too
        return not errors and len(results) == len(self._sources) and not any(result.error for result in results)
    
    async def prune(self, *, dry_run: bool = False) -> bool:
        """
        Apply the retention policies to the job sources, without running the job. Returns True if every source was pruned.
        """
        failed = False
        
        for source in self._sources:
            logger = self._logger.getChild(source.name)
            retention_policy = self._sources_retention_policy.get(source.name, self._retention_policy)
            
            if not retention_policy:
                logger.info(f'No retention policy. Nothing to prune')
                continue
            
            context = ContextService(source, self._dest, logger=logger)
            runner = PruneRunner(context, retention_policy, cleanup=self._cleanup, logger=logger)
            
            try:
                await runner.run(dry_run=dry_run)
            except Exception as e:
                logger.exception(f'Failed to prune. {e}')
                failed = True
                continue
            
            if not dry_run:
                self._store_stats(source.name, await self._get_versions_stats(context))
        
        return not failed
    
    async def _semaphore_task_runner(self, source: SourceModel, semaphore: asyncio.Semaphore) -> ResultModel:
        async with semaphore:
            logger = self._logger.getChild(source.name)
            
            log_stream = io.StringIO()
            # bind stream to logger
            stream_handler = logging.StreamHandler(log_stream)
            stream_handler.setFormatter(NoExceptionFormatter('%(asctime)s - %(message)s'))
            
            logger.addHandler(stream_handler)
            
            context = ContextService(source, self._dest, logger=logger)
            # source specific policy replaces the job policy
            retention_policy = self._sources_retention_policy.get(source.name, self._retention_policy)
            
            try:
                if self._type == 'backup':
                    runner = BackupRunner(context, retention_policy, cleanup=self._cleanup, logger=logger)
                    
                    result = await runner.run()
                elif self._type == 'replication':
                    runner = ReplicationRunner(context, retention_policy, mode=self._replication_mode, cleanup=self._cleanup, logger=logger)
                    
                    if not self._replication_src:
                        raise UsBackupRuntimeError(f"Replication source is not set for job {self._name}")
                    
                    replicate_context = ContextService(source, self._replication_src, logger=logger)
                    result = await runner.run(replicate_context)
            except Exception as e:
                self._logger.exception(e)
                result = ResultModel(context, error=e)
            
            # a failed run keeps the version counts of the previous run, since the versions may not even be readable
            versions = {} if result.error else await self._get_versions_stats(context)
            
            # Store only primitives so pickle never depends on third-party class definitions
            self._store_stats(context.name, {
                'date': result.date,
                'elapsed': result.elapsed,
                'error': str(result.error) if result.error else None,
                'dest': str(result.dest),
                **versions,
            })
                
            result.set_message(log_stream.getvalue())
                
            logger.removeHandler(stream_handler)
            log_stream.close()
            
            return result
    
    async def _get_versions_stats(self, context: ContextService) -> dict:
        versions = await context.get_versions()
        
        return {
            'versions': len(versions),
            'oldest': versions[0].version if versions else None,
            'newest': versions[-1].version if versions else None,
        }
    
    def _store_stats(self, source: str, values: dict) -> None:
        merge = lambda entries, key: {**entries, key: {**entries.get(key, {}), **values}}
        
        # updated atomically so concurrent processes never overwrite each other's entries
        if self._type == 'backup':
            self._datastore.update('backups', lambda backups: merge(backups, source), {})
        else:
            # a source is usually replicated to several storages, so replications are kept per destination storage
            self._datastore.update('replications', lambda replications: {**replications, self._dest.name: merge(replications.get(self._dest.name, {}), source)}, {})
    
    def is_job_due(self, now: datetime.datetime | None = None) -> bool:
        cron_schedule = self._schedule
        
        self._logger.debug(f"Checking if job {self._name} is due with schedule {cron_schedule}")
        
        if not cron_schedule:
            self._logger.debug(f"Job {self._name} has no cron schedule, running job")
            return True
        
        schedule = cron_schedule.split()
        
        minute, hour, day, month, weekday = schedule
        now = now or datetime.datetime.now()
        
        if not self._is_cron_field_due(minute, now.minute, 0):
            return False
        
        if not self._is_cron_field_due(hour, now.hour, 0):
            return False
        
        if not self._is_cron_field_due(month, now.month, 1):
            return False
        
        day_due = self._is_cron_field_due(day, now.day, 1)
        
        # cron counts weekdays from sunday, which can be written as 0 or 7
        cron_weekday = (now.weekday() + 1) % 7
        weekday_due = self._is_cron_field_due(weekday, cron_weekday, 0) or (cron_weekday == 0 and self._is_cron_field_due(weekday, 7, 0))
        
        # like cron, a job restricted by both day fields runs when either of them matches
        if day != '*' and weekday != '*':
            if not (day_due or weekday_due):
                return False
        elif not (day_due and weekday_due):
            return False
        
        self._logger.debug(f"Job {self._name} is due with schedule {cron_schedule}")
        
        return True
    
    def _is_cron_field_due(self, field: str, value: int, minimum: int) -> bool:
        # a list matches when any of its items matches
        if ',' in field:
            return any(self._is_cron_field_due(item, value, minimum) for item in field.split(','))
        
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
            
            # steps count from the first value of the field, e.g. */2 on days matches 1, 3, 5...
            if (value - minimum) % step == 0:
                return True
            else:
                return False
        
        if field.isdigit():
            if int(field) == value:
                return True
            else:
                return False

        return False