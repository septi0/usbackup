from pydantic import BaseModel, Field, ConfigDict

__all__ = ['UsBackupRetentionPolicyModel']

class UsBackupRetentionPolicyModel(BaseModel):
    last: int = Field(None, ge=1)
    hourly: int = Field(None, ge=1)
    daily: int = Field(None, ge=1)
    weekly: int = Field(None, ge=1)
    monthly: int = Field(None, ge=1)
    yearly: int = Field(None, ge=1)
    
    model_config = ConfigDict(extra='forbid')