import aiohttp
from usbackup.libraries.fs_adapter import FsAdapter
from usbackup.models.path import PathModel
from usbackup.handlers.backup import HandlerBaseModel, BackupHandler, BackupHandlerError

class UnifiHandlerModel(HandlerBaseModel):
    handler: str = 'unifi'
    user: str | None = None
    password: str | None = None

class UnifiHandler(BackupHandler):
    handler: str = 'unifi'

    def __init__(self, model: UnifiHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)
        
        self._user: str | None = model.user
        self._password: str | None = model.password

    async def backup(self, dest: PathModel, dest_link: PathModel | None = None) -> None:
        self._logger.debug(f'Creating session for Unifi controller at "{self._host}"')
        
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
            login_url = f'https://{self._host}/api/auth/login'
            login_data = {'username': self._user, 'password': self._password}
            
            self._logger.info(f'Authenticating to Unifi controller at "{self._host}"')
            
            async with session.post(login_url, json=login_data, ssl=False) as resp:
                if resp.status != 200:
                    raise BackupHandlerError(f'Failed to authenticate to Unifi controller: {resp.status}', 1001)

                self._logger.info('Authentication successful')
                
                # get csrf token
                csrf_token = resp.headers.get('X-Csrf-Token')

                if not csrf_token:
                    raise BackupHandlerError('CSRF token not found in response headers', 1003)
                
                # get cookies from set-cookie headers
                cookie = resp.headers.get('Set-Cookie', '').split(';')[0].strip()

            backup_url = f'https://{self._host}/api/backup/download'
            backup_headers = {
                'X-Csrf-Token': csrf_token,
                'Cookie': cookie,
            }

            self._logger.info(f'Getting backup file from Unifi controller at "{self._host}"')

            # get backup file
            async with session.get(backup_url, headers=backup_headers, ssl=False) as resp:
                if resp.status != 200:
                    raise BackupHandlerError(f'Failed to download backup: {resp.status}', 1002)

                self._logger.info('Backup download successful')
                
                # save backup file
                with FsAdapter.open(dest.join('unifi_backup.unifi'), 'wb') as f:
                    content = await resp.read()
                    f.write(content)
                    self._logger.info(f'Backup saved to "{dest.path}"')