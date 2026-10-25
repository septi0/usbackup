import shlex
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator, field_validator
from usbackup.models.retention_policy import RetentionPolicyModel
    
class JobModel(BaseModel):
    name: str
    type: Literal['backup', 'replication'] = 'backup'
    dest: str
    limit: list[str] = []
    exclude: list[str] = []
    schedule: str = Field('0 0 * * *', pattern=r'^(\*|(\d+|\*\/\d+|\d+-\d+|\d+(,\d+)*))(\s+(\*|(\d+|\*\/\d+|\d+-\d+|\d+(,\d+)*))){4}$')
    retention_policy: RetentionPolicyModel | None = None
    sources_retention_policy: dict[str, RetentionPolicyModel] = {}
    notification_policy: Literal['never', 'always', 'on-failure'] = 'always'
    concurrency: int = Field(1, ge=1)
    replication_mode: Literal['incremental', 'full', 'archive'] = 'incremental'
    pre_run_cmd: list | None = None
    post_run_cmd: list | None = None
    replicate: str | None = None

    model_config = ConfigDict(extra='forbid')

    @model_validator(mode='before')
    @classmethod
    def validate_before(cls, values):
        if 'pre_run_cmd' in values and isinstance(values['pre_run_cmd'], str):
            values['pre_run_cmd'] = shlex.split(values['pre_run_cmd'])
            
        if 'post_run_cmd' in values and isinstance(values['post_run_cmd'], str):
            values['post_run_cmd'] = shlex.split(values['post_run_cmd'])
            
        return values
    
    @field_validator('schedule', mode='after')
    @classmethod
    def validate_schedule(cls, schedule):
        # weekdays accept 7 as sunday, like cron
        limits = [('minute', 0, 59), ('hour', 0, 23), ('day', 1, 31), ('month', 1, 12), ('weekday', 0, 7)]
        
        for field, (name, minimum, maximum) in zip(schedule.split(), limits):
            for item in field.split(','):
                if item == '*':
                    continue
                
                if item.startswith('*/'):
                    if int(item[2:]) < 1:
                        raise ValueError(f'Invalid {name} step "{item}", the step must be at least 1')
                    
                    continue
                
                start, _, end = item.partition('-')
                values = [int(start), int(end)] if end else [int(start)]
                
                if any(value < minimum or value > maximum for value in values) or values[0] > values[-1]:
                    raise ValueError(f'Invalid {name} value "{item}", expected values between {minimum} and {maximum}')
        
        return schedule
    
    @field_validator('sources_retention_policy', mode='before')
    @classmethod
    def validate_sources_retention_policy(cls, sources_retention_policy):
        if not sources_retention_policy:
            raise ValueError('Sources retention policy must define at least one source')
        
        return sources_retention_policy
    
    @model_validator(mode='after')
    @classmethod
    def validate_after(cls, values):
        if values.type == 'replication':
            if not values.replicate:
                raise ValueError('For "replication" type jobs, the "replicate" field is mandatory (it should contain the name of a storage)')
            
            if values.replicate == values.dest:
                raise ValueError('Replication job cannot replicate to the same storage as the source')
            
        excluded_sources = [name for name in values.sources_retention_policy if name in values.exclude]
        if excluded_sources:
            raise ValueError(f'Sources retention policy references sources excluded from the job: {", ".join(excluded_sources)}')
        
        if values.limit:
            unlisted_sources = [name for name in values.sources_retention_policy if name not in values.limit]
            if unlisted_sources:
                raise ValueError(f'Sources retention policy references sources missing from the job limit list: {", ".join(unlisted_sources)}')
        
        return values