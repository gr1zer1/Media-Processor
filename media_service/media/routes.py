from fastapi import APIRouter,UploadFile,Depends
from core.auth import current_user
from .media import upload
from core import MediaFileModel,MediaVersionModel,ProcessingTaskModel
from .schemas import JWTSchema,UploadResponseSchema
from core import config
from core.db import db_helper

from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncSession

import uuid

from .media import media_processing

SessionDep = Annotated[AsyncSession, Depends(db_helper.get_session)]


router = APIRouter()

@router.post("/upload")
async def upload(
    file: UploadFile,
    session:SessionDep,
    user:JWTSchema = Depends(current_user),
    ):

    new_file_name = str(uuid.uuid4())

    minio_key = f"original-{new_file_name}"
    db_helper.minio_client.put_object(
        bucket_name=config.bucket_name,
        object_name=minio_key,
        data=file.file,
        length=-1,
        part_size=10 * 1024 * 1024,
    )
    


    media_file = MediaFileModel(
        original_filename=file.filename,
        filetype=file.content_type,
        filesize=file.size,
        user_id=user.sub,
    )

    original_version = MediaVersionModel(
        file_id=media_file.id,
        version="original",
        url=f"{config.minio_url}/{config.bucket_name}/original-{new_file_name}",  #change
        minio_key=f"original-{new_file_name}",
    )


    session.add(media_file)
    await session.commit()
    await session.refresh(media_file)

    session.add(original_version)
    await session.commit()
    await session.refresh(original_version)

    processing_task = ProcessingTaskModel(
        file_id=media_file.id,
        status="pending",

    )

    session.add(processing_task)
    await session.commit()
    await session.refresh(processing_task)

    media_processing.delay(minio_key, media_file.id, file.content_type, new_file_name)
    
    return UploadResponseSchema.model_validate(processing_task)