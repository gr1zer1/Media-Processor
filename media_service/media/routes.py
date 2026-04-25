from fastapi import APIRouter, HTTPException,UploadFile,Depends,Body
from fastapi.responses import StreamingResponse

from core.auth import current_user, get_token_from_header,encode_token
from core import MediaFileModel,MediaVersionModel,ProcessingTaskModel
from .schemas import IdsRequest, JWTSchema,UploadResponseSchema,MediaFileSchema,UserSchema
from core import config
from core.db import db_helper

from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import uuid

from .media import media_processing,make_url

import aiohttp
import asyncio

SessionDep = Annotated[AsyncSession, Depends(db_helper.get_session)]


router = APIRouter()


async def get_stream_file(
        minio_key:str
        ) -> StreamingResponse:
    
    response = db_helper.minio_client.get_object(config.bucket_name, minio_key)


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
    ids: IdsRequest | None = Body(default=None),
    user_token: str = Depends(get_token_from_header),
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
    
    #private link
    if ids is None:

        media_file = MediaFileModel(
            original_filename=file.filename,
            filetype=file.content_type,
            filesize=file.size,
            user_id=user.id,
            user_access_ids=None
        )

    #public link without access control
    elif len(ids.ids) == 0 or ids.ids == None:
        media_file = MediaFileModel(
            original_filename=file.filename,
            filetype=file.content_type,
            filesize=file.size,
            user_id=user.id,
            user_access_ids=[]
        )
    
    #public link with access control
    else:
        media_file = MediaFileModel(
            original_filename=file.filename,
            filetype=file.content_type,
            filesize=file.size,
            user_id=user.id,
            user_access_ids=ids.ids
        )
    

    session.add(media_file)
    await session.commit()
    await session.refresh(media_file)
    
    original_version = MediaVersionModel(
        file_id=media_file.id,
        version_type="original",
        url=make_url(), 
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

"""TODO: Fix bag with access control for public files. Currently anyone can access any file if they know the name.
We need to add some kind of token or signature to the URL to ensure that only authorized users can access the file."""

@router.get("/files/get/{url}")
async def get_file_by_url(
    url:str,
    session:SessionDep,
    user:JWTSchema = Depends(current_user),
    ) -> dict:
    stmt = (select(MediaVersionModel)
            .where(MediaVersionModel.url == url)
            .options(selectinload(MediaVersionModel.file))
    )
    res = await session.execute(stmt)
    data = res.scalar_one_or_none()

    if not data:
        raise HTTPException(status_code=404, detail="File not found")
    
    if data.file.user_id != user.sub and (data.file.user_access_ids is None or user.sub not in data.file.user_access_ids):
        raise HTTPException(status_code=403, detail="Access denied")

    return get_stream_file(data.minio_key)


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