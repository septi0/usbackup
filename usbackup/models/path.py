import re
import os
import urllib.parse
from typing import Literal
from pydantic import BaseModel, ConfigDict, model_validator
from usbackup.models.host import HostModel

class PathModel(BaseModel):
    path: str
    host: HostModel
    protocol: Literal["local_fs", "ssh"] | None = None
    params: dict[str, str] = {}

    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='before')
    @classmethod
    def validate_before(cls, values):
        if not isinstance(values, str):
            return values

        pattern = r'^(?:(?P<protocol>[a-z0-9+\-]+)://)?(?P<host>[^\/]+)?(?P<path>\/[^?]*)(?:\?(?P<params>[^#]*))?$'

        match = re.match(pattern, values)

        if not match:
            raise ValueError('Invalid path string provided')

        parsed_values = {}

        parsed_values['path'] = match.group('path')

        if match.group('host'):
            parsed_values['host'] = match.group('host')
        else:
            parsed_values['host'] = 'localhost'

        parsed_values["protocol"] = match.group("protocol") if match.group("protocol") else None
        parsed_values['params'] = dict(urllib.parse.parse_qsl(match.group('params'))) if match.group('params') else {}

        return parsed_values
    
    @model_validator(mode='after')
    @classmethod
    def validate_after(cls, values):
        if values.protocol is None:
            values.protocol = "local_fs" if values.host.host == "localhost" else "ssh"
            
        if values.protocol == "local_fs" and values.host.host != "localhost":
            raise ValueError('Local filesystem protocol can only be used with localhost')
            
        return values

    def join(self, path: str) -> 'PathModel':
        model = self.model_copy()
        model.path = os.path.join(self.path, path)

        return model

    def __str__(self) -> str:
        if self.protocol == "local_fs":
            return self.path
        else:
            return f'{self.host}{self.path}'