from pydantic import BaseModel, ConfigDict, model_validator
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
    
    @model_validator(mode='after')
    @classmethod
    def validate(cls, values):
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
        
        # add dynamic notification handlers
        parsed_notifiers = []
        
        for handler in values.notifiers:
            if not 'handler' in handler:
                raise ValueError('Handler not specified')
            
            # Validate the handler model
            parsed_notifiers.append(handler_model_factory('notification', handler['handler'], **handler))
            
        values.notifiers = parsed_notifiers
        
        # add models for dest and replicate for each job
        for i, job in enumerate(values.jobs):
            values.jobs[i].dest = next((storage for storage in values.storages if storage.name == job.dest), None)
            
            if not values.jobs[i].dest:
                raise ValueError(f'Job "{job.name}" has inexistent destination storage')
            
            if job.replicate:
                values.jobs[i].replicate = next((storage for storage in values.storages if storage.name == job.replicate), None)
                
                if not values.jobs[i].replicate:
                    raise ValueError(f'Job "{job.name}" has inexistent replication storage')
            
        return values