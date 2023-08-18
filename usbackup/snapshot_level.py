import os
import logging
import time
import datetime
import re
import hashlib
import usbackup.cmd_exec as cmd_exec
from usbackup.aio_files import afread, afwrite
from usbackup.jobs_queue import JobsQueue
from usbackup.file_cache import FileCache
from usbackup.exceptions import UsbackupConfigError, UsbackupError
from usbackup.backup_handlers.base import BackupHandler

__all__ = ['UsBackupSnapshotLevel']

class UsBackupSnapshotLevel:
    def __init__(self, level_data: str, *, backup_dst: str, handlers: list, cleanup: JobsQueue, cache: FileCache, logger: logging.Logger) -> None:
        self._handlers: list[BackupHandler] = handlers

        parsed_level_data = self._parse_level_data(level_data)

        self._name: str =  parsed_level_data[0]
        self._replicas: int = parsed_level_data[1]
        self._type: str = parsed_level_data[2]
        self._options: list[tuple] = parsed_level_data[3]

        self._cleanup: JobsQueue = cleanup
        self._cache: FileCache = cache
        self._logger: logging.Logger = logger.getChild(self._name)

        self._label_path: str = os.path.join(backup_dst, self._name)
        self._backup_dst: str = os.path.join(self._label_path, "backup.1")
        self._backup_dst_link: str = self._gen_backup_dst_link()

        self._id: str = hashlib.md5(self._backup_dst.encode()).hexdigest()

    @property
    def name(self) -> str:
        return self._name

    @property
    def logger(self) -> logging.Logger:
        return self._logger
    
    @property
    def backup_dst(self) -> str:
        return self._backup_dst

    async def backup_needed(self, *, exclude: list = []) -> bool:
        backup_needed = False
        last_backup = await self.get_last_backup()

        if self._type == 'schedule' and not 'schedule' in exclude:
            backup_needed = self._check_backup_needed_by_schedule(last_backup)
        elif self._type == 'age' and not 'age' in exclude:
            backup_needed = self._check_backup_needed_by_age(last_backup)
        elif self._type == 'on_demand' and not 'on_demand' in exclude:
            backup_needed = True
        
        return backup_needed
        
    async def get_last_backup(self) -> dict:
        return {
            'start': self._cache.get(f'{self._id}_last_backup_start', 0),
            'finish': self._cache.get(f'{self._id}_last_backup_finish', 0),
        }
    
    async def backup(self) -> None:
        level_run_time = datetime.datetime.now()

        if await self._lock_file_exists():
            raise UsbackupError(f'Backup already running')

        self._logger.info(f'Backup started at {level_run_time}')

        self._cache.set(f'{self._id}_last_backup_start', level_run_time.timestamp())
        self._cache.set(f'{self._id}_last_backup_finish', 0)
    
        await self._rotate_backups()

        if not os.path.isdir(self._backup_dst):
            self._logger.info(f'Creating directory {self._backup_dst}')
            await cmd_exec.mkdir(self._backup_dst)

        await self._create_lock_file()
        self._cleanup.add_job(f'remove_lock_{self._id}', self._remove_lock_file)

        await self._truncate_backup_report()

        await self._write_backup_report([f'Backup for level {self._name} started at {level_run_time}', ""])

        for handler in self._handlers:
            try:
                await self._write_backup_report(f'Starting {handler.name} backup')
                handler_report = await handler.backup(self._backup_dst, self._backup_dst_link, logger=self._logger)
            except (Exception) as e:
                self._logger.exception(f'{handler.name} backup handler exception: {e}', exc_info=True)
                handler_report = f'Exception: {e}'

            if isinstance(handler_report, str):
                handler_report = [handler_report]

            await self._write_backup_report(handler_report)

        await self._remove_lock_file()
        self._cleanup.remove_job(f'remove_lock_{self._id}')

        level_finish_time = datetime.datetime.now()

        self._cache.set(f'{self._id}_last_backup_finish', level_finish_time.timestamp())

        elapsed_time = level_finish_time - level_run_time

        await self._write_backup_report([f'Backup for level {self._name} finished at {level_finish_time}', f'Elapsed time: {elapsed_time}', ""])

        self._logger.info(f'Backup finished at {level_finish_time}. Elapsed time: {elapsed_time}')

    async def get_backup_report(self) -> str:
        report_path = os.path.join(self._backup_dst, "backup.log")
        report = ''

        if not os.path.isfile(report_path):
            return report
        
        # read all report lines
        report = await afread(report_path)

        return report
    
    async def du(self) -> dict:
        output = {
            'total': 0,
            'versions': []
        }

        if not os.path.isdir(self._label_path):
            return output

        usage = await cmd_exec.du(self._label_path, match='backup.*')

        if not usage:
            return output
        
        usage = usage.strip().split('\n')

        for row in usage:
            row = re.split(r'\s+', row, maxsplit=1)

            if len(row) != 2:
                continue

            version = os.path.basename(row[1])
            # du returns size in KB, convert to bytes
            size = int(row[0]) * 1024
            
            output['total'] += size
            output['versions'].append((version, size))

        # sort by version
        output['versions'].sort(key=lambda x: x[0])

        return output
    
    def _parse_level_data(self, level_data: str) -> tuple:
        level = level_data.strip().split()

        if len(level) < 3:
            raise UsbackupConfigError('Invalid level specified')

        name = level[0]
        replicas = int(level[1])
        type = level[2]
        options = level[3:]

        if not name:
            raise UsbackupConfigError('No level name specified')

        if not replicas > 0:
            raise UsbackupConfigError('Invalid number of replicas specified')

        if not type in ('schedule', 'age', 'on_demand'):
            raise UsbackupConfigError(f'Invalid backup type "{type}"')

        if type == 'schedule':
            if len(options) != 5:
                raise UsbackupConfigError("Invalid schedule specified")
            
            parsed_options = []

            for schedule in options:
                if schedule == '*':
                    opt = ('any', None)

                elif schedule.isdigit():
                    opt = ('fixed', int(schedule))

                elif schedule.startswith('*/'):
                    value = schedule[2:]

                    if not value.isdigit():
                        raise UsbackupConfigError("Invalid schedule specified")

                    opt = ('step', int(value))

                elif '-' in schedule:
                    (start, end) = schedule.split('-')

                    if not start.isdigit() or not end.isdigit():
                        raise UsbackupConfigError("Invalid schedule specified")

                    opt = ('range', (int(start), int(end)))

                elif ',' in schedule:
                    values = schedule.split(',')

                    for value in values:
                        if not value.isdigit():
                            raise UsbackupConfigError("Invalid schedule specified")

                    opt = ('list', tuple([int(x) for x in values]))

                elif not opt:
                    raise UsbackupConfigError("Invalid schedule specified")

                parsed_options.append(opt)

            options = tuple(parsed_options)
        elif type == 'age':
            if len(options) < 1:
                raise UsbackupConfigError("No age interval specified")

            # regex split 1m, 1h, 1d into number and interval
            age_interval = re.match(r'(\d+)([mhd])', options[0])

            if not age_interval:
                raise UsbackupConfigError("Invalid age interval specified")

            groups = age_interval.groups()

            options = (int(groups[0]), groups[1])

        return (name, replicas, type, options)

    def _gen_backup_dst_link(self) -> str:
        backup_dst_link = None

        if self._replicas > 1:
            backup_dst_link = os.path.join(self._label_path, "backup.2")

            if os.path.isdir(backup_dst_link):
                backup_dst_link = backup_dst_link

        return backup_dst_link

    def _check_backup_needed_by_schedule(self, last_backup: dict) -> bool:
        # check if run time matches schedule
        parsed_run_time = datetime.datetime.now().strftime("%M %H %d %m %w").split()
        schedule_match = True

        for (config_segment, run_time_segment) in zip(self._options, parsed_run_time):
            run_time_segment = int(run_time_segment)

            if config_segment[0] == 'any':
                continue

            # handle fixed number syntax
            if config_segment[0] == 'fixed' and config_segment[1] != run_time_segment:
                schedule_match = False
                break

            # handle */5 syntax
            if config_segment[0] == 'step':
                if run_time_segment % config_segment[1] != 0:
                    schedule_match = False
                    break

            # handle 1-5 syntax
            if config_segment[0] == 'range':
                (start, end) = config_segment[1]

                if not start <= run_time_segment <= end:
                    schedule_match = False
                    break

            # handle 1,2,3 syntax
            if config_segment[0] == 'list':
                if not run_time_segment in config_segment[1]:
                    schedule_match = False
                    break

        if not schedule_match:
            self._logger.debug(f'Backup not needed. Schedule {self._options} does not match {parsed_run_time}')
            return False
        
        last_backup_start_ts = last_backup.get('start')

        if not last_backup_start_ts:
            return True

        # make sure last backup is not too recent
        parsed_last_backup_time = time.strftime('%M %H %d %m %w', time.localtime(last_backup_start_ts)).split()

        if parsed_last_backup_time == parsed_run_time:
            self._logger.debug(f'Backup not needed. Last backup was done at {parsed_last_backup_time}')
            return False

        return True

    def _check_backup_needed_by_age(self, last_backup: dict) -> bool:
        age_intervals = {
            'm': 60,
            'h': 60 * 60,
            'd': 60 * 60 * 24,
        }

        target_age = self._options[0] * age_intervals[self._options[1].lower()]

        last_backup_finish_ts = last_backup.get('finish')

        if not last_backup_finish_ts:
            return True
        
        run_time_ts = datetime.datetime.now().timestamp()

        # check if latest version is within the age interval
        last_backup_age = run_time_ts - last_backup_finish_ts

        if last_backup_age < target_age:
            self._logger.debug(f'Backup not needed. Last backup is within the age interval ({last_backup_age} < {target_age})')
            return False

        return True
    
    async def _rotate_backups(self) -> None:
        if not os.path.isdir(self._backup_dst):
            return None
        
        rm_list = []
        mv_list = []

        if self._replicas == 1:
            return None

        for replica in range(self._replicas, 0, -1):
            src = os.path.join(self._label_path, "backup." + str(replica))
            dst = os.path.join(self._label_path, "backup." + str(replica + 1))

            if replica == self._replicas:
                rm_list.append(src)
            else:
                mv_list.append((src, dst))

        for src in rm_list:
            if not os.path.isdir(src):
                self._logger.warn(f'Backup directory "{src}" does not exist. Can\'t remove it')
                continue

            self._logger.info(f'Removing {src}')

            await cmd_exec.remove(src)

        for (src, dst) in mv_list:
            if not os.path.isdir(src):
                self._logger.warn(f'Backup directory "{src}" does not exist. Can\'t move it to {dst}')
                continue

            self._logger.info(f'Moving {src} to {dst}')

            await cmd_exec.move(src, dst)

    async def _lock_file_exists(self) -> bool:
        lock_file = os.path.join(self._backup_dst, 'backup.lock')

        return os.path.isfile(lock_file)

    async def _create_lock_file(self) -> None:
        lock_file = os.path.join(self._backup_dst, 'backup.lock')

        await afwrite(lock_file, '')

    async def _remove_lock_file(self) -> None:
        lock_file = os.path.join(self._backup_dst, 'backup.lock')

        await cmd_exec.remove(lock_file)

    async def _truncate_backup_report(self) -> None:
        report_path = os.path.join(self._backup_dst, "backup.log")

        if not os.path.isfile(report_path):
            return None

        # truncate file
        await afwrite(report_path, "")

    async def _write_backup_report(self, report: str | list) -> None:
        report_path = os.path.join(self._backup_dst, "backup.log")

        if not report:
            return None

        if not isinstance(report, list):
            report = [report]

        # append stats to file
        await afwrite(report_path, "\n".join(report) + "\n", mode='a')