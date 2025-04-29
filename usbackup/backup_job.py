import logging
import asyncio
import datetime
import os
import shlex
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_host import UsBackupHost
from usbackup.backup_result import UsbackupResult
from usbackup.backup_notifier import UsbackupNotifier
from usbackup.exceptions import UsbackupRuntimeError

__all__ = ['UsBackupJob']

class UsBackupJob:
    def __init__(self, hosts: list[UsBackupHost], dest: str, config: dict, *, notifier: UsbackupNotifier, logger: logging.Logger):
        self._hosts: list[UsBackupHost] = hosts
        self._dest: str = dest
        self._config: dict = config
        
        self._name: str = config.get('name')
        
        self._notifier: UsbackupNotifier = notifier
        self._logger: logging.Logger = logger

    @property
    def name(self) -> str:
        return self._name
    
    @property
    def hosts(self) -> list[UsBackupHost]:
        return self._hosts
    
    @property
    def dest(self) -> str:
        return self._dest
        
    async def run(self) -> None:
        tasks = []
        results = []
        
        if self._config.get('pre-backup-cmd'):
            self._logger.info(f"Running pre backup command")
            await cmd_exec.exec_cmd(shlex.split(self._config['pre-backup-cmd']))
        
        semaphore = asyncio.Semaphore((self._config.get('concurrency')))
        
        for host in self._hosts:
            tasks.append(asyncio.create_task(self._semaphore_worker(host, semaphore=semaphore), name=host.name))
                
        # wait for all tasks to finish
        await asyncio.gather(*tasks, return_exceptions=True)
        
        for task in tasks:
            if isinstance(task.exception(), Exception):
                self._logger.exception(task.exception(), exc_info=True)
                results.append(UsbackupResult(task.get_name(), error=task.exception()))
            else:
                results.append(task.result())
                
        if self._config.get('post-backup-cmd'):
            self._logger.info(f"Running post backup command")
            await cmd_exec.exec_cmd(shlex.split(self._config['post-backup-cmd']))
                
        self._logger.info(f"Backup finished for host {str(host)}")
        
        # handle reporting
        await self._notifier.notify(self._name, results, notification_policy=self._config.get('notification-policy'))
    
    async def _semaphore_worker(self, host: UsBackupHost, *, semaphore: asyncio.Semaphore) -> UsbackupResult:
        async with semaphore:
            self._logger.info(f"Running backup for host {host.name}")
            
            dest = os.path.join(self._dest, host.name)
            return await host.backup(dest, self._config.get('retention-policy'))
    
    def is_job_due(self) -> bool:
        cron_schedule = self._config.get('schedule')
        
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