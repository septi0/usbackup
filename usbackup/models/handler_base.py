from pydantic import BaseModel, ConfigDict

class HandlerBaseModel(BaseModel):
    handler: str
    
    model_config = ConfigDict(extra='forbid')
