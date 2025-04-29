import os
import logging
import signal
import math
import datetime
import asyncio
from usbackup.cleanup_queue import CleanupQueue
from usbackup.file_cache import FileCache
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

        self._config = UsBackupConfigParser(config_file)
        self._logger: logging.Logger = self._logger_factory(log_file, log_level)
        
        self._cleanup: CleanupQueue = CleanupQueue()
        self._cache: FileCache = FileCache()
        self._notifier: UsbackupNotifier = self._notifier_factory(self._config['notification'])

    def backup(self, daemon: bool = False, config: dict = {}) -> None:
        return self._run_main(self._run_backup, daemon=daemon, config=config)

    def du(self, *, config: dict) -> str | dict:
        return self._run_main(self._run_du, config=config)
    
    def stats(self) -> str:
        return self._get_stats()
    
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
            handler_logger = notifier_logger.getChild(notifier_config['handler'])
            handler_class = notification_handler_loader(notifier_config['handler'])

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
        self._cleanup.add_job('persist_cache', self._cache.persist)

        if not daemon:
            if config['retention-policy']:
                # convert retention_policy to dict
                config['retention-policy'] = config['retention-policy'].split(',')
                config['retention-policy'] = {k.strip(): int(v) for k, v in (x.split('=') for x in config['retention-policy'])}
                
            backup_job = self._backup_job_factory('manual', config)
            
            await backup_job.run()
            return
        
        jobs_configs = self._config['jobs']
        
        backup_jobs: list[UsBackupJob] = []
        
        for job_config in jobs_configs:
            backup_jobs.append(self._backup_job_factory(job_config['name'], job_config))
        
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

            # persist cache every 5 minutes
            if datetime.datetime.now().minute % 5 == 0:
                self._logger.debug('Persisting cache')
                self._cache.persist()

            self._logger.debug(f'Next run in {time_left} s')

            await asyncio.sleep(time_left)

    # async def _run_du(self, *, format: str = 'string') -> None:
    #     self._logger.debug(f'Checking disk usage of snapshots')

    #     output = {}

    #     for snapshot in self._snapshots:
    #         try:
    #             snapshot_usage = await snapshot.du()

    #             if snapshot_usage.get('levels'):
    #                 output[snapshot.name] = snapshot_usage
    #         except Exception as e:
    #             output[snapshot.name] = {'error': str(e)}

    #     if format == 'string':
    #         return self._format_du(output)
    #     else:
    #         return output
        
    # def _get_stats(self) -> str:
    #     output = ''
        
    #     for snapshot in self._snapshots:
    #         output += f"[{snapshot.name}]:\n"
    #         output += '  Levels:\n'
            
    #         for level in snapshot.levels:
    #             backup_stats = level.get_backup_stats()
                
    #             if not backup_stats.get('start') or not backup_stats.get('finish'):
    #                 output += f"    {level.name}:\n"
    #                 output += f"    - Last backup: Never\n\n"
    #                 continue
                
    #             start = datetime.datetime.fromtimestamp(backup_stats['start'])
    #             finish = datetime.datetime.fromtimestamp(backup_stats['finish'])
                
    #             elapsed = finish - start
                
    #             output += f"    {level.name}:\n"
    #             output += f"    - Last backup: {str(finish)}\n"
    #             output += f"    - Backup duration: {str(elapsed)}\n"
    #             output += f"    - Versions: {backup_stats.get('versions', 0)}\n"
    #             output += '\n'

    #     return output
    
    def _backup_job_factory(self, job_name: str, job_config: dict) -> UsBackupJob:
        hosts_config = self._config['hosts']
        
        if job_config.get('limit'):
            hosts_config = [host for host in hosts_config if host.get('name') in job_config['limit']]
        
        if job_config.get('exclude'):
            hosts_config = [host for host in hosts_config if host.get('name') not in job_config['exclude']]
            
        if not hosts_config:
            raise UsbackupRuntimeError("No hosts left to backup after limit/exclude filters")
            
        hosts: list[UsBackupHost] = []
        
        for host in hosts_config:                
            hosts.append(self._backup_host_factory(host))
            
        dest = job_config['dest']
            
        if not dest:
            raise UsbackupRuntimeError("No destination found for job")
        
        job_config = {
            'schedule': job_config.get('schedule'),
            'retention-policy': job_config.get('retention-policy'),
            'notification-policy': job_config.get('notification-policy'),
            'concurrency': job_config.get('concurrency'),
            'pre-backup-cmd': job_config.get('pre-backup-cmd'),
            'post-backup-cmd': job_config.get('post-backup-cmd'),
        }
            
        logger = self._logger.getChild(job_name)
            
        return UsBackupJob(job_name, hosts, dest, job_config, notifier=self._notifier, logger=logger)
    
    def _backup_host_factory(self, host_config: dict) -> UsBackupHost:
        host_name = host_config['name']
        try:
            remote = Remote(host_config['host'], default_user='root', default_port=22)
        except ValueError:
            raise UsbackupRuntimeError(f'Invalid host {host_config["host"]}')
        
        host_logger = self._logger.getChild(host_name)
        handlers = []
        
        for backup_config in host_config['backup']:
            handler_logger = host_logger.getChild(backup_config['handler'])
            handler_class = backup_handler_loader(backup_config['handler'])
            
            handlers.append(handler_class(remote, backup_config, logger=handler_logger))
        
        return UsBackupHost(host_name, remote, handlers, cleanup=self._cleanup, cache=self._cache, logger=host_logger)
    
    async def _run_due_jobs(self, backup_jobs: list[UsBackupJob]) -> None:
        tasks = []
            
        for job in backup_jobs:
            if job.is_job_due():
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

    # def _format_du(self, snapshot_usage: dict) -> str:
    #     if not snapshot_usage:
    #         return "No snapshots found"
        
    #     output = ''

    #     for snapshot_name, snapshot_data in snapshot_usage.items():
    #         snapshot_total = self._prettify_size(snapshot_data.get('total', 0))
    #         output += f"{snapshot_name} ({snapshot_total}):\n"
    #         snapshot_prefix = ''

    #         if 'error' in snapshot_data:
    #             output += f"{snapshot_prefix}└── Error:{snapshot_data['error']}\n\n"
    #             continue

    #         if not 'levels' in snapshot_data:
    #             continue

    #         levels = len(snapshot_data['levels'])

    #         for level, level_data in snapshot_data['levels'].items():
    #             levels -= 1

    #             if levels:
    #                 output += f"{snapshot_prefix}├──{level}"
    #                 level_prefix = '│  '
    #             else:
    #                 output += f"{snapshot_prefix}└──{level}"
    #                 level_prefix = '   '

    #             level_total = self._prettify_size(level_data.get('total', 0))
    #             output += f" ({level_total}):\n"

    #             versions = len(level_data['versions'])

    #             for (version, size) in level_data['versions']:
    #                 versions -= 1

    #                 if versions:
    #                     version_prefix = '├── '
    #                     extra_nl = False
    #                 else:
    #                     version_prefix = '└── '
    #                     extra_nl = True

    #                 size = self._prettify_size(size)

    #                 output += f"{snapshot_prefix}{level_prefix}{version_prefix}{version}: {size}\n"

    #                 if extra_nl:
    #                     output += f'{snapshot_prefix}{level_prefix}\n'

    #     return output
    
    # prettify size same way as du -h
    def _prettify_size(self, size: int) -> str:
        sizes = ['B', 'KB', 'MB', 'GB', 'TB']

        if size == 0:
            return '0B'

        i = int(math.floor(math.log(size, 1024)))

        if i > 4:
            i = 4

        p = math.pow(1024, i)
        s = round(size / p, 2)

        return f"{s:.1f}{sizes[i]}"
