from pydantic import BaseModel, ConfigDict, field_validator
from usbackup.handlers import handler_model_factory
from usbackup.models.host import HostModel

class SourceModel(BaseModel):
    name: str
    host: HostModel
    handlers: list
    
    model_config = ConfigDict(extra='forbid')
    
    @field_validator('handlers', mode='after')
    @classmethod
    def validate_handlers(cls, handlers):
        parsed_values = []
        
        for i, handler in enumerate(handlers):
            if not 'handler' in handler:
                raise ValueError(f'Handler not specified')
            
            try:
                parsed_values.append(handler_model_factory('backup', handler['handler'], **handler))
            except ImportError as e:
                raise ValueError(f'Inexistent handler "{handler["handler"]}"')
        
        # the commands of a source write into the same folder, so their files must not overwrite each other
        files = [handler.output_file for handler in parsed_values if handler.handler == 'command']
        duplicates = sorted({file for file in files if files.count(file) > 1})
        
        if duplicates:
            raise ValueError(f'Command handlers write the same file: {", ".join(duplicates)}')
        
        return parsed_values