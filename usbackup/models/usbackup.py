from pydantic import BaseModel, ConfigDict, model_validator, field_validator
from usbackup.models.source import SourceModel
from usbackup.models.storage import StorageModel
from usbackup.models.job import JobModel
from usbackup.handlers import handler_model_factory

class UsBackupModel(BaseModel):
    sources: list[SourceModel]
    storages: list[StorageModel]
    jobs: list[JobModel]
    notifiers: list = []

    model_config = ConfigDict(extra='forbid')
    
    @field_validator('notifiers', mode='after')
    @classmethod
    def validate_notifiers(cls, notifiers):
        parsed_notifiers = []
        
        for i, handler in enumerate(notifiers):
            if not 'handler' in handler:
                raise ValueError('Handler not specified')
            
            try:
                parsed_notifiers.append(handler_model_factory('notification', handler['handler'], **handler))
            except ImportError as e:
                raise ValueError(f'Inexistent handler "{handler["handler"]}"')
            
        return parsed_notifiers
    
    @model_validator(mode='after')
    @classmethod
    def validate_after(cls, values):
        # ensure that sources[].name is unique
        host_names = [source.name for source in values.sources]
        if len(host_names) != len(set(host_names)):
            raise ValueError('Source names must be unique')
        
        # ensure that storages[].name is unique
        storage_names = [storage.name for storage in values.storages]
        if len(storage_names) != len(set(storage_names)):
            raise ValueError('Storage names must be unique')
        
        # ensure that jobs[].name is unique
        job_names = [job.name for job in values.jobs]
        if len(job_names) != len(set(job_names)):
            raise ValueError('Job names must be unique')
            
        return values