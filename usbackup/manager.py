import os
import sys
import logging
import asyncio
import time
import signal
import math
from configparser import ConfigParser
from usbackup.snapshot import UsBackupSnapshot
from usbackup.exceptions import UsbackupConfigError

__all__ = ['UsBackupManager']

class UsBackupManager:
    def __init__(self, params: dict) -> None:
        self._pid_file: str = "/tmp/usbackup.pid"
        self._running: bool = False

        config = self._parse_config(params.get('config_files'))

        self._logger: logging.Logger = self._gen_logger(params.get('log_file', ''), params.get('log_level', 'INFO'))
        self._snapshots: list[UsBackupSnapshot] = self._gen_snapshots(params.get('snapshot_names'), config)

    def backup(self, *, service: bool = False) -> None:
        if service:
            self._run_service()
        else:
            self._run_once()

    def du(self, format: str = 'dict') -> str | dict:
        self._logger.debug(f'Checking disk usage of snapshots')

        output = {}

        for snapshot in self._snapshots:
            try:
                snapshot_usage = snapshot.du()

                if snapshot_usage.get('levels'):
                    output[snapshot.name] = snapshot_usage
            except Exception as e:
                output[snapshot.name] = {'error': str(e)}

            snapshot.cleanup()

        if format == 'string':
            return self._format_du(output)
        else:
            return output

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

            snapshots.append(UsBackupSnapshot(snapshot_name, snapshot_config, logger=self._logger))

        return snapshots

    def _run_service(self) -> None:
        pid = str(os.getpid())

        if os.path.isfile(self._pid_file):
            self._logger.error("Service is already running")
            sys.exit(1)

        with open(self._pid_file, 'w') as f:
            f.write(pid)

        self._logger.info("Starting service")

        # catch sigterm
        def sigterm_handler(signum, frame):
            raise KeyboardInterrupt
        
        signal.signal(signal.SIGTERM, sigterm_handler)

        loop = asyncio.new_event_loop()

        asyncio.set_event_loop(loop)

        async def run_service():
            while True:
                await self._do_backup(service=True)
                await asyncio.sleep(60)

        try:
            loop.run_until_complete(run_service())
        except (KeyboardInterrupt):
            pass
        except (Exception) as e:
            self._logger.exception(e, exc_info=True)
        finally:
            self._logger.info("Shutting down service")

            os.unlink(self._pid_file)

            tasks = asyncio.all_tasks(loop)

            for task in tasks:
                task.cancel()

            loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

            for task in tasks:
                if task.exception():
                    self._logger.exception(task.exception(), exc_info=True)
                
            loop.close()
    
    def _run_once(self) -> None:
        loop = asyncio.new_event_loop()

        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(self._do_backup())
        except (KeyboardInterrupt):
            self._logger.info("Backup interrupted by user")
            pass
        except (Exception) as e:
            self._logger.info("Backup interrupted by an exception")
            self._logger.exception(e, exc_info=True)
        finally:
            tasks = asyncio.all_tasks(loop)

            for task in tasks:
                task.cancel()

            loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))

            for task in tasks:
                if task.exception():
                    self._logger.exception(task.exception(), exc_info=True)
                
            loop.close()

    async def _do_backup(self, *, service = False) -> None:
        if self._running:
            logging.warning("Previous backup is still running")
            return

        # set _running to current timestamp
        self._running = time.time()

        formatted_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(self._running))

        self._logger.debug(f'Checking backups for {formatted_time} time')

        for snapshot in self._snapshots:
            try:
                snapshot.backup(self._running, not service)
            except (Exception) as e:
                self._logger.exception(f"{snapshot.name} snapshot exception: {e}", exc_info=True)
            except (KeyboardInterrupt) as e:
                snapshot.cleanup()
                self._running = False

                raise e from None
            finally:
                snapshot.cleanup()

        self._running = False

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

                    # check if last loop iteration
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
