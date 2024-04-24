import os
import logging
import signal
import math
import datetime
import asyncio
import usbackup.backup_handlers as backup_handlers
import usbackup.report_handlers as report_handlers
from configparser import ConfigParser
from usbackup.jobs_queue import JobsQueue
from usbackup.file_cache import FileCache
from usbackup.snapshot import UsBackupSnapshot
from usbackup.exceptions import UsbackupConfigError, GracefulExit

__all__ = ['UsBackupManager']

class UsBackupManager:
    def __init__(self, params: dict) -> None:
        self._pid_filepath: str = self._gen_pid_filepath()

        config = self._parse_config(params.get('config_files'))

        self._cleanup: JobsQueue = JobsQueue()
        self._cache: FileCache = FileCache(self._gen_cache_filepath())

        self._logger: logging.Logger = self._gen_logger(params.get('log_file', ''), params.get('log_level', 'INFO'))
        self._snapshots: list[UsBackupSnapshot] = self._gen_snapshots(params.get('snapshot_names'), config)

    def backup(self, *, service: bool = False) -> None:
        self._run_main(self._run_backup, service=service)

    def du(self, *, format: str = 'dict') -> str | dict:
        return self._run_main(self._run_du, format=format)
    
    def stats(self) -> str:
        return self._get_stats()

    def _parse_config(self, config_files: list[str]) -> dict:
        if not config_files:
            config_files = [
                '/etc/usbackup/config.conf',
                '/etc/opt/usbackup/config.conf',
                os.path.expanduser('~/.config/usbackup/config.conf'),
            ]
        
        config_inst = ConfigParser()
        config_inst.read(config_files)

        # check if any config was found
        if not config_inst.sections():
            raise UsbackupConfigError("No config found")

        config = {}

        for section in config_inst.sections():
            section_data = {}

            for key, value in config_inst.items(section):
                section_data[key] = value

            config[section] = section_data

        return config
    
    def _gen_pid_filepath(self) -> str:
        if os.getuid() == 0:
            return '/var/run/usbackup.pid'
        else:
            return os.path.expanduser('~/.usbackup.pid')
        
    def _gen_cache_filepath(self) -> str:
        if os.getuid() == 0:
            return '/var/cache/usbackup/filecache.json'
        else:
            return os.path.expanduser('~/.cache/usbackup/filecache.json')
    
    def _gen_logger(self, log_file: str, log_level: str) -> logging.Logger:
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

    def _gen_snapshots(self, snapshot_names: list[str], config: dict) -> list[UsBackupSnapshot]:
        snapshots_names = []
        config_keys = list(config.keys())

        if snapshot_names:
            names = list(set(snapshot_names))
            for name in names:
                if not name in config_keys:
                    raise UsbackupConfigError(f"Snapshot {name} not found in config file")
            
                snapshots_names.append(name)
        else:
            snapshots_names = [name for name in config_keys if name != 'GLOBALS']

        if not snapshots_names:
            raise UsbackupConfigError("No snapshots found in config file")
        
        global_config = {}

        if 'GLOBALS' in config_keys:
            global_config = config.get('GLOBALS')

        snapshots = []
        
        for snapshot_name in snapshots_names:
            snapshot_config = config.get(snapshot_name)
            snapshot_config = {**global_config, **snapshot_config}

            snapshots.append(UsBackupSnapshot(snapshot_name, snapshot_config, cleanup=self._cleanup, cache=self._cache, logger=self._logger))

        return snapshots
    
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

    async def _run_backup(self, *, service: bool = False) -> None:
        self._cleanup.add_job('persist_cache', self._cache.persist)

        if not service:
            # run once
            await self._do_backup()
            return
        
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
            asyncio.create_task(self._do_backup(exclude=['on_demand']))

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

    async def _run_du(self, *, format: str = 'string') -> None:
        self._logger.debug(f'Checking disk usage of snapshots')

        output = {}

        for snapshot in self._snapshots:
            try:
                snapshot_usage = await snapshot.du()

                if snapshot_usage.get('levels'):
                    output[snapshot.name] = snapshot_usage
            except Exception as e:
                output[snapshot.name] = {'error': str(e)}

        if format == 'string':
            return self._format_du(output)
        else:
            return output
        
    def _get_stats(self) -> str:
        output = ''
        
        for snapshot in self._snapshots:
            output += f"[{snapshot.name}]:\n"
            output += '  Levels:\n'
            
            for level in snapshot.levels:
                backup_stats = level.get_backup_stats()
                
                if not backup_stats.get('start') or not backup_stats.get('finish'):
                    output += f"    {level.name}:\n"
                    output += f"    - Last backup: Never\n\n"
                    continue
                
                start = datetime.datetime.fromtimestamp(backup_stats['start'])
                finish = datetime.datetime.fromtimestamp(backup_stats['finish'])
                
                elapsed = finish - start
                
                output += f"    {level.name}:\n"
                output += f"    - Last backup: {str(finish)}\n"
                output += f"    - Backup duration: {str(elapsed)}\n"
                output += f"    - Versions: {backup_stats.get('versions', 0)}\n"
                output += '\n'

        return output

    async def _do_backup(self, *, exclude: list = []) -> None:
        tasks = []

        for (index, snapshot) in enumerate(self._snapshots):
            if snapshot.name in exclude:
                continue

            tasks.append(asyncio.create_task(snapshot.backup_if_needed(exclude=exclude), name=index))
            
        await asyncio.gather(*tasks, return_exceptions=True)

        for task in tasks:
            snapshot = self._snapshots[int(task.get_name())]

            if isinstance(task.exception(), Exception):
                snapshot.logger.exception(task.exception(), exc_info=True)

    def _format_du(self, snapshot_usage: dict) -> str:
        if not snapshot_usage:
            return "No snapshots found"
        
        output = ''

        for snapshot_name, snapshot_data in snapshot_usage.items():
            snapshot_total = self._prettify_size(snapshot_data.get('total', 0))
            output += f"{snapshot_name} ({snapshot_total}):\n"
            snapshot_prefix = ''

            if 'error' in snapshot_data:
                output += f"{snapshot_prefix}└── Error:{snapshot_data['error']}\n\n"
                continue

            if not 'levels' in snapshot_data:
                continue

            levels = len(snapshot_data['levels'])

            for level, level_data in snapshot_data['levels'].items():
                levels -= 1

                if levels:
                    output += f"{snapshot_prefix}├──{level}"
                    level_prefix = '│  '
                else:
                    output += f"{snapshot_prefix}└──{level}"
                    level_prefix = '   '

                level_total = self._prettify_size(level_data.get('total', 0))
                output += f" ({level_total}):\n"

                versions = len(level_data['versions'])

                for (version, size) in level_data['versions']:
                    versions -= 1

                    if versions:
                        version_prefix = '├── '
                        extra_nl = False
                    else:
                        version_prefix = '└── '
                        extra_nl = True

                    size = self._prettify_size(size)

                    output += f"{snapshot_prefix}{level_prefix}{version_prefix}{version}: {size}\n"

                    if extra_nl:
                        output += f'{snapshot_prefix}{level_prefix}\n'

        return output
    
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
