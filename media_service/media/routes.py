from fastapi import APIRouter,UploadFile,File
from .media import upload
from core import MediaFileModel,MediaVersionModel,ProcessingTaskModel


router = APIRouter()

@router.post("/upload")
async def upload(file: UploadFile):
    


    upload.delay(file)
    return {"message": "File upload initiated"}