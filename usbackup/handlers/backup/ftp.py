import os
import ssl
import datetime
import aioftp
from typing import Literal
from aioftp.client import ListInfo
from usbackup.models.path import PathModel
from usbackup.handlers.backup import HandlerBaseModel, BackupHandler, BackupHandlerError


class FtpHandlerModel(HandlerBaseModel):
    handler: str = 'ftp'
    limit: list[str] = []
    exclude: list[str] = []
    tls: bool = False
    mode: Literal['incremental', 'full'] = 'incremental'
    user: str | None = None
    password: str | None = None


class FtpHandler(BackupHandler):
    handler: str = 'ftp'

    def __init__(self, model: FtpHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)

        self._src_paths: list[str] = self._gen_src_paths(model.limit)
        self._exclude: list[str] = model.exclude
        self._tls: bool = model.tls
        self._mode: str = model.mode
        self._user: str | None = model.user
        self._password: str | None = model.password

    async def backup(self, dest: PathModel, dest_link: PathModel | None = None) -> None:
        host = self._host.host
        port = 990 if self._tls else 21
        user = self._user or 'anonymous'
        password = self._password or ''

        ssl_context = ssl.create_default_context() if self._tls else None

        self._logger.info(f'Connecting to FTP{"S" if self._tls else ""} server "{host}:{port}"')

        if self._mode == 'incremental':
            self._logger.info('Using incremental backup mode')
        else:
            self._logger.info('Using full backup mode')

        async with aioftp.Client.context(host, port=port, user=user, password=password, ssl=ssl_context) as list_client:
            async with aioftp.Client.context(host, port=port, user=user, password=password, ssl=ssl_context) as download_client:
                for src_path in self._src_paths:
                    self._logger.info(f'Downloading "{src_path}" from "{host}"')
                    await self._download_path(list_client, download_client, src_path, dest, dest_link)

    async def _download_path(self, list_client: aioftp.Client, download_client: aioftp.Client, src_path: str, dest: PathModel, dest_link: PathModel | None = None) -> None:
        try:
            async for remote_path, info in list_client.list(src_path, recursive=True):
                remote_path_str = str(remote_path)

                if self._is_excluded(remote_path_str):
                    self._logger.debug(f'Skipping excluded path "{remote_path_str}"')
                    continue

                if info['type'] == 'file':
                    relative_path = remote_path_str.lstrip('/')
                    local_path = dest.join(relative_path)
                    local_dir = os.path.dirname(local_path.path)

                    os.makedirs(local_dir, exist_ok=True)

                    if self._mode == 'incremental' and dest_link is not None:
                        link_path = dest_link.join(relative_path)

                        if self._can_hardlink(link_path.path, info):
                            self._logger.debug(f'Hard-linking "{remote_path_str}" from previous backup')
                            os.link(link_path.path, local_path.path)
                            continue

                    self._logger.debug(f'Downloading "{remote_path_str}"')

                    await download_client.download(remote_path_str, local_path.path, write_into=True)
                    self._stamp_mtime(local_path.path, info)
        except aioftp.StatusCodeError as e:
            raise BackupHandlerError(f'Failed to download FTP path "{src_path}": {e}', 1040)

    def _can_hardlink(self, local_path: str, info: ListInfo) -> bool:
        if not os.path.isfile(local_path):
            return False

        remote_size = int(info.get('size', -1))
        remote_mtime = self._parse_mtime(info.get('modify', ''))

        if remote_size < 0 or remote_mtime is None:
            return False

        stat = os.stat(local_path)

        size_match = stat.st_size == remote_size
        mtime_match = abs(stat.st_mtime - remote_mtime.timestamp()) <= 1

        return size_match and mtime_match

    def _stamp_mtime(self, local_path: str, info: ListInfo) -> None:
        remote_mtime = self._parse_mtime(info.get('modify', ''))

        if remote_mtime is not None:
            mtime_ts = remote_mtime.timestamp()
            os.utime(local_path, (mtime_ts, mtime_ts))

    def _parse_mtime(self, modify: str) -> datetime.datetime | None:
        for fmt in ('%Y%m%d%H%M%S', '%Y%m%d%H%M%S.%f'):
            try:
                return datetime.datetime.strptime(modify, fmt).replace(tzinfo=datetime.timezone.utc)
            except (ValueError, TypeError):
                continue
        return None

    def _gen_src_paths(self, limit: list[str]) -> list[str]:
        src_paths = []

        if limit:
            for src in limit:
                # make sure all sources are absolute paths
                if not os.path.isabs(src):
                    raise BackupHandlerError(f'Invalid limit "{src}". Path must be absolute', 1042)

                # make sure paths end with a slash
                if not src.endswith('/'):
                    src += '/'

                src_paths.append(src)
        else:
            src_paths = ['/']

        return src_paths

    def _is_excluded(self, path: str) -> bool:
        for exclude in self._exclude:
            if path == exclude or path.startswith(exclude.rstrip('/') + '/'):
                return True
        return False
