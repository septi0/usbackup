from pydantic import BaseModel, ConfigDict, Field, model_validator
from usbackup.handlers import handler_model_factory
from usbackup.models.host import HostModel

__all__ = ['UsBackupSourceModel']

class UsBackupSourceModel(BaseModel):
    name: str
    host: HostModel
    handlers: list
    
    model_config = ConfigDict(extra='forbid')
    
    @model_validator(mode='after')
    @classmethod
    def validate_handler(cls, values):
        handlers = values.handlers
        
        parsed_values = []
        
        for handler in handlers:
            if not 'handler' in handler:
                raise ValueError('Handler not specified')
            
            # Validate the handler model
            parsed_values.append(handler_model_factory('backup', handler['handler'], **handler))
            
        values.handlers = parsed_values
            
        return values