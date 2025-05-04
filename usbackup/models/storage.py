from pydantic import BaseModel, ConfigDict
from usbackup.models.path import PathModel

class StorageModel(BaseModel):
    name: str
    path: PathModel
    
    model_config = ConfigDict(extra='forbid')