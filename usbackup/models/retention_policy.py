from pydantic import BaseModel, Field, ConfigDict

class RetentionPolicyModel(BaseModel):
    last: int | None = Field(None, ge=1)
    hourly: int | None = Field(None, ge=1)
    daily: int | None = Field(None, ge=1)
    weekly: int | None = Field(None, ge=1)
    monthly: int | None = Field(None, ge=1)
    yearly: int | None = Field(None, ge=1)
    
    model_config = ConfigDict(extra='forbid')