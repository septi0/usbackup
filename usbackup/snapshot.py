import logging
import time
import shlex
import usbackup.cmd_exec as cmd_exec
import usbackup.backup_handlers as backup_handlers
import usbackup.report_handlers as report_handlers
from usbackup.snapshot_level import UsbackupSnapshotLevel
from usbackup.exceptions import UsbackupConfigError
from usbackup.backup_handlers.base import BackupHandler
from usbackup.report_handlers.base import ReportHandler

__all__ = ['UsbackupSnapshot']

class UsbackupSnapshot:
    def __init__(self, name: str, config: dict, *, logger: logging.Logger):
        self._name: str = name
        self._logger: logging.Logger = logger.getChild(self._name)

        self._cleanup_jobs: list[tuple] = []

        self._mountpoints: list[str] = shlex.split(config.get("mount", ""))
        self._backup_dst: str = self._gen_backup_dst(config)
        self._levels: list[UsbackupSnapshotLevel] = self._gen_levels(config)
        self._report_handlers: list[ReportHandler] = self._gen_report_handlers(config)
        self._pre_backup_cmd: list[str] = shlex.split(config.get("pre_backup_cmd", ""))
        self._post_backup_cmd: list[str] = shlex.split(config.get("post_backup_cmd", ""))

    @property
    def name(self) -> str:
        return self._name

    def get_levels(self) -> list:
        return self._levels
    
    def backup(self, run_time: float = None, include_manual_levels: bool = False) -> None:
        levels_to_backup = []

        if not run_time:
            run_time = time.time()

        for level in self._levels:
            if level.backup_needed(run_time, include_manual_levels):
                levels_to_backup.append(level)

        # check if we have levels to backup
        if not levels_to_backup:
            self._logger.debug("No levels to backup")
            return
        
        self._logger.info("Starting backup")

        # mount all mountpoints
        self._mount_mountpoints(self._mountpoints)

        # run pre backup command
        if self._pre_backup_cmd:
            self._logger.info("Running pre backup command")
            cmd_exec.exec_cmd(self._pre_backup_cmd)

        # backup levels that need backup
        for level in levels_to_backup:
            try:
                level.backup()
            except (Exception) as e:
                self._logger.exception(f"{level.name} level exception: {e}", exc_info=True)

        self._run_report_handlers(levels_to_backup)

        # run post backup command
        if self._post_backup_cmd:
            self._logger.info("Running post backup command")
            cmd_exec.exec_cmd(self._post_backup_cmd)

        self._logger.info("Backup finished")

    def cleanup(self) -> None:
        for (handler, args, kwargs) in self._cleanup_jobs:
            handler(*args, **kwargs)

        self._cleanup_jobs = []
    
    def _gen_backup_dst(self, config: dict) -> str:
        backup_dst = config.get("destination")

        # make sure we have a backup base
        if not backup_dst:
            raise UsbackupConfigError('No backup destination specified in config file')
        
        return backup_dst

    def _gen_levels(self, config: dict) -> list[UsbackupSnapshotLevel]:
        handlers = []

        for backup_handler in backup_handlers.list:
            if not issubclass(backup_handler, BackupHandler):
                raise TypeError(f"Backup handler {backup_handler} is not a subclass of BackupHandler")
            
            handler = backup_handler(self._name, config)

            if(bool(handler)):
                handlers.append(handler)

        backup_levels = config.get("levels")

        if not backup_levels:
            raise UsbackupConfigError('No backup levels specified in config file')
        
        backup_levels = backup_levels.strip().splitlines()

        levels = []

        for level_data in backup_levels:
            if not level_data:
                continue

            levels.append(UsbackupSnapshotLevel(level_data, backup_dst=self._backup_dst, handlers=handlers, logger=self._logger))

        return levels

    def _gen_report_handlers(self, config: dict) -> list[ReportHandler]:
        handlers = []

        for report_handler in report_handlers.list:
            if not issubclass(report_handler, ReportHandler):
                raise TypeError(f"Report handler {report_handler} is not a subclass of ReportHandler")
            
            handler = report_handler(self._name, config)

            if(bool(handler)):
                handlers.append(handler)

        return handlers

    def _mount_mountpoints(self, mountpoints: list[str]) -> None:
        # mount all mountpoints
        if mountpoints:
            self._logger.info(f"Mounting {mountpoints}")
            for mountpoint in mountpoints:
                try:
                    cmd_exec.mount(mountpoint)
                except (Exception) as e:
                    if "already mounted" in str(e):
                        self._logger.warning(f"{mountpoint} already mounted")
                    else:
                        raise e

            self._add_cleanup_job(self.unmount_mountpoints, mountpoints)

    def unmount_mountpoints(self, mountpoints: list[str]) -> None:
        # unmount all mountpoints
        if mountpoints:
            self._logger.info(f"Unmounting {mountpoints}")
            for mountpoint in mountpoints:
                try:
                    cmd_exec.umount(mountpoint)
                except (Exception) as e:
                    if "target is busy" in str(e):
                        self._logger.warning(f"{mountpoint} target is busy")
                    elif "not mounted" in str(e):
                        self._logger.warning(f"{mountpoint} not mounted")
                    else:
                        raise e
    
    def _add_cleanup_job(self, handler, *args, **kwargs) -> None:
        self._cleanup_jobs.append((handler, args, kwargs))

    def _run_report_handlers(self, levels: list) -> None:
        report = []

        for level in levels:
            report.append(level.get_backup_report())

        self._logger.info("Running report handlers")

        for handler in self._report_handlers:
            try:
                handler.report(report, logger=self._logger)
            except (Exception) as e:
                self._logger.exception(f"{handler.name} report handler exception: {e}", exc_info=True)