from pydantic import BaseModel, ConfigDict, Field, model_validator
from usbackup.models.host import UsBackupHostModel
from usbackup.models.job import UsBackupJobModel
from usbackup.handlers import handler_factory

__all__ = ['UsBackupModel']

class UsBackupModel(BaseModel):
    # the hosts name must be unique
    hosts: list[UsBackupHostModel]
    jobs: list[UsBackupJobModel] = []
    notifiers: list = []

    model_config = ConfigDict(extra='forbid')
    
    @model_validator(mode='after')
    @classmethod
    def validate_handler(cls, values): 
        # ensure that hosts[].name is unique
        host_names = [host.name for host in values.hosts]
        if len(host_names) != len(set(host_names)):
            raise ValueError('Host names must be unique')
        
        # ensure that jobs[].name is unique
        job_names = [job.name for job in values.jobs]
        if len(job_names) != len(set(job_names)):
            raise ValueError('Job names must be unique')
        
        handlers = values.notifiers
        
        parsed_values = []
        
        for handler in handlers:
            if not 'handler' in handler:
                raise ValueError('Handler not specified')
            
            # Dynamically load the handler class
            handler_model = handler_factory('notification', name=handler['handler'], entity='model')
            
            # Validate the handler model
            parsed_values.append(handler_model(**handler))
            
        values.notifiers = parsed_values
            
        return values