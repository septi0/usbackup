import logging
import datetime
import shlex
import asyncio
import hashlib
import re
import usbackup.cmd_exec as cmd_exec
import usbackup.backup_handlers as backup_handlers
import usbackup.report_handlers as report_handlers
from usbackup.remote import Remote
from usbackup.jobs_queue import JobsQueue
from usbackup.file_cache import FileCache
from usbackup.snapshot_level import UsBackupSnapshotLevel
from usbackup.exceptions import UsbackupConfigError
from usbackup.backup_handlers.base import BackupHandler
from usbackup.report_handlers.base import ReportHandler

__all__ = ['UsBackupSnapshot']

class UsBackupSnapshot:
    def __init__(self, name: str, config: dict, *, cleanup: JobsQueue, cache: FileCache, logger: logging.Logger):
        self._name: str = name

        self._cleanup: JobsQueue = cleanup
        self._cache: FileCache = cache
        self._logger: logging.Logger = logger.getChild(self._name)

        self._mountpoints: list[str] = shlex.split(config.get("mount", ""))
        self._dest: str = self._gen_dest(config)
        self._src_host: Remote = self._gen_src_host(config)
        self._levels: list[UsBackupSnapshotLevel] = self._gen_levels(config)
        self._report_handlers: list[ReportHandler] = self._gen_report_handlers(config)
        self._pre_backup_cmd: list[str] = shlex.split(config.get("pre_backup_cmd", ""))
        self._post_backup_cmd: list[str] = shlex.split(config.get("post_backup_cmd", ""))
        self._concurrency_group: str = config.get("concurrency_group", "")

        self._id: str = hashlib.md5(self._name.encode()).hexdigest()

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
    
    async def backup_if_needed(self, *, exclude: list = []) -> None:
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

        await self._ensure_mountpoints()

        if len(levels_to_backup) > 1:
            self._logger.warning('More than one level to backup. Performance may be degraded')

        # run pre backup command
        if self._pre_backup_cmd:
            self._logger.info("Running pre backup command")
            await cmd_exec.exec_cmd(self._pre_backup_cmd)

        tasks = []
        finalized_backups = []

        # backup levels
        for (index, level) in enumerate(levels_to_backup):
            tasks.append(asyncio.create_task(level.backup(), name=index))

        await asyncio.gather(*tasks, return_exceptions=True)

        for task in tasks:
            level = levels_to_backup[int(task.get_name())]

            if isinstance(task.exception(), Exception):
                level.logger.exception(task.exception(), exc_info=True)
            else:
                finalized_backups.append(level)

        await self._run_report_handlers(finalized_backups)

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

        await self._ensure_mountpoints()

        for level in self._levels:
            level_usage = await level.du()

            if level_usage.get('versions'):
                output['total'] += level_usage['total']
                output['levels'][level.name] = level_usage

        return output
    
    def _gen_dest(self, config: dict) -> str:
        dest = config.get("dest")

        # make sure we have a backup base
        if not dest:
            raise UsbackupConfigError('No backup dest specified in config file')
        
        return dest
    
    def _gen_src_host(self, config: dict) -> Remote:
        src_host = config.get('src-host', 'localhost')

        try:
            return Remote(src_host)
        except ValueError:
            raise UsbackupConfigError('Invalid src-host provided for backup')

    def _gen_levels(self, config: dict) -> list[UsBackupSnapshotLevel]:
        handlers = []

        for backup_handler in backup_handlers.list:
            if not issubclass(backup_handler, BackupHandler):
                raise TypeError(f"Backup handler {backup_handler} is not a subclass of BackupHandler")
            
            handler_config = self._gen_handler_config('backup', backup_handler.handler, config)
            handler = backup_handler(self._src_host, self._name, handler_config)

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

            levels.append(UsBackupSnapshotLevel(level_data, dest=self._dest, handlers=handlers, cleanup=self._cleanup, cache=self._cache, logger=self._logger))

        return levels

    def _gen_report_handlers(self, config: dict) -> list[ReportHandler]:
        handlers = []

        for report_handler in report_handlers.list:
            if not issubclass(report_handler, ReportHandler):
                raise TypeError(f"Report handler {report_handler} is not a subclass of ReportHandler")
            
            handler_config = self._gen_handler_config('report', report_handler.handler, config)
            handler = report_handler(self._name, handler_config)

            if(bool(handler)):
                handlers.append(handler)

        return handlers
    
    def _gen_handler_config(self, type: str, handler: str, config: dict) -> dict:
        # return only keys that start with type.handler
        return {k: v for k, v in config.items() if re.match(f"{type}\.{handler}($|\.)", k)}

    async def _ensure_mountpoints(self) -> None:
        if not self._mountpoints:
            return
        
        for mountpoint in self._mountpoints:
            try:
                await cmd_exec.mounted(mountpoint)
                continue
            except (Exception) as e:
                pass
        
            self._logger.info(f"Mounting {mountpoint}")

            await cmd_exec.mount(mountpoint)

    async def _run_report_handlers(self, levels: list) -> None:
        report = []

        if not levels:
            return

        for level in levels:
            report.append(await level.get_backup_report())

        self._logger.info("Running report handlers")

        for handler in self._report_handlers:
            try:
                await handler.report(report, logger=self._logger)
            except (Exception) as e:
                self._logger.exception(f"{handler.name} report handler exception: {e}", exc_info=True)