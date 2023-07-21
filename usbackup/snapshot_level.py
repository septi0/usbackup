import os
import logging
import time
import datetime
import re
import usbackup.cmd_exec as cmd_exec
from usbackup.exceptions import UsbackupConfigError
from usbackup.backup_handlers.base import BackupHandler

__all__ = ['UsBackupSnapshotLevel']

class UsBackupSnapshotLevel:
    def __init__(self, level_data: str, *, backup_dst: str, handlers: list, logger: logging.Logger) -> None:
        self._handlers: list[BackupHandler] = handlers

        parsed_level_data = self._parse_level_data(level_data)

        self._name: str =  parsed_level_data[0]
        self._replicas: int = parsed_level_data[1]
        self._type: str = parsed_level_data[2]
        self._options: list[tuple] = parsed_level_data[3]

        self._logger: logging.Logger = logger.getChild(self._name)

        self._label_path: str = os.path.join(backup_dst, self._name)
        self._backup_dst: str = os.path.join(self._label_path, "backup.1")
        self._backup_dst_link: str = self._gen_backup_dst_link()

    @property
    def name(self) -> str:
        return self._name
    
    def get_backup_dst(self) -> str:
        return self._backup_dst

    def backup_needed(self, run_time: float = None, include_manual: bool = False) -> bool:
        backup_needed = False
        last_backup = self.get_last_backup()

        if not run_time:
            run_time = time.time()

        if self._type == 'schedule':
            backup_needed = self._check_backup_needed_by_schedule(last_backup, run_time)
        elif self._type == 'age':
            backup_needed = self._check_backup_needed_by_age(last_backup)
        elif self._type == 'on_demand':
            backup_needed = include_manual
        
        return backup_needed
        
    def get_last_backup(self) -> int:
        lock_path = os.path.join(self._backup_dst, "backup.lock")
        if not os.path.isfile(lock_path):
            return None

        # get mtime from tile
        timestamp = os.path.getmtime(lock_path)

        return timestamp
    
    def backup(self) -> None:
        self._rotate_backups()

        self._logger.info(f'Creating directory {self._backup_dst}')
        cmd_exec.mkdir(self._backup_dst)

        # create lock file
        lock_file = os.path.join(self._backup_dst, 'backup.lock')

        with open(lock_file, 'w') as f:
            f.write('')

        self._truncate_backup_report()

        start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self._write_backup_report([f'Backup for level {self._name} started at {start_time}', ""])

        for handler in self._handlers:
            try:
                self._write_backup_report(f'Starting {handler.name} backup')
                handler_report = handler.backup(self._backup_dst, self._backup_dst_link, logger=self._logger)
            except (Exception) as e:
                self._logger.exception(f'{handler.name} backup handler exception: {e}', exc_info=True)
                handler_report = f'Exception: {e}'

            if isinstance(handler_report, str):
                handler_report = [handler_report]

            self._write_backup_report(handler_report)

    def get_backup_report(self) -> str:
        report_path = os.path.join(self._backup_dst, "backup.log")
        report = ''

        if not os.path.isfile(report_path):
            return report
        
        # read all report lines
        with open(report_path, 'r') as f:
            report = f.read()

        return report
    
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

            for schedule in options:
                if not schedule.isdigit() and schedule != '*':
                    raise UsbackupConfigError("Invalid schedule specified")

            options = tuple(options)
        elif type == 'age':
            if len(options) < 1:
                raise UsbackupConfigError("No age interval specified")

            # regex split 1m, 1h, 1d into number and interval
            age_interval = re.match(r'(\d+)([mhd])', options[0])

            if not age_interval:
                raise UsbackupConfigError("Invalid age interval specified")

            options = tuple(age_interval.groups())

        return (name, replicas, type, options)

    def _gen_backup_dst_link(self) -> str:
        backup_dst_link = None

        if self._replicas > 1:
            backup_dst_link = os.path.join(self._label_path, "backup.2")

            if os.path.isdir(backup_dst_link):
                backup_dst_link = backup_dst_link

        return backup_dst_link

    def _check_backup_needed_by_schedule(self, last_backup: int, run_time: float) -> bool:
        # check if run time matches schedule
        run_time = time.strftime('%M %H %d %m %w', time.localtime(run_time)).split()

        for (schedule, segment) in zip(self._options, run_time):
            if schedule != '*' and schedule != segment:
                self._logger.debug(f'Backup not needed. Schedule {schedule} does not match {segment}')
                return False

        if not last_backup:
            return True

        # make sure last backup is not too recent
        last_backup_time = time.strftime('%M', time.localtime(last_backup)).split()

        if last_backup_time[0] == run_time[0]:
            self._logger.debug(f'Backup not needed. Last backup was done at minute {last_backup_time[0]}')
            return False

        return True

    def _check_backup_needed_by_age(self, last_backup: int) -> bool:
        age_intervals = {
            'm': 60,
            'h': 60 * 60,
            'd': 60 * 60 * 24,
        }

        target_age = int(self._options[0]) * age_intervals[self._options[1].lower()]

        if not last_backup:
            return True

        # check if latest version is within the age interval
        last_backup_age = time.time() - last_backup

        if last_backup_age < target_age:
            self._logger.debug(f'Backup not needed. Last backup is within the age interval ({last_backup_age} < {target_age})')
            return False

        return True
    
    def _rotate_backups(self) -> None:
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

            cmd_exec.remove(src)

        for (src, dst) in mv_list:
            if not os.path.isdir(src):
                self._logger.warn(f'Backup directory "{src}" does not exist. Can\'t move it to {dst}')
                continue

            self._logger.info(f'Moving {src} to {dst}')

            cmd_exec.move(src, dst)

    def _truncate_backup_report(self) -> None:
        report_path = os.path.join(self._backup_dst, "backup.log")

        if not os.path.isfile(report_path):
            return None

        # truncate file
        with open(report_path, 'w') as f:
            f.write("")

    def _write_backup_report(self, report: str | list) -> None:
        report_path = os.path.join(self._backup_dst, "backup.log")

        if not report:
            return None

        if not isinstance(report, list):
            report = [report]

        # append stats to file
        with open(report_path, 'a') as f:
            f.write("\n".join(report) + "\n")