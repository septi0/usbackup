import logging
import asyncio
import datetime
import shlex
import io
import usbackup.libraries.cmd_exec as cmd_exec
from usbackup.models.job import UsBackupJobModel
from usbackup.models.retention_policy import UsBackupRetentionPolicyModel
from usbackup.models.result import UsBackupResultModel
from usbackup.services.context import UsBackupContext
from usbackup.services.notifier import UsbackupNotifier
from usbackup.exceptions import UsbackupRuntimeError

__all__ = ['UsBackupJob']

class UsBackupJob:
    def __init__(self, job: UsBackupJobModel, contexts: list[UsBackupContext], *, runner_factory: object, notifier: UsbackupNotifier, logger: logging.Logger):
        self._contexts: list[UsBackupContext] = contexts
        
        self._runner_factory: object = runner_factory
        self._notifier: UsbackupNotifier = notifier
        self._logger: logging.Logger = logger
        
        self._name: str = job.name
        self._type: str = job.type
        self._schedule: str = job.schedule
        self._retention_policy: UsBackupRetentionPolicyModel = job.retention_policy
        self._notification_policy: str = job.notification_policy
        self._concurrency: int = job.concurrency
        self._pre_run_cmd: list = shlex.split(job.pre_run_cmd) if job.pre_run_cmd else []
        self._post_run_cmd: list = shlex.split(job.post_run_cmd) if job.post_run_cmd else []

    @property
    def name(self) -> str:
        return self._name
        
    async def run(self) -> None:
        tasks = []
        results = []
        
        self._logger.info(f'Starting {self._type} job "{self._name}"')
        
        if self._pre_run_cmd:
            self._logger.info(f"Running pre run command")
            await cmd_exec.exec_cmd(self._pre_run_cmd)
        
        semaphore = asyncio.Semaphore((self._concurrency))
        
        for context in self._contexts:
            tasks.append(asyncio.create_task(self._semaphore_task_runner(context, semaphore), name=context.source.name))
                
        # wait for all tasks to finish
        await asyncio.gather(*tasks, return_exceptions=True)
        
        for task in tasks:
            if isinstance(task.exception(), Exception):
                try: raise task.exception()
                except Exception as e: self._logger.exception(e, exc_info=True)
                results.append(UsBackupResultModel(context, error=e))
            else:
                results.append(task.result())
                
        if self._post_run_cmd:
            self._logger.info(f"Running post run command")
            await cmd_exec.exec_cmd(self._post_run_cmd)
                
        self._logger.info(f'{self._type} job "{self._name}" finished')
        
        # handle reporting
        await self._notifier.notify(self._name, self._type, results, notification_policy=self._notification_policy)
    
    async def _semaphore_task_runner(self, context: UsBackupContext, semaphore: asyncio.Semaphore) -> UsBackupResultModel:
        async with semaphore:
            log_stream = io.StringIO()
            logger = self._logger.getChild(context.source.name)
            
            stream_handler = logging.StreamHandler(log_stream)
            stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            logger.addHandler(stream_handler)
            
            logger.info(f"Running {self._type} task for {context.source.name}")
            
            runner = self._runner_factory(context, logger=logger)
            
            run_time = datetime.datetime.now()
            
            logger.info(f'{self._type} task started at {run_time}')
            
            try:
                elapsed = await runner.backup(self._retention_policy)
            except Exception as e:
                logger.exception(e, exc_info=True)
                return UsBackupResultModel(context, message=log_stream.getvalue(), error=e)

            finish_time = datetime.datetime.now()

            elapsed_time = finish_time - run_time
            elapsed_time_s = elapsed_time.total_seconds()

            logger.info(f'{self._type} task at {finish_time}. Elapsed time: {elapsed_time_s:.2f} seconds')

            return UsBackupResultModel(context, message=log_stream.getvalue(), elapsed_time=elapsed)
    
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