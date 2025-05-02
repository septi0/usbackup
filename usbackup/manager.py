import os
import logging
import signal
import yaml
import datetime
import asyncio
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.models.usbackup import UsBackupModel
from usbackup.models.job import UsBackupJobModel
from usbackup.models.host import UsBackupHostModel
from usbackup.models.handler_base import UsBackupHandlerBaseModel
from usbackup.services.host import UsBackupHost
from usbackup.services.job import UsBackupJob
from usbackup.services.notifier import UsbackupNotifier
from usbackup.exceptions import UsbackupRuntimeError, GracefulExit
from usbackup.handlers import handler_factory

__all__ = ['UsBackupManager']

class UsBackupManager:
    def __init__(self, *, log_file: str = None, log_level: str = None, config_file: str = None, ) -> None:
        self._pid_filepath: str = self._gen_pid_filepath()

        self._logger: logging.Logger = self._logger_factory(log_file, log_level)
        self._model: UsBackupModel = UsBackupModel(**self._load_config(config_file))
            
        self._cleanup: CleanupQueue = CleanupQueue()
        self._notifier: UsbackupNotifier = self._notifier_factory(self._model.notifiers)

    def backup(self, daemon: bool = False, config: dict = {}) -> None:
        return self._run_main(self._run_backup, daemon=daemon, config=config)
    
    def _load_config(self, file: str = None) -> str:
        config_files = [
            '/etc/usbackup/config.yml',
            '/etc/opt/usbackup/config.yml',
            os.path.expanduser('~/.config/usbackup/config.yml'),
        ]
        
        if file:
            config_files = [file]
            
        file_to_load = None
        
        for config_file in config_files:
            if os.path.isfile(config_file):
                file_to_load = config_file
                break
       
        if not file_to_load:
            raise UsbackupRuntimeError("No config file found")
        
        with open(file_to_load, 'r') as f:
            try:
                config = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise UsbackupRuntimeError(f"Failed to parse config file: {e}")
            
        return config
        
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
    
    def _notifier_factory(self, handlers_models: list[UsBackupHandlerBaseModel]) -> UsbackupNotifier:
        if not handlers_models:
            return None
        
        notifier_logger = self._logger.getChild('notifier')
        handlers = []

        for handler_model in handlers_models:
            handler_logger = notifier_logger.getChild(handler_model.handler)
            handler_class = handler_factory('notification', name=handler_model.handler, entity='handler')

            handlers.append(handler_class(handler_model, logger=handler_logger))

        return UsbackupNotifier(handlers, logger=notifier_logger)
    
    def _backup_job_factory(self, job_model: UsBackupJobModel) -> UsBackupJob:
        host_models = self._model.hosts
        
        # filter host models
        if job_model.limit:
            host_models = [host for host in host_models if host.get('name') in job_model.limit]
        
        if job_model.exclude:
            host_models = [host for host in host_models if host.get('name') not in job_model.exclude]
            
        if not host_models:
            raise UsbackupRuntimeError("No hosts left to backup after limit/exclude filters")
            
        hosts = []
        
        for host_model in host_models:                
            hosts.append(self._backup_host_factory(host_model))
            
        logger = self._logger.getChild(job_model.name)
            
        return UsBackupJob(job_model, hosts=hosts, notifier=self._notifier, logger=logger)
    
    def _backup_host_factory(self, host_model: UsBackupHostModel) -> UsBackupHost:
        host_name = host_model.name
        
        host_logger = self._logger.getChild(host_name)
        
        return UsBackupHost(host_model, cleanup=self._cleanup, logger=host_logger)
    
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
            config['type'] = 'backup'
            if config.get('retention_policy'):
                # convert retention_policy to dict
                config['retention_policy'] = config['retention_policy'].split(',')
                config['retention_policy'] = {k.strip(): int(v) for k, v in (x.split('=') for x in config['retention_policy'])}
                
            job_model = UsBackupJobModel(**config)
                
            backup_job = self._backup_job_factory(job_model)
            
            await backup_job.run()
            return
        
        jobs_models = self._model.jobs
        
        if not jobs_models:
            self._logger.error("No jobs found in config")
            return
        
        backup_jobs = []
        
        for job_config in jobs_models:
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