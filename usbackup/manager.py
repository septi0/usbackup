import os
import logging
import signal
import yaml
import datetime
import asyncio
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.models.usbackup import UsBackupModel
from usbackup.models.job import UsBackupJobModel
from usbackup.models.storage import UsBackupStorageModel
from usbackup.models.source import UsBackupSourceModel
from usbackup.models.handler_base import UsBackupHandlerBaseModel
from usbackup.services.job import UsBackupJob
from usbackup.services.context import UsBackupContext
from usbackup.services.runner import UsBackupRunner
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
    
    def _notifier_factory(self, handler_models: list[UsBackupHandlerBaseModel]) -> UsbackupNotifier:
        if not handler_models:
            return None
        
        notifier_logger = self._logger.getChild('notifier')
        handlers = []

        for handler_model in handler_models:
            handler_logger = notifier_logger.getChild(handler_model.handler)

            handlers.append(handler_factory('notification', handler_model.handler, handler_model, logger=handler_logger))

        return UsbackupNotifier(handlers, logger=notifier_logger)
    
    def _job_factory(self, model: UsBackupJobModel) -> UsBackupJob:
        source_models = self._model.sources
        
        # filter source models
        if model.limit:
            source_models = [source for source in source_models if source.name in model.limit]
        
        if model.exclude:
            source_models = [source for source in source_models if source.name not in model.exclude]
            
        if not source_models:
            raise UsbackupRuntimeError("No sources left to backup after limit/exclude filters")
        
        # find storage by job_model.dest
        storage_model = next((storage for storage in self._model.storages if storage.name == model.dest), None)
        
        if not storage_model:
            raise UsbackupRuntimeError(f'Storage "{model.dest}" not found')
        
        contexts = []
        
        for source_model in source_models:                
            contexts.append(self._context_factory(source_model, storage_model))

        return UsBackupJob(model, contexts, runner_factory=self._runner_factory, notifier=self._notifier, logger=self._logger)
    
    def _context_factory(self, source_model: UsBackupSourceModel, storage_model: UsBackupStorageModel) -> UsBackupContext:
        source_name = source_model.name
        
        source_logger = self._logger.getChild(source_name)
        
        destination = os.path.join(storage_model.path, source_name)
        
        return UsBackupContext(source_model, destination, logger=source_logger)
    
    def _runner_factory(self, context: UsBackupContext, *, logger: logging.Logger) -> UsBackupRunner:
        return UsBackupRunner(context, cleanup=self._cleanup, logger=logger)
    
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
                
            job = self._job_factory(job_model)
            
            await job.run()
            return
        
        job_models = self._model.jobs
        
        if not job_models:
            self._logger.error("No jobs found in config")
            return
        
        jobs = []
        
        for job_model in job_models:
            jobs.append(self._job_factory(job_model))
        
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
            asyncio.create_task(self._run_due_jobs(jobs))

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
    
    async def _run_due_jobs(self, jobs: list[UsBackupJob]) -> None:
        tasks = []
            
        for job in jobs:
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