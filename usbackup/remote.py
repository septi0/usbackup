import re

__all__ = ['Remote']

class Remote:
    def __init__(self, remote: str, default_user: str = '', default_port: int = 0, default_password: str = ''):
        self._host: str
        self._user: str
        self._port: int
        self._password: str

        if remote:
            pattern = r'^(?:(?P<username>[^@]+)@)?(?P<hostname>[^:/]+)(?::(?P<port>\d+))?(?:/(?P<password>.+))?$'

            match = re.match(pattern, remote)

            if not match:
                raise ValueError('Invalid remote string')

            self._host = match.group('hostname')
            self._user = match.group('username') or default_user
            self._port = match.group('port') or default_port
            self._password = match.group('password') or default_password

    @property
    def host(self) -> str:
        return self._host
    
    @property
    def user(self) -> str:
        return self._user
    
    @property
    def port(self) -> int:
        return self._port
    
    @property
    def password(self) -> str:
        return self._password
    
    def __str__(self) -> str:
        return f"{self._user}@{self._host}"
    
    def __bool__(self) -> bool:
        return self._host is not None