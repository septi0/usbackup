from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from usbackup.models.retention_policy import UsBackupRetentionPolicyModel

__all__ = ['UsBackupJobModel']
    
class UsBackupJobModel(BaseModel):
    name: str
    type: Literal['backup', 'replication']
    limit: list[str] = []
    exclude: list[str] = []
    schedule: str = Field('0 0 * * *', pattern=r'^(\*|(\d+|\*\/\d+|\d+-\d+|\d+(,\d+)*))(\s+(\*|(\d+|\*\/\d+|\d+-\d+|\d+(,\d+)*))){4}$')
    retention_policy: UsBackupRetentionPolicyModel = None
    notification_policy: Literal['never', 'always', 'on-failure'] = 'always'
    concurrency: int = Field(1, ge=1)
    pre_run_cmd: str = None
    post_run_cmd: str = None

    model_config = ConfigDict(extra='forbid')