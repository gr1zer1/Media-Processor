from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

class JWTSchema(BaseModel):
    sub:str
    role:str

    model_config = ConfigDict(extra="ignore")


class UploadResponseSchema(BaseModel):
    id:int
    file_id:int
    status:str
    error_message:str | None = None
    started_at:datetime | None = None
    finished_at:datetime | None = None

    model_config = ConfigDict(from_attributes=True)



class MediaFileSchema(BaseModel):
    id:int
    original_filename:str
    filetype:str
    filesize:int
    user_id:int
    user_access_ids:list[int] | None = None
    updated_at:datetime
    created_at:datetime

    model_config = ConfigDict(from_attributes=True)


class UserSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    role: str
    quota_used: int
    quota_limit: int
    created_at: datetime
    updated_at: datetime


class IdsRequest(BaseModel):
    ids: list[int] | None = Field(default=None)
    