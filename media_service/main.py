from fastapi import FastAPI
from contextlib import asynccontextmanager
from core.config import config
from core.db import db_helper


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up the Media Service...")
    if not db_helper.minio_client.bucket_exists(config.bucket_name):
        db_helper.minio_client.make_bucket(config.bucket_name)
    

    yield
    
    print("Shutting down the Media Service...")


app = FastAPI(title="Media Service API", version="1.0.0", lifespan=lifespan)