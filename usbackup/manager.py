import os
import logging
import signal
import math
import datetime
import asyncio
from usbackup.cleanup_queue import CleanupQueue
from usbackup.remote import Remote
from usbackup.backup_config_parser import UsBackupConfigParser
from usbackup.backup_job import UsBackupJob
from usbackup.backup_host import UsBackupHost
from usbackup.backup_notifier import UsbackupNotifier
from usbackup.exceptions import UsbackupRuntimeError, GracefulExit
from usbackup.backup_handlers import dynamic_loader as backup_handler_loader
from usbackup.notification_handlers import dynamic_loader as notification_handler_loader

__all__ = ['UsBackupManager']

class UsBackupManager:
    def __init__(self, *, config_file: str = None, log_file: str = None, log_level: str = None) -> None:
        self._pid_filepath: str = self._gen_pid_filepath()
        
        if not config_file:
            config_file = self._get_default_config_file()

        self._config: UsBackupConfigParser = UsBackupConfigParser(file=config_file)
        self._logger: logging.Logger = self._logger_factory(log_file, log_level)
        
        self._cleanup: CleanupQueue = CleanupQueue()
        self._notifier: UsbackupNotifier = self._notifier_factory(self._config.get('notification'))

    def backup(self, daemon: bool = False, config: dict = {}) -> None:
        return self._run_main(self._run_backup, daemon=daemon, config=config)
    
    def _get_default_config_file(self) -> str:
        config_files = [
            '/etc/usbackup/config.yml',
            '/etc/opt/usbackup/config.yml',
            os.path.expanduser('~/.config/usbackup/config.yml'),
        ]
            
        file_to_load = None
        
        for config_file in config_files:
            if os.path.isfile(config_file):
                file_to_load = config_file
                break
       
        if not file_to_load:
            raise UsbackupRuntimeError("No default config file found")
        
        return file_to_load
        
    def _gen_pid_filepath(self) -> str:
        if os.getuid() == 0:
            return '/var/run/usbackup.pid'
        else:
            return os.path.expanduser('~/.usbackup.pid')
    
    def _logger_factory(self, log_file: str, log_level: str) -> logging.Logger:
        levels = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }

        format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

        if not log_level in levels:
            log_level = "INFO"

        logger = logging.getLogger()
        logger.setLevel(levels[log_level])

        if log_file:
            handler = logging.FileHandler(log_file)
        else:
            handler = logging.StreamHandler()

        handler.setLevel(levels[log_level])
        handler.setFormatter(logging.Formatter(format))

        logger.addHandler(handler)

        return logger
    
    def _notifier_factory(self, config: list) -> UsbackupNotifier:
        if not config:
            return UsbackupNotifier([], logger=self._logger)

        notifier_logger = self._logger.getChild('notifier')
        handlers = []

        for notifier_config in config:
            handler_logger = notifier_logger.getChild(notifier_config.get('handler'))
            handler_class = notification_handler_loader(notifier_config.get('handler'))

            handlers.append(handler_class(notifier_config, logger=handler_logger))

        return UsbackupNotifier(handlers, logger=notifier_logger)
    
    def _sigterm_handler(self) -> None:
        raise GracefulExit
    
    def _run_main(self, main_task, *args, **kwargs) -> any:
        output = None

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop.add_signal_handler(signal.SIGTERM, self._sigterm_handler)
        loop.add_signal_handler(signal.SIGINT, self._sigterm_handler)
        loop.add_signal_handler(signal.SIGQUIT, self._sigterm_handler)

        try:
            output = loop.run_until_complete(main_task(*args, **kwargs))
        except (GracefulExit) as e:
            self._logger.info("Received termination signal")
        except (Exception) as e:
            self._logger.exception(e, exc_info=True)
        finally:
            try:
                # run cleanup jobs before exiting
                self._logger.info("Running cleanup jobs")
                loop.run_until_complete(self._cleanup.run_jobs())
                
                self._cancel_tasks(loop)
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                asyncio.set_event_loop(None)
                loop.close()

        return output
    
    def _cancel_tasks(self, loop: asyncio.AbstractEventLoop) -> None:
        tasks = asyncio.all_tasks(loop=loop)

        if not tasks:
            return

        for task in tasks:
            task.cancel()

        loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

        for task in tasks:
            if task.cancelled():
                continue

            if task.exception() is not None:
                loop.call_exception_handler({
                    'message': 'Unhandled exception during task cancellation',
                    'exception': task.exception(),
                    'task': task,
                })

    async def _run_backup(self, daemon: bool = False, config: dict = {}) -> None:
        if not daemon:
            config['name'] = 'manual'
            if config.get('retention-policy'):
                # convert retention_policy to dict
                config['retention-policy'] = config['retention-policy'].split(',')
                config['retention-policy'] = {k.strip(): int(v) for k, v in (x.split('=') for x in config['retention-policy'])}
                
            config = UsBackupConfigParser(config=config, section='jobs')
                
            backup_job = self._backup_job_factory(config)
            
            await backup_job.run()
            return
        
        jobs_configs = self._config.get('jobs')
        
        if not jobs_configs:
            self._logger.error("No jobs found in config")
            return
        
        backup_jobs = []
        
        for job_config in jobs_configs:
            backup_jobs.append(self._backup_job_factory(job_config))
        
        # run as service
        pid = str(os.getpid())

        if os.path.isfile(self._pid_filepath):
            self._logger.error("Service is already running")
            return

        with open(self._pid_filepath, 'w') as f:
            f.write(pid)

        self._cleanup.add_job('service_pid', os.remove, self._pid_filepath)
        self._cleanup.add_job('shutdown_service', self._logger.info, 'Shutting down service')

        self._logger.info(f'Starting service with pid {pid}')

        service_run_time = datetime.datetime.now().replace(second=0, microsecond=0)

        # run every minute
        while True:
            asyncio.create_task(self._run_due_jobs(backup_jobs))

            # calculate the next scheduled run_time for the service
            service_run_time += datetime.timedelta(minutes=1)

            # calculate the time left until the next run_time
            time_left = (service_run_time - datetime.datetime.now()).total_seconds()

            # we are behind schedule if time_left is negative
            if time_left < 0:
                self._logger.fatal(f'Behind schedule by {abs(int(time_left / 60)) + 1} m')
                break

            self._logger.debug(f'Next run in {time_left} s')

            await asyncio.sleep(time_left)
    
    def _backup_job_factory(self, job_config: dict) -> UsBackupJob:
        hosts_config = self._config.get('hosts')
        
        if job_config.get('limit'):
            hosts_config = [host for host in hosts_config if host.get('name') in job_config['limit']]
        
        if job_config.get('exclude'):
            hosts_config = [host for host in hosts_config if host.get('name') not in job_config['exclude']]
            
        if not hosts_config:
            raise UsbackupRuntimeError("No hosts left to backup after limit/exclude filters")
            
        hosts = []
        
        for host in hosts_config:                
            hosts.append(self._backup_host_factory(host))
    
        dest = job_config.get('dest')
            
        if not dest:
            raise UsbackupRuntimeError("No destination found for job")
            
        logger = self._logger.getChild(job_config.get('name'))
            
        return UsBackupJob(hosts, dest, job_config, notifier=self._notifier, logger=logger)
    
    def _backup_host_factory(self, host_config: dict) -> UsBackupHost:
        host_name = host_config.get('name')
        try:
            remote = Remote(host_config.get('host'), default_user='root', default_port=22)
        except ValueError:
            raise UsbackupRuntimeError(f'Invalid host {host_config.get("host")}')
        
        host_logger = self._logger.getChild(host_name)
        handlers = []
        
        for backup_config in host_config.get('backup'):
            handler_logger = host_logger.getChild(backup_config.get('handler'))
            handler_class = backup_handler_loader(backup_config.get('handler'))
            
            handlers.append(handler_class(remote, backup_config, logger=handler_logger))
        
        return UsBackupHost(host_name, remote, handlers, cleanup=self._cleanup, logger=host_logger)
    
    async def _run_due_jobs(self, backup_jobs: list[UsBackupJob]) -> None:
        tasks = []
            
        for job in backup_jobs:
            if job.is_job_due():
                self._logger.info(f"Job {job.name} is due. Running it")
                tasks.append(asyncio.create_task(job.run(), name=job.name))
        
        if not tasks:
            self._logger.debug('No jobs due')
            return
        
        self._logger.info(f"Running {len(tasks)} jobs")
        
        if len(tasks) > 1:
            self._logger.warning('More than one job run concurrently. Performance may be degraded')
                
        await asyncio.gather(*tasks, return_exceptions=True)
        
        for task in tasks:
            if isinstance(task.exception(), Exception):
                self._logger.exception(task.exception(), exc_info=True)