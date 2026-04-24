from fastapi import APIRouter, HTTPException,UploadFile,Depends
from fastapi.responses import StreamingResponse

from core.auth import current_user, get_token_from_header,encode_token
from core import MediaFileModel,MediaVersionModel,ProcessingTaskModel
from .schemas import JWTSchema,UploadResponseSchema,MediaFileSchema,UserSchema
from core import config
from core.db import db_helper

from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import uuid

from .media import media_processing

import aiohttp
import asyncio

SessionDep = Annotated[AsyncSession, Depends(db_helper.get_session)]


router = APIRouter()


async def private_stream_file(
        file_name:str,
        version_type:str,
        user:JWTSchema,
        session:AsyncSession,
        ) -> StreamingResponse:
    stmt = (select(MediaFileModel)
            .where(MediaFileModel.original_filename == file_name)
    )
    result = await session.execute(stmt)
    file = result.scalar_one_or_none()

    if not file or file.user_id != user.sub:
        return {"error": "File not found or access denied"}
    
    file_stmt = (select(MediaVersionModel)
                 .where(MediaVersionModel.file_id == file.id, MediaVersionModel.version_type == version_type)
    )
    file_result = await session.execute(file_stmt)
    media_version = file_result.scalar_one_or_none()

    if not media_version:
        raise HTTPException(status_code=404, detail="File not found")

    response = db_helper.minio_client.get_object(config.bucket_name, media_version.minio_key)


    return StreamingResponse(
        response.stream(5 * 1024 * 1024),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="file.jpg"'
        }
    )


async def public_stream_file(
        file_name:str,
        version_type:str,
        session:AsyncSession,
        ) -> StreamingResponse:
    stmt = (select(MediaFileModel)
            .where(MediaFileModel.original_filename == file_name)
    )
    result = await session.execute(stmt)
    file = result.scalar_one_or_none()

    
    file_stmt = (select(MediaVersionModel)
                 .where(MediaVersionModel.file_id == file.id,MediaVersionModel.version_type == version_type)
    )
    file_result = await session.execute(file_stmt)
    media_version = file_result.scalar_one_or_none()

    if not media_version:
        raise HTTPException(status_code=404, detail="File not found")
    response = db_helper.minio_client.get_object(config.bucket_name, media_version.minio_key)


    return StreamingResponse(
        response.stream(5 * 1024 * 1024),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": 'attachment; filename="file.jpg"'
        }
    )


@router.post("/upload")
async def upload(
    file: UploadFile,
    session:SessionDep,
    user_token: str = Depends(get_token_from_header)
    ):
    async with aiohttp.ClientSession() as http_session:
        async with http_session.get(config.user_service_url + "/users/by-jwt", headers={"Authorization": f"Bearer {user_token}"}) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=401, detail="Unauthorized")
            user_data = await resp.json()
    user = UserSchema.model_validate(user_data)

    new_file_name = str(uuid.uuid4())

    minio_key = f"original-{new_file_name}"
    db_helper.minio_client.put_object(
        bucket_name=config.bucket_name,
        object_name=minio_key,
        data=file.file,
        length=-1,
        part_size=10 * 1024 * 1024,
    )

    length = file.size
    


    media_file = MediaFileModel(
        original_filename=file.filename,
        filetype=file.content_type,
        filesize=file.size,
        user_id=user.id,
    )

    session.add(media_file)
    await session.commit()
    await session.refresh(media_file)
    
    original_version = MediaVersionModel(
        file_id=media_file.id,
        version_type="original",
        url=f"{config.minio_url}/{config.bucket_name}/original-{new_file_name}",  #change
        minio_key=f"original-{new_file_name}",
    )



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

    service_token = encode_token({"sub": "media_service"})

    async with aiohttp.ClientSession() as http_session:
        
        await http_session.patch(
            config.user_service_url + f"/users/{length}/?user_id={user.id}",
            headers={"Authorization": f"Bearer {service_token}"})
    
    return UploadResponseSchema.model_validate(processing_task)


@router.get("/status/{task_id}",response_model=UploadResponseSchema)
async def check_status(
    task_id:int,
    session:SessionDep,
    user:JWTSchema = Depends(current_user),
    ) -> UploadResponseSchema:

    stmt = select(ProcessingTaskModel).where(ProcessingTaskModel.id == task_id)
    result = await session.execute(stmt)
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    elif task.file.user_id != user.sub:
        raise HTTPException(status_code=403, detail="Access denied")


    return UploadResponseSchema.model_validate(task)


@router.get("/files",response_model=list[MediaFileSchema])
async def list_files(
    session:SessionDep,
    user:JWTSchema = Depends(current_user),
    ) -> list[MediaFileSchema]:

    stmt = select(MediaFileModel).where(MediaFileModel.user_id == user.sub)
    result = await session.execute(stmt)
    files = result.scalars().all()

    return files

@router.get("/files/private/{file_name}",response_model=StreamingResponse)
async def get_private_file(
    file_name:str,
    version_type:str,
    session:SessionDep,
    user:JWTSchema = Depends(current_user),
    ) -> StreamingResponse:
    return await private_stream_file(file_name, version_type, user, session)

"""TODO: Fix bag with access control for public files. Currently anyone can access any file if they know the name.
We need to add some kind of token or signature to the URL to ensure that only authorized users can access the file."""
@router.get("/files/public/{file_name}",response_model=StreamingResponse)
async def get_public_file(
    file_name:str,
    version_type:str,
    session:SessionDep,
    ) -> StreamingResponse:
    return await public_stream_file(file_name, version_type, session)


@router.get("/files/{file_id}")
async def get_file_by_id(
    file_id:int,
    session:SessionDep,
    user:JWTSchema = Depends(current_user),
    ) -> dict:
    stmt = (select(MediaFileModel)
            .where(MediaFileModel.id == file_id)
            .options(selectinload(MediaFileModel.media_versions))
    )
    result = await session.execute(stmt)
    file = result.scalar_one_or_none()

    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    elif file.user_id != user.sub:
        raise HTTPException(status_code=403, detail="Access denied")

    

    return {
        "media_file":file,
        "media_versions":file.media_versions
    }