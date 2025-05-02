from pydantic import BaseModel, ConfigDict, Field, model_validator
from usbackup.handlers import handler_factory
from usbackup.models.remote import RemoteModel

__all__ = ['UsBackupHostModel']

class UsBackupHostModel(BaseModel):
    name: str
    host: RemoteModel
    dest: str
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
            
            # Dynamically load the handler class
            handler_model = handler_factory('backup', name=handler['handler'], entity='model')
            
            # Validate the handler model
            parsed_values.append(handler_model(**handler))
            
        values.handlers = parsed_values
            
        return values