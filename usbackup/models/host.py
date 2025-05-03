import socket
import re
from pydantic import BaseModel, ConfigDict, model_validator
from usbackup.libraries.cmd_exec import CmdExecHostModel

__all__ = ['HostModel']

"""
Allwed remote formats:
    - hostname
    - hostname:port
    - username@hostname
    - username@hostname:port
    - username:password@hostname:port
    - username:password@hostname
"""

class HostModel(BaseModel, CmdExecHostModel):
    model_config = ConfigDict(extra='forbid')
    
    @model_validator(mode='before')
    @classmethod
    def validate_handler(cls, values):
        if not isinstance(values, str):
            raise ValueError('Invalid remote string provided')
        
        pattern = r'^(?:(?P<username>[^:@]+)(?::(?P<password>[^@]+))?@)?(?P<hostname>[^:/]+)(?::(?P<port>\d+))?$'

        match = re.match(pattern, values)

        if not match:
            raise ValueError('Invalid remote string provided')
        
        parsed_values = {}
        
        parsed_values['host'] = match.group('hostname')
        parsed_values['local'] = True if (parsed_values['host'] == socket.gethostname() or parsed_values['host'] == 'localhost') else False
        
        if match.group('username'): parsed_values['user'] = match.group('username')
        if match.group('password'): parsed_values['password'] = match.group('password')
        if match.group('port'): parsed_values['port'] = int(match.group('port'))
        
        return parsed_values
    
    def __str__(self) -> str:
        return self.host