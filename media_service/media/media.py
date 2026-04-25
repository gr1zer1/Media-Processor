from datetime import datetime, timezone
from typing import BinaryIO
import logging
import os
import subprocess
import tempfile
import uuid

from celery import Celery
from PIL import Image
from sqlalchemy.orm import sessionmaker
from sqlalchemy import update

from core.db import db_helper
from core.config import config
from core import MediaVersionModel
from core.models.processing_task import ProcessingTaskModel

from sqlalchemy import create_engine


logger = logging.getLogger(__name__)

app = Celery(
    "tasks",
    broker=f"{config.redis_url}/0",
    backend=f"{config.redis_url}/0",
)

engine = create_engine(config.db_url.replace("asyncpg", "psycopg2"))

Session = sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


def set_task_status(media_file_id: int, status: str, error: str | None = None):
    with Session() as session:
        session.execute(
            update(ProcessingTaskModel)
            .where(ProcessingTaskModel.file_id == media_file_id)
            .values(
                status=status,
                error_message=error,
                finished_at=datetime.now(timezone.utc),
            )
        )
        session.commit()


def save_versions_to_db(*versions):
    with Session() as session:
        for version in versions:
            session.add(version)
        session.commit()
        for version in versions:
            session.refresh(version)


def upload_to_minio(object_name: str, data: BinaryIO, length: int):
    db_helper.minio_client.put_object(
        bucket_name=config.bucket_name,
        object_name=object_name,
        data=data,
        length=length,
        part_size=10 * 1024 * 1024,
    )


def make_url(object_name: str) -> str:
    return f"{config.minio_url}/{config.bucket_name}/{object_name}"


def download_to_tempfile(minio_key: str) -> str:
    response = db_helper.minio_client.get_object(
        bucket_name=config.bucket_name,
        object_name=minio_key,
    )
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"-{uuid.uuid4()}") as tmp:
            for chunk in response.stream(32 * 1024):
                tmp.write(chunk)
            return tmp.name
    finally:
        response.close()
        response.release_conn()


def process_image(src_path: str, media_file_id: int, new_file_name: str) -> list:
    versions = []
    image = Image.open(src_path)

    thumbnail_object = f"thumbnail-{new_file_name}"
    thumbnail_path = f"/tmp/{uuid.uuid4()}-{thumbnail_object}"
    try:
        thumbnail = image.copy()
        thumbnail.thumbnail((128, 128))
        thumbnail.save(thumbnail_path)
        with open(thumbnail_path, "rb") as f:
            upload_to_minio(thumbnail_object, f, os.path.getsize(thumbnail_path))
    finally:
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)

    versions.append(MediaVersionModel(
        file_id=media_file_id,
        version_type="thumbnail",
        url=make_url(thumbnail_object),
        minio_key=thumbnail_object,
    ))

    medium_object = f"medium-{new_file_name}"
    medium_path = f"/tmp/{uuid.uuid4()}-{medium_object}"
    try:
        width, height = image.size
        new_height = int(height * 800 / width)
        medium = image.resize((800, new_height), Image.LANCZOS)
        medium.save(medium_path)
        with open(medium_path, "rb") as f:
            upload_to_minio(medium_object, f, os.path.getsize(medium_path))
    finally:
        if os.path.exists(medium_path):
            os.remove(medium_path)

    versions.append(MediaVersionModel(
        file_id=media_file_id,
        version_type="medium",
        url=make_url(medium_object),
        minio_key=medium_object,
    ))

    return versions


def process_video(src_path: str, media_file_id: int, new_file_name: str, content_type: str) -> list:
    versions = []

    converted_object = f"converted-{new_file_name}.mp4"
    converted_path = f"/tmp/{uuid.uuid4()}-{converted_object}"

    try:
        if content_type == "video/mp4":
            converted_path = src_path
        else:
            result = subprocess.run([
                "ffmpeg",
                "-i", src_path,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-y",
                converted_path,
            ], capture_output=True, timeout=None)

            if result.returncode != 0:
                raise Exception(f"ffmpeg conversion error: {result.stderr.decode()}")

        with open(converted_path, "rb") as f:
            upload_to_minio(converted_object, f, os.path.getsize(converted_path))

        versions.append(MediaVersionModel(
            file_id=media_file_id,
            version_type="converted",
            url=make_url(converted_object),
            minio_key=converted_object,
        ))

        preview_object = f"preview-{new_file_name}.jpg"
        preview_path = f"/tmp/{uuid.uuid4()}-{preview_object}"
        try:
            result = subprocess.run([
                "ffmpeg",
                "-i", converted_path,
                "-ss", "00:00:01",
                "-vf", "scale=128:128",
                "-frames:v", "1",
                "-y",
                preview_path,
            ], capture_output=True, timeout=60)

            if result.returncode != 0:
                raise Exception(f"ffmpeg preview error: {result.stderr.decode()}")

            with open(preview_path, "rb") as f:
                upload_to_minio(preview_object, f, os.path.getsize(preview_path))

            versions.append(MediaVersionModel(
                file_id=media_file_id,
                version_type="preview",
                url=make_url(preview_object),
                minio_key=preview_object,
            ))
        finally:
            if os.path.exists(preview_path):
                os.remove(preview_path)

    finally:
        if converted_path != src_path and os.path.exists(converted_path):
            os.remove(converted_path)

    return versions


@app.task
def media_processing(minio_key: str, media_file_id: int, content_type: str, new_file_name: str):
    src_path = download_to_tempfile(minio_key)

    try:
        if content_type.startswith("image/"):
            versions = process_image(src_path, media_file_id, new_file_name)

        elif content_type.startswith("video/"):
            versions = process_video(src_path, media_file_id, new_file_name, content_type)

        else:
            raise Exception(f"Unsupported content type: {content_type}")

        save_versions_to_db(*versions)
        set_task_status(media_file_id, "done")
        logger.info(f"media_processing done: file_id={media_file_id}")

    except Exception as e:
        logger.exception(f"media_processing failed: file_id={media_file_id}")
        set_task_status(media_file_id, "failed", error=str(e))
        raise

    finally:
        if os.path.exists(src_path):
            os.remove(src_path)