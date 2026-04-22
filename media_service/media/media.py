from celery import Celery
from core.db import db_helper
from core.config import config
from fastapi import UploadFile

app = Celery(
    "tasks",
    broker=f"{config.redis_url}/0",
    backend=f"{config.redis_url}/0",
)

@app.task
def upload(file: UploadFile):

    db_helper.minio_client.put_object(
        bucket_name=config.bucket_name,
        object_name=f"original-{file.filename}",
        data=file.file,
        length=-1,
        part_size=10 * 1024 * 1024,
    )
    