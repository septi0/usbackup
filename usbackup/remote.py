import socket
import re

__all__ = ['Remote']

"""
Allwed remote formats:
    - hostname
    - hostname:port
    - username@hostname
    - username@hostname:port
    - username:password@hostname:port
    - username:password@hostname
"""

class Remote:
    def __init__(self, remote: str, default_user: str = '', default_port: int = 0, default_password: str = ''):
        self._host: str = None
        self._user: str
        self._password: str
        self._port: int
        self._local: bool

        if remote:
            pattern = r'^(?:(?P<username>[^:@]+)(?::(?P<password>[^@]+))?@)?(?P<hostname>[^:/]+)(?::(?P<port>\d+))?$'

            match = re.match(pattern, remote)

            if not match:
                raise ValueError('Invalid remote string')

            self._host = match.group('hostname')
            self._user = match.group('username') or default_user
            self._password = match.group('password') or default_password
            self._port = match.group('port') or default_port

            self._local = True if (self._host == socket.gethostname() or self._host == 'localhost') else False

    @property
    def host(self) -> str:
        return self._host
    
    @property
    def user(self) -> str:
        return self._user
    
    @property
    def password(self) -> str:
        return self._password
    
    @property
    def port(self) -> int:
        return self._port

    @property
    def local(self) -> bool:
        return self._local
    
    def __str__(self) -> str:
        return f"{self._user}@{self._host}"
    
    def __bool__(self) -> bool:
        return self._host is not None