from pydantic import BaseModel, Field, ConfigDict

class JWTSchema(BaseModel):
    sub:str
    role:str

    model_config = ConfigDict(extra="ignore")