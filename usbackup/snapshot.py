import logging
import datetime
import shlex
import usbackup.cmd_exec as cmd_exec
import usbackup.backup_handlers as backup_handlers
import usbackup.report_handlers as report_handlers
from usbackup.jobs_queue import JobsQueue
from usbackup.snapshot_level import UsBackupSnapshotLevel
from usbackup.exceptions import UsbackupConfigError
from usbackup.backup_handlers.base import BackupHandler
from usbackup.report_handlers.base import ReportHandler

__all__ = ['UsBackupSnapshot']

class UsBackupSnapshot:
    def __init__(self, name: str, config: dict, *, cleanup: JobsQueue, logger: logging.Logger):
        self._name: str = name
        self._cleanup: JobsQueue = cleanup
        self._logger: logging.Logger = logger.getChild(self._name)

        self._mountpoints: list[str] = shlex.split(config.get("mount", ""))
        self._backup_dst: str = self._gen_backup_dst(config)
        self._levels: list[UsBackupSnapshotLevel] = self._gen_levels(config)
        self._report_handlers: list[ReportHandler] = self._gen_report_handlers(config)
        self._pre_backup_cmd: list[str] = shlex.split(config.get("pre_backup_cmd", ""))
        self._post_backup_cmd: list[str] = shlex.split(config.get("post_backup_cmd", ""))
        self._concurrency_group: str = config.get("concurrency_group", "")

    @property
    def name(self) -> str:
        return self._name

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @property
    def levels(self) -> list:
        return self._levels

    @property
    def concurrency_group(self) -> str:
        return self._concurrency_group
    
    async def backup(self, *, exclude: list = []) -> None:
        levels_to_backup = []

        snapshot_run_time = datetime.datetime.now()

        self._logger.debug(f"Checking backup for time {snapshot_run_time}")

        for level in self._levels:
            backup_needed = await level.backup_needed(exclude=exclude)
            if backup_needed:
                levels_to_backup.append(level)

        # check if we have levels to backup
        if not levels_to_backup:
            self._logger.debug("No levels to backup")
            return
        
        self._logger.info("Starting backup")

        # run pre backup command
        if self._pre_backup_cmd:
            self._logger.info("Running pre backup command")
            await cmd_exec.exec_cmd(self._pre_backup_cmd)

        job_name = f'snapshot_{self._name}_mountpoints'

        # mount all mountpoints
        await self._mount_mountpoints()

        # add umount_mountpoints to cleanup queue
        self._cleanup.add_job(job_name, self._umount_mountpoints)

        # backup levels that need backup
        for level in levels_to_backup:
            try:
                await level.backup()
            except (Exception) as e:
                level.logger.exception(e, exc_info=True)

        await self._run_report_handlers(levels_to_backup)

        # remove umount_mountpoints from cleanup queue
        self._cleanup.remove_job(job_name)

        # unmount all mountpoints
        await self._umount_mountpoints()

        # run post backup command
        if self._post_backup_cmd:
            self._logger.info("Running post backup command")
            await cmd_exec.exec_cmd(self._post_backup_cmd)

        self._logger.info("Backup finished")

    async def du(self) -> dict:
        output = {
            'total': 0,
            'levels': {}
        }

        job_name = f'snapshot_{self._name}_mountpoints'

        # mount all mountpoints
        await self._mount_mountpoints()

        # add umount_mountpoints to cleanup queue
        self._cleanup.add_job(job_name, self._umount_mountpoints)

        for level in self._levels:
            level_usage = await level.du()

            if level_usage.get('versions'):
                output['total'] += level_usage['total']
                output['levels'][level.name] = level_usage

        # remove umount_mountpoints from cleanup queue
        self._cleanup.remove_job(job_name)

        # unmount all mountpoints
        await self._umount_mountpoints()

        return output
    
    def _gen_backup_dst(self, config: dict) -> str:
        backup_dst = config.get("destination")

        # make sure we have a backup base
        if not backup_dst:
            raise UsbackupConfigError('No backup destination specified in config file')
        
        return backup_dst

    def _gen_levels(self, config: dict) -> list[UsBackupSnapshotLevel]:
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

            levels.append(UsBackupSnapshotLevel(level_data, backup_dst=self._backup_dst, handlers=handlers, logger=self._logger))

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

    async def _mount_mountpoints(self) -> None:
        if not self._mountpoints:
            return
        
        self._logger.info(f"Mounting {self._mountpoints}")

        for mountpoint in self._mountpoints:
            try:
                await cmd_exec.mount(mountpoint)
            except (Exception) as e:
                if "already mounted" in str(e):
                    self._logger.warning(f"{mountpoint} already mounted")
                else:
                    raise e from None

    async def _umount_mountpoints(self) -> None:
        if not self._mountpoints:
            return
        
        self._logger.info(f"Unmounting {self._mountpoints}")
        
        for mountpoint in self._mountpoints:
            try:
                await cmd_exec.umount(mountpoint)
            except (Exception) as e:
                if "target is busy" in str(e):
                    self._logger.warning(f"{mountpoint} target is busy")
                elif "not mounted" in str(e):
                    self._logger.warning(f"{mountpoint} not mounted")
                else:
                    raise e from None

    async def _run_report_handlers(self, levels: list) -> None:
        report = []

        for level in levels:
            report.append(await level.get_backup_report())

        self._logger.info("Running report handlers")

        for handler in self._report_handlers:
            try:
                await handler.report(report, logger=self._logger)
            except (Exception) as e:
                self._logger.exception(f"{handler.name} report handler exception: {e}", exc_info=True)