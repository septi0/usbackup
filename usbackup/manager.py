import os
import sys
import fcntl
import logging
import signal
import yaml
import datetime
import asyncio
import json
import re
from logging.handlers import TimedRotatingFileHandler
from dotenv import dotenv_values
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.libraries.cmd_exec import CmdExec
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
    # like cron, clock changes of up to 3 hours (daylight saving time) are followed minute by minute, larger ones restart the schedule
    _max_clock_jump: int = 180
    
    def __init__(self, *, log_file: str | None = None, log_level: str | None = None, config_file: str | None = None, alt_job: dict | None = None) -> None:
        self._pid_filepath: str = self._get_pid_filepath()

        self._logger: logging.Logger = self._logger_factory(log_file, log_level)
        self._model: UsBackupModel = UsBackupModel(**self._load_config(config_file=config_file, alt_job=alt_job))
        datastore_filepath = self._get_datastore_filepath()

        self._datastore: Datastore = Datastore(datastore_filepath)
        self._cleanup: CleanupQueue = CleanupQueue(datastore=self._datastore, lock_dir=os.path.join(os.path.dirname(datastore_filepath), 'cleanup'))
    
    def run_once(self, job_name: str | None = None, *, limit: list[str] | None = None, exclude: list[str] | None = None) -> bool:
        """ Run a job once, without scheduling: the configured job with the given name, otherwise the job built from the command line. Returns True if the job completed successfully."""
        job = self._job_factory(self._get_job_model(job_name) if job_name else self._model.jobs[0], limit=limit, exclude=exclude)
        
        return self._run_main(self._do_run_once, job) is True
    
    def prune(self, job_name: str, *, limit: list[str] | None = None, exclude: list[str] | None = None, dry_run: bool = False) -> bool:
        """ Apply the retention policies of a configured job, without running it. Returns True if every source was pruned."""
        job_model = self._get_job_model(job_name)
        
        if not job_model.retention_policy and not job_model.sources_retention_policy:
            raise UsBackupRuntimeError(f'Job "{job_name}" has no retention policy')
        
        job = self._job_factory(job_model, limit=limit, exclude=exclude)
        
        # a dry run only reads, so it never runs cleanup jobs either
        return self._run_main(job.prune, dry_run=dry_run, recover=not dry_run) is True
    
    def run_forever(self) -> bool:
        """ Run the backup job forever, scheduling it every minute. Returns False if the service failed."""
        return self._run_main(self._do_run_forever) is not False
    
    def stats(self, format: str) -> None:
        """ Get the current stats of the backup service."""
        # a read only query never runs cleanup jobs, which may need slow or unreachable remote hosts
        return self._run_main(self._get_stats, format=format, recover=False)
    
    def _load_config(self, *, config_file: str | None = None, alt_job: dict | None = None) -> dict:
        if not config_file:
            default_config_paths = [
                '/etc/usbackup',
                '/etc/opt/usbackup',
                os.path.expanduser('~/.config/usbackup'),
            ]

            for dir in default_config_paths:
                if os.path.isfile(os.path.join(dir, 'config.yml')):
                    config_file = os.path.join(dir, 'config.yml')
                    break

        if not config_file or not os.path.isfile(config_file):
            raise UsBackupRuntimeError("Config file does not exist")
        
        config_secrets_file = None
        
        if os.path.isfile(os.path.dirname(config_file) + '/secrets.env'):
            config_secrets_file = os.path.dirname(config_file) + '/secrets.env'

        with open(config_file, 'r') as f:                
            try:
                config = yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise UsBackupRuntimeError(f"Failed to parse config file: {e}")
            
        if alt_job:
            config['jobs'] = [alt_job]
        
        if config_secrets_file:
            config = self._expand_config_secrets(config, config_secrets_file)
            
        return config

    def _expand_config_secrets(self, config: dict, config_secrets_file: str) -> dict:
        try:
            secrets = dotenv_values(config_secrets_file)
        except Exception as e:
            raise UsBackupRuntimeError(f"Failed to load secrets file: {e}")

        for key, value in config.items():
            config[key] = self._replace_config_secrets(value, secrets)
        
        return config

    def _replace_config_secrets(self, obj: Any, secrets: dict) -> Any:
        if isinstance(obj, dict):
            return {k: self._replace_config_secrets(v, secrets) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_config_secrets(item, secrets) for item in obj]
        elif isinstance(obj, str):
            return re.sub(r'\$\{(\w+)\}', lambda m: secrets.get(m.group(1), m.group(0)), obj)

        return obj

    def _get_pid_filepath(self) -> str:
        if os.getuid() == 0:
            return '/var/run/usbackup.pid'
        else:
            return os.path.expanduser('~/.usbackup.pid')
        
    def _get_ssh_control_dir(self) -> str:
        # a runtime directory keeps control socket paths short and is cleared on reboot
        if os.getuid() == 0:
            return '/run/usbackup/ssh'
        
        if os.environ.get('XDG_RUNTIME_DIR'):
            return os.path.join(os.environ['XDG_RUNTIME_DIR'], 'usbackup', 'ssh')
        
        return os.path.expanduser('~/.usbackup/ssh')
    
    def _is_venv(self) -> bool:
        return sys.prefix != getattr(sys, 'base_prefix', sys.prefix)
        
    def _get_datastore_filepath(self) -> str:
        if self._is_venv():
            filepath = os.path.join(sys.prefix, 'var', 'data.db')
        elif os.getuid() == 0:
            filepath = '/var/lib/usbackup/data.db'
        else:
            filepath = os.path.expanduser(f'~/.usbackup/data.db')

        directory = os.path.dirname(filepath)
        
        # the datastore holds cleanup entries with host credentials, so only its owner may read it
        os.makedirs(directory, mode=0o700, exist_ok=True)
        
        if os.stat(directory).st_uid == os.getuid():
            os.chmod(directory, 0o700)
            
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
    
    def _get_job_model(self, name: str) -> JobModel:
        job_model = next((job for job in self._model.jobs if job.name == name), None)
        
        if not job_model:
            raise UsBackupRuntimeError(f'Job "{name}" does not exist')
        
        return job_model
    
    def _job_factory(self, model: JobModel, *, limit: list[str] | None = None, exclude: list[str] | None = None) -> JobService:
        source_models = self._model.sources
        
        # filter source models
        if model.limit:
            source_models = [source for source in source_models if source.name in model.limit]
        
        if model.exclude:
            source_models = [source for source in source_models if source.name not in model.exclude]
        
        # a manual run of a configured job can be narrowed to some of its sources
        unknown_sources = [name for name in [*(limit or []), *(exclude or [])] if name not in [source.name for source in source_models]]
        
        if unknown_sources:
            raise UsBackupRuntimeError(f'Job "{model.name}" has no sources named: {", ".join(unknown_sources)}')
        
        if limit:
            source_models = [source for source in source_models if source.name in limit]
        
        if exclude:
            source_models = [source for source in source_models if source.name not in exclude]
            
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
    
    def _run_main(self, main_task, *args, recover: bool = True, **kwargs) -> Any:
        output = None

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        loop.add_signal_handler(signal.SIGTERM, self._sigterm_handler)
        loop.add_signal_handler(signal.SIGINT, self._sigterm_handler)
        loop.add_signal_handler(signal.SIGQUIT, self._sigterm_handler)
        
        if not CmdExec.enable_ssh_reuse(self._get_ssh_control_dir()):
            self._logger.warning(f'SSH connection reuse disabled: "{self._get_ssh_control_dir()}" is not a private directory with a short enough path')
            
        # only entries of processes that are no longer alive are recovered
        try:
            if recover:
                if self._cleanup.has_orphans():
                    self._logger.warning("Cleanup queue has items. Possible crash detected. Running cleanup jobs")
                
                # also removes empty queues left by dead processes
                loop.run_until_complete(self._cleanup.consume_orphans())
        except Exception as e:
            self._logger.exception(f'Failed to recover from crash: {e}')

        try:
            output = loop.run_until_complete(main_task(*args, **kwargs))
        except (GracefulExit) as e:
            self._logger.info("Received termination signal")
        except (Exception) as e:
            self._logger.exception(e)
            output = False
        finally:
            try:
                # stop running tasks first so cleanup jobs do not race with them
                self._cancel_tasks(loop)
                
                # run cleanup jobs before exiting
                self._logger.info("Running cleanup jobs")
                
                # failed cleanup jobs stay queued and are retried by the next start
                try:
                    loop.run_until_complete(self._cleanup.consume_all())
                except Exception as e:
                    self._logger.exception(f'Failed to run cleanup jobs: {e}')
                
                loop.run_until_complete(CmdExec.close_ssh_connections())
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                self._cleanup.close()
                asyncio.set_event_loop(None)
                loop.close()

        return output
    
    def _cancel_tasks(self, loop: asyncio.AbstractEventLoop) -> None:
        tasks = asyncio.all_tasks(loop=loop)

        if not tasks:
            return
        
        self._logger.info(f"Cancelling {len(tasks)} running task(s)")

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
                
    async def _do_run_once(self, job: JobService) -> bool:
        self._datastore.set('last_manual_run', datetime.datetime.now())
        
        return await job.run()
        
    async def _do_run_forever(self) -> bool:
        job_models = self._model.jobs
        
        if not job_models:
            self._logger.error("No jobs found in config")
            return False
        
        jobs = []
        
        for job_model in job_models:
            jobs.append(self._job_factory(job_model))
        
        # run as service
        pid_file = self._acquire_pid_file()

        if pid_file is None:
            self._logger.error("Service is already running")
            return False

        try:
            self._logger.info(f'Starting service with pid {os.getpid()}')

            last_minute = datetime.datetime.now().replace(second=0, microsecond=0) - datetime.timedelta(minutes=1)

            # every wall clock minute is checked once, like cron, also when daylight saving time moves the clock
            while True:
                now = datetime.datetime.now().replace(second=0, microsecond=0)
                elapsed = int((now - last_minute).total_seconds() // 60)

                if elapsed > self._max_clock_jump:
                    self._logger.warning(f'Clock jumped forward by {elapsed} minutes. Jobs due in the skipped minutes are not run')
                    asyncio.create_task(self._run_due_jobs(jobs, [now]))
                    last_minute = now
                elif elapsed > 1:
                    # minutes skipped by a forward clock change or a short stall still get their jobs run, once
                    self._logger.warning(f'Clock jumped forward by {elapsed} minutes. Running the jobs due in the skipped minutes')
                    asyncio.create_task(self._run_due_jobs(jobs, [last_minute + datetime.timedelta(minutes=minute) for minute in range(1, elapsed + 1)]))
                    last_minute = now
                elif elapsed == 1:
                    asyncio.create_task(self._run_due_jobs(jobs, [now]))
                    last_minute = now
                elif elapsed < -self._max_clock_jump:
                    self._logger.warning(f'Clock jumped back by {-elapsed} minutes. The schedule continues from the new time')
                    asyncio.create_task(self._run_due_jobs(jobs, [now]))
                    last_minute = now

                # after a short backward change (e.g. daylight saving time ending) the minutes that already ran are not run again

                current = datetime.datetime.now()
                time_left = (current.replace(second=0, microsecond=0) + datetime.timedelta(minutes=1) - current).total_seconds()

                self._logger.debug(f'Next run in {time_left} s')

                await asyncio.sleep(time_left)
        finally:
            self._release_pid_file(pid_file)

    def _acquire_pid_file(self) -> int | None:
        """
        Lock and write the pid file, held for the whole service lifetime. Returns None if another service holds it.
        """
        pid_file = os.open(self._pid_filepath, os.O_RDWR | os.O_CREAT, 0o644)
        
        # the lock is released by the kernel when the service dies, so a stale pid file never blocks a new service
        try:
            fcntl.flock(pid_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(pid_file)
            return None
        
        os.ftruncate(pid_file, 0)
        os.write(pid_file, str(os.getpid()).encode('utf-8'))
        
        return pid_file
    
    def _release_pid_file(self, pid_file: int) -> None:
        try:
            os.unlink(self._pid_filepath)
            self._logger.info(f"Removed pid file {self._pid_filepath}")
        except OSError as e:
            self._logger.error(f"Failed to remove pid file {self._pid_filepath}: {e}")
        
        os.close(pid_file)
    
    def _is_service_running(self) -> bool:
        try:
            pid_file = os.open(self._pid_filepath, os.O_RDONLY)
        except FileNotFoundError:
            return False
        
        # the running service holds an exclusive lock on its pid file
        try:
            fcntl.flock(pid_file, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            os.close(pid_file)
        
        return False
            
    async def _get_stats(self, format: str) -> str:
        backups = {}
        
        for name, backup in self._datastore.get('backups', {}).items():
            backups[name] = {
                'date': str(backup['date']),
                'elapsed': str(backup['elapsed']),
                'error': backup['error'],
                'dest': backup['dest'],
            }
        
        stats = {
            'service_running': self._is_service_running(),
            'last_manual_run': str(self._datastore.get('last_manual_run', '')),
            'last_scheduled_run': str(self._datastore.get('last_scheduled_run', '')),
            'backups': backups,
        }
        
        return self._format_stats(stats, format)
    
    async def _run_due_jobs(self, jobs: list[JobService], minutes: list[datetime.datetime]) -> None:
        tasks = []
            
        # a job due in several of the minutes is still run once
        for job in jobs:
            if not any(job.is_job_due(minute) for minute in minutes):
                continue
            
            if job.is_running:
                self._logger.warning(f"Job {job.name} is due but its previous run is still in progress. Skipping it")
                continue
            
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