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
            
        # ensure that jobs reference existing storages and sources, so typos are reported by configtest
        for job in values.jobs:
            if job.dest not in storage_names:
                raise ValueError(f'Job "{job.name}" references inexistent destination storage "{job.dest}"')

            if job.type == 'replication' and job.replicate not in storage_names:
                raise ValueError(f'Job "{job.name}" references inexistent replication storage "{job.replicate}"')

            unknown_sources = [name for name in [*job.limit, *job.exclude] if name not in host_names]
            if unknown_sources:
                raise ValueError(f'Job "{job.name}" limit/exclude references inexistent sources: {", ".join(unknown_sources)}')

            unknown_sources = [name for name in job.sources_retention_policy if name not in host_names]
            if unknown_sources:
                raise ValueError(f'Job "{job.name}" sources retention policy references inexistent sources: {", ".join(unknown_sources)}')
        
        # ensure that remote storages are only used as replication destinations
        storages = {storage.name: storage for storage in values.storages}
        for job in values.jobs:
            dest = storages.get(job.dest)
            if job.type == 'backup' and dest and dest.path.protocol != 'local_fs':
                raise ValueError(f'Job "{job.name}" backs up to remote storage "{job.dest}". Remote storages can only be used as replication destinations')
            
            replicate = storages.get(job.replicate) if job.replicate else None
            if job.type == 'replication' and replicate and replicate.path.protocol != 'local_fs':
                raise ValueError(f'Job "{job.name}" replicates from remote storage "{job.replicate}". Replication sources must be local storages')
        
        return values