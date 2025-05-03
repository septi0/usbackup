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
    retention_policy: RetentionPolicyModel = None
    notification_policy: Literal['never', 'always', 'on-failure'] = 'always'
    concurrency: int = Field(1, ge=1)
    pre_run_cmd: str = None
    post_run_cmd: str = None
    replicate: str = None

    model_config = ConfigDict(extra='forbid')
    
    @model_validator(mode='after')
    @classmethod
    def validate(cls, values): 
        if values.type == 'replication':
            if not values.replicate:
                raise ValueError('Replication job requires a storage to replicate from')
            
            if values.replicate == values.dest:
                raise ValueError('Replication job cannot replicate to the same storage as the source')
            
        return values