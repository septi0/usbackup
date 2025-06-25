import os
import logging
import signal
import yaml
import datetime
import asyncio
import json
from logging.handlers import TimedRotatingFileHandler
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.libraries.datastore import Datastore
from usbackup.models.usbackup import UsBackupModel
from usbackup.models.job import JobModel
from usbackup.models.handler_base import HandlerBaseModel
from usbackup.services.job import JobService
from usbackup.services.notifier import NotifierService
from usbackup.exceptions import UsBackupRuntimeError, GracefulExit
from typing import Any

__all__ = ['UsBackupManager']

class UsBackupManager:
    def __init__(self, *, log_file: str | None = None, log_level: str | None = None, config_file: str | None = None, alt_job: dict | None = None) -> None:
        self._pid_filepath: str = self._get_pid_filepath()

        self._logger: logging.Logger = self._logger_factory(log_file, log_level)
        self._model: UsBackupModel = UsBackupModel(**self._load_config(file=config_file, alt_job=alt_job))
        self._cleanup: CleanupQueue = CleanupQueue()
        self._datastore: Datastore = Datastore(self._get_datastore_filepath())

    def run_once(self) -> None:
        return self._run_main(self._do_run_once)
    
    def run_forever(self) -> None:
        return self._run_main(self._do_run_forever)
    
    def stats(self, format: str) -> None:
        return self._run_main(self._get_stats, format=format)
    
    def _load_config(self, *, file: str | None = None, alt_job: dict | None = None) -> dict:
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
            raise UsBackupRuntimeError("No config file found")
        
        with open(file_to_load, 'r') as f:
            try:
                config = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise UsBackupRuntimeError(f"Failed to parse config file: {e}")
            
        if alt_job:
            # convert retention_policy to dict
            if alt_job.get('retention_policy'):
                alt_job['retention_policy'] = alt_job['retention_policy'].split(',')
                alt_job['retention_policy'] = {k.strip(): int(v) for k, v in (x.split('=') for x in alt_job['retention_policy'])}
                
            config['jobs'] = [alt_job]
            
        return config
        
    def _get_pid_filepath(self) -> str:
        if os.getuid() == 0:
            return '/var/run/usbackup.pid'
        else:
            return os.path.expanduser('~/.usbackup.pid')
        
    def _get_datastore_filepath(self) -> str:
        if os.getuid() == 0:
            filepath = '/var/opt/usbackup/usbackup.db'
        else:
            filepath = os.path.expanduser('~/.usbackup/usbackup.db')
            
        directory = os.path.dirname(filepath)
        
        if not os.path.exists(directory):
            os.makedirs(directory)
            
        return filepath
    
    def _logger_factory(self, log_file: str | None, log_level: str | None) -> logging.Logger:
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
            directory = os.path.dirname(log_file)
            
            if not os.path.exists(directory):
                os.makedirs(directory)
            
            handler = TimedRotatingFileHandler(log_file, when="midnight", backupCount=4)
        else:
            handler = logging.StreamHandler()

        handler.setLevel(levels[log_level])
        handler.setFormatter(logging.Formatter(format))

        logger.addHandler(handler)

        return logger
    
    def _notifier_factory(self, job_model: JobModel, handler_models: list[HandlerBaseModel]) -> NotifierService:
        notifier_logger = self._logger.getChild('notifier')

        return NotifierService(job_model, handler_models, logger=notifier_logger)
    
    def _job_factory(self, model: JobModel) -> JobService:
        source_models = self._model.sources
        
        # filter source models
        if model.limit:
            source_models = [source for source in source_models if source.name in model.limit]
        
        if model.exclude:
            source_models = [source for source in source_models if source.name not in model.exclude]
            
        if not source_models:
            raise UsBackupRuntimeError("No sources left to backup after limit/exclude filters")
        
        dest = next((storage for storage in self._model.storages if storage.name == model.dest), None)
        
        if not dest:
            raise UsBackupRuntimeError(f"Job {model.name} has inexistent destination storage")
        
        replication_src = None
        
        if model.type == 'replication':
            replication_src = next((storage for storage in self._model.storages if storage.name == model.replicate), None)
            
            if not replication_src:
                raise UsBackupRuntimeError(f"Job {model.name} has inexistent replication storage")
            
        notifier = self._notifier_factory(model, self._model.notifiers)

        return JobService(model, source_models, replication_src, dest, cleanup=self._cleanup, datastore=self._datastore, notifier=notifier, logger=self._logger)
    
    def _sigterm_handler(self) -> None:
        raise GracefulExit
    
    def _run_main(self, main_task, *args, **kwargs) -> Any:
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
            self._logger.exception(e)
        finally:
            try:
                # run cleanup jobs before exiting
                self._logger.info("Running cleanup jobs")
                loop.run_until_complete(self._cleanup.consume_all())
                
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
                
    async def _do_run_once(self) -> None:
        self._datastore.set('last_manual_run', datetime.datetime.now())
        
        job = self._job_factory(self._model.jobs[0])
        
        await job.run()
        
        return

    async def _do_run_forever(self) -> None:
        self._datastore.set('running', True)
        
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

        self._cleanup.push('remove_service_pid', os.remove, self._pid_filepath)
        self._cleanup.push('set_running_state', self._datastore.set, 'running', False)
        self._cleanup.push('log_service_shutdown', self._logger.info, 'Shutting down service')

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
            
    async def _get_stats(self, format: str) -> str:
        backups = {}
        
        for name, backup in self._datastore.get('backups', {}).items():
            backups[name] = {
                'date': str(backup.date),
                'elapsed': str(backup.elapsed),
                'error': str(backup.error) if backup.error else None,
                'dest': str(backup.dest),
            }
        
        stats = {
            'service_running': self._datastore.get('running', False),
            'last_manual_run': str(self._datastore.get('last_manual_run', '')),
            'last_scheduled_run': str(self._datastore.get('last_scheduled_run', '')),
            'backups': backups,
        }
        
        return self._format_stats(stats, format)
    
    async def _run_due_jobs(self, jobs: list[JobService]) -> None:
        tasks = []
            
        for job in jobs:
            if job.is_job_due():
                self._logger.info(f"Job {job.name} is due. Running it")
                tasks.append(asyncio.create_task(job.run(), name=job.name))
        
        if not tasks:
            self._logger.debug('No jobs due')
            return
        
        self._logger.info(f"Running {len(tasks)} jobs")
        
        self._datastore.set('last_scheduled_run', datetime.datetime.now())
        
        if len(tasks) > 1:
            self._logger.warning('More than one job run concurrently. Performance may be degraded')
                
        await asyncio.gather(*tasks, return_exceptions=True)
        
        for task in tasks:
            if isinstance(task.exception(), Exception):
                self._logger.exception(task.exception())
                
    def _format_stats(self, stats: dict, format: str) -> str:
        if format == 'json':
            return json.dumps(stats)
        
        if format == 'text':
            dictionary = {
                'service_running': 'Service running',
                'last_manual_run': 'Last manual run',
                'last_scheduled_run': 'Last scheduled run',
                'backups': 'Backups',
            }
            
            output = []
            output.append(f"{dictionary['service_running']}: {stats['service_running']}")
            output.append(f"{dictionary['last_manual_run']}: {stats['last_manual_run']}")
            output.append(f"{dictionary['last_scheduled_run']}: {stats['last_scheduled_run']}")
            output.append(f"{dictionary['backups']}:")
            output.append('  ' + '-' * 20)
            for name, backup in stats['backups'].items():
                output.append(f"  {name}:")
                output.append(f"    date: {backup['date']}")
                output.append(f"    elapsed: {backup['elapsed']}")
                output.append(f"    error: {backup['error']}")
                output.append(f"    dest: {backup['dest']}")
            return '\n'.join(output)
        
        raise UsBackupRuntimeError(f"Unknown format {format}")