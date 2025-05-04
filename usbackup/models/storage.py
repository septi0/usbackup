from pydantic import BaseModel, ConfigDict

class StorageModel(BaseModel):
    name: str
    path: str
    
    model_config = ConfigDict(extra='forbid')