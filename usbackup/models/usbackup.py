from pydantic import BaseModel, ConfigDict, model_validator
from usbackup.models.source import UsBackupSourceModel
from usbackup.models.storage import UsBackupStorageModel
from usbackup.models.job import UsBackupJobModel
from usbackup.handlers import handler_model_factory

__all__ = ['UsBackupModel']

class UsBackupModel(BaseModel):
    sources: list[UsBackupSourceModel]
    storages: list[UsBackupStorageModel]
    jobs: list[UsBackupJobModel] = []
    notifiers: list = []

    model_config = ConfigDict(extra='forbid')
    
    @model_validator(mode='after')
    @classmethod
    def validate_handler(cls, values): 
        # ensure that sources[].name is unique
        host_names = [source.name for source in values.sources]
        if len(host_names) != len(set(host_names)):
            raise ValueError('Source names must be unique')
        
        # ensure that jobs[].name is unique
        job_names = [job.name for job in values.jobs]
        if len(job_names) != len(set(job_names)):
            raise ValueError('Job names must be unique')
        
        handlers = values.notifiers
        
        parsed_values = []
        
        for handler in handlers:
            if not 'handler' in handler:
                raise ValueError('Handler not specified')
            
            # Validate the handler model
            parsed_values.append(handler_model_factory('notification', handler['handler'], **handler))
            
        values.notifiers = parsed_values
            
        return values