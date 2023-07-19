import os
import shlex
import logging
import tarfile
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_handlers.base import BackupHandler
from usbackup.remote import Remote
from usbackup.exceptions import UsbackupConfigError, HandlerError

class FilesHandler(BackupHandler):
    def __init__(self, snapshot_name: str, config: dict):
        self._name: str = 'files'
        self._snapshot_name:str = snapshot_name
        
        self._backup_src: list[str] = shlex.split(config.get("backup_files", ''))
        self._backup_src_exclude: list[str] = shlex.split(config.get("backup_files.exclude", ''))
        self._backup_src_bwlimit: str = config.get("backup_files.bwlimit")
        self._backup_src_mode: str = self._gen_backup_mode(config)

        try:
            self._backup_src_remote: Remote = Remote(config.get("backup_files.remote"), 'root', 22)
        except ValueError:
            raise UsbackupConfigError("Invalid remote provided for files")
        
        if self._backup_src_mode == 'archive' and bool(self._backup_src_remote):
            raise UsbackupConfigError("Archive mode does not support remote backup")

    def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> list:
        if not bool(self._backup_src):
            raise HandlerError(f'Handler "{self._name}" not configured')
        
        logger = logger.getChild('files')
        
        logger.info("* Backing up files")

        backup_dst = os.path.join(backup_dst, 'files')

        if not os.path.isdir(backup_dst):
            logger.info(f'Creating files backup folder "{backup_dst}"')
            cmd_exec.mkdir(backup_dst)

        if backup_dst_link:
            backup_dst_link = os.path.join(backup_dst_link, 'files')

        report = []

        if self._backup_src_mode == 'incremental':
            logger.info('Using incremental backup mode')
            report.append('Using incremental backup mode')

            report += self._backup_rsync(backup_dst, backup_dst_link, logger=logger)
        elif self._backup_src_mode == 'full':
            logger.info(f'Using full backup mode')
            report.append('Using full backup mode')

            report += self._backup_rsync(backup_dst, None, logger=logger)
        elif self._backup_src_mode == 'archive':
            logger.info(f'Using archive backup mode')
            report.append('Using archive backup mode')

            report += self._backup_tar(backup_dst, logger=logger)
        else:
            raise HandlerError('Invalid backup mode')

        return report
    
    def _gen_backup_mode(self, config: dict) -> str:
        backup_mode = config.get("backup_files.mode", 'incremental')

        if backup_mode not in ['incremental', 'archive', 'full']:
            raise UsbackupConfigError(f'Invalid backup_files.mode: "{backup_mode}"')
        
        return backup_mode
    
    def _backup_rsync(self, backup_dst: str, backup_dst_link: str, *, logger: logging.Logger) -> list[str]:
        report = []

        for dir_src in self._backup_src:
            kwargs = {}

            if bool(self._backup_src_remote):
                user = self._backup_src_remote.user
                host = self._backup_src_remote.host

                dir_src = f'{user}@{host}:{dir_src}'
                if self._backup_src_remote.password:
                    kwargs['password'] = self._backup_src_remote.password

            logger.info(f'Copying "{dir_src}" to "{backup_dst}"')
            report += [f'* "{dir_src}" -> "{backup_dst}"', '']

            options = [
                'archive',
                'hard-links',
                'acls',
                'xattrs',
                'delete',
                'delete-during',
                'stats',
                # 'verbose',
                'relative',
                ('out-format', "%t %i %f"),
            ]

            if self._backup_src_exclude:
                for exclude_dir in self._backup_src_exclude:
                    options.append(('exclude', exclude_dir))

            if bool(self._backup_src_remote):
                options.append(f'rsh=ssh -p {self._backup_src_remote.port}')

            if self._backup_src_bwlimit:
                options.append(('bwlimit', str(self._backup_src_bwlimit)))

            if backup_dst_link:
                options.append(('link-dest', backup_dst_link))

            report_line = cmd_exec.rsync(dir_src, backup_dst, options=options, **kwargs)

            report_line = report_line.splitlines()

            if len(report_line) >= 16:
                report_line = "\n".join(report_line[-16:])

            logger.debug(f'rsync output: {report_line}')
            report += [str(report_line), '']

        return report
    
    def _backup_tar(self, backup_dst: str, *, logger: logging.Logger) -> list[str]:
        report = []
        destination_archive = os.path.join(backup_dst, f'{self._snapshot_name}.tar.gz')
        sources = []

        for src_dir in self._backup_src:
            if bool(self._backup_src_remote):
                raise HandlerError('Archive mode does not support remote backup')

            sources.append(src_dir)

        if not sources:
            raise HandlerError('No sources to archive')
        
        logger.info(f'Archiving "{sources}" to "{destination_archive}"')
        report += [f'* "{sources}" -> "{destination_archive}"', '']

        report_line = cmd_exec.tar(destination_archive, sources)

        logger.debug(f'tar output: {report_line}')
        report += [str(report_line), '']

        return report
    
    def __bool__(self) -> bool:
        return bool(self._backup_src)
    
    @property
    def name(self) -> str:
        return self._name