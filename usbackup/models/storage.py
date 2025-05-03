from pydantic import BaseModel, ConfigDict

__all__ = ['StorageModel']

class StorageModel(BaseModel):
    name: str
    path: str
    
    model_config = ConfigDict(extra='forbid')