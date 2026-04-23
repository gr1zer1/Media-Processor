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


class MediaFileSchema(BaseModel):
    id:int
    original_filename:str
    filetype:str
    filesize:int
    user_id:int

    model_config = ConfigDict(from_attributes=True)
    