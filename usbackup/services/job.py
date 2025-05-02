import logging
import asyncio
import datetime
import shlex
import usbackup.libraries.cmd_exec as cmd_exec
from usbackup.models.job import UsBackupJobModel
from usbackup.models.retention_policy import UsBackupRetentionPolicyModel
from usbackup.models.result import UsBackupResultModel
from usbackup.services.host import UsBackupHost
from usbackup.services.notifier import UsbackupNotifier
from usbackup.exceptions import UsbackupRuntimeError

__all__ = ['UsBackupJob']


class UsBackupJob:
    def __init__(self, model: UsBackupJobModel, *, hosts: list[UsBackupHost], notifier: UsbackupNotifier, logger: logging.Logger):
        self._name: str = model.name
        self._type: str = model.type
        self._schedule: str = model.schedule
        self._retention_policy: UsBackupRetentionPolicyModel = model.retention_policy
        self._notification_policy: str = model.notification_policy
        self._concurrency: int = model.concurrency
        self._pre_run_cmd: list = shlex.split(model.pre_run_cmd) if model.pre_run_cmd else []
        self._post_run_cmd: list = shlex.split(model.post_run_cmd) if model.post_run_cmd else []
        
        self._hosts: list[UsBackupHost] = hosts
        
        self._notifier: UsbackupNotifier = notifier
        self._logger: logging.Logger = logger

    @property
    def name(self) -> str:
        return self._name
    
    @property
    def hosts(self) -> list[UsBackupHost]:
        return self._hosts
        
    async def run(self) -> None:
        tasks = []
        results = []
        
        if self._pre_run_cmd:
            self._logger.info(f"Running pre run command")
            await cmd_exec.exec_cmd(self._pre_run_cmd)
        
        semaphore = asyncio.Semaphore((self._concurrency))
        
        for host in self._hosts:
            tasks.append(asyncio.create_task(self._semaphore_worker(host, semaphore=semaphore), name=host.name))
                
        # wait for all tasks to finish
        await asyncio.gather(*tasks, return_exceptions=True)
        
        for task in tasks:
            if isinstance(task.exception(), Exception):
                self._logger.exception(task.exception(), exc_info=True)
                results.append(UsBackupResultModel(task.get_name(), error=task.exception()))
            else:
                results.append(task.result())
                
        if self._post_run_cmd:
            self._logger.info(f"Running post run command")
            await cmd_exec.exec_cmd(self._post_run_cmd)
                
        self._logger.info(f"Backup finished for host {str(host)}")
        
        # handle reporting
        await self._notifier.notify(self._name, self._type, results, notification_policy=self._notification_policy)
    
    async def _semaphore_worker(self, host: UsBackupHost, *, semaphore: asyncio.Semaphore) -> UsBackupResultModel:
        async with semaphore:
            self._logger.info(f"Running backup for host {host.name}")
            
            result = await host.backup(self._retention_policy)
            
            
            
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