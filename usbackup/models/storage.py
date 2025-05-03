from pydantic import BaseModel, ConfigDict

__all__ = ['UsBackupStorageModel']

class UsBackupStorageModel(BaseModel):
    name: str
    path: str
    
    model_config = ConfigDict(extra='forbid')