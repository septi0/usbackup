import shlex
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from usbackup.models.retention_policy import RetentionPolicyModel
    
class JobModel(BaseModel):
    name: str
    type: Literal['backup', 'replication'] = 'backup'
    dest: str
    limit: list[str] = []
    exclude: list[str] = []
    schedule: str = Field('0 0 * * *', pattern=r'^(\*|(\d+|\*\/\d+|\d+-\d+|\d+(,\d+)*))(\s+(\*|(\d+|\*\/\d+|\d+-\d+|\d+(,\d+)*))){4}$')
    retention_policy: RetentionPolicyModel | None = None
    notification_policy: Literal['never', 'always', 'on-failure'] = 'always'
    concurrency: int = Field(1, ge=1)
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
    
    @model_validator(mode='after')
    @classmethod
    def validate_after(cls, values):
        if values.type == 'replication':
            if not values.replicate:
                raise ValueError('For "replication" type jobs, the "replicate" field is mandatory (it should contain the name of a storage)')
            
            if values.replicate == values.dest:
                raise ValueError('Replication job cannot replicate to the same storage as the source')
            
        return values