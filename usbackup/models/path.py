import re
import os
from typing import Literal
from pydantic import BaseModel, ConfigDict, model_validator
from usbackup.models.host import HostModel

class PathModel(BaseModel):
    path: str
    host: HostModel
    
    model_config = ConfigDict(extra='forbid')
    
    @model_validator(mode='before')
    @classmethod
    def validate_before(cls, values):
        if not isinstance(values, str):
            return values
        
        pattern = r'^(?P<host>[^\/]+)?(?P<path>\/.*)$'

        match = re.match(pattern, values)
        
        if not match:
            raise ValueError('Invalid path string provided')
        
        parsed_values = {}
        
        parsed_values['path'] = match.group('path')

        if match.group('host'):
            parsed_values['host'] = match.group('host')
        else:
            parsed_values['host'] = 'localhost'
        
        return parsed_values
    
    def join(self, path: str) -> 'PathModel':
        model = self.model_copy()
        model.path = os.path.join(self.path, path)
        
        return model
    
    def __str__(self) -> str:
        if self.host.local:
            return self.path
        else:
            return f'{self.host}{self.path}'