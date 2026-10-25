from pydantic import BaseModel, Field, ConfigDict, model_validator

class RetentionPolicyModel(BaseModel):
    last: int | None = Field(None, ge=1)
    hourly: int | None = Field(None, ge=1)
    daily: int | None = Field(None, ge=1)
    weekly: int | None = Field(None, ge=1)
    monthly: int | None = Field(None, ge=1)
    yearly: int | None = Field(None, ge=1)
    
    model_config = ConfigDict(extra='forbid')
    
    @model_validator(mode='after')
    @classmethod
    def validate_after(cls, values):
        if all(getattr(values, field) is None for field in cls.model_fields):
            raise ValueError(f'Retention policy must define at least one of: {", ".join(cls.model_fields)}')
        
        return values