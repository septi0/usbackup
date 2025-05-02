from pydantic import BaseModel, ConfigDict

class UsBackupHandlerBaseModel(BaseModel):
    handler: str
    
    model_config = ConfigDict(extra='forbid')