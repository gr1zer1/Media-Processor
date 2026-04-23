from fastapi import FastAPI
from contextlib import asynccontextmanager
from core.config import config
from core.db import db_helper
from media.routes import router as media_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up the Media Service...")
    if not db_helper.minio_client.bucket_exists(config.bucket_name):
        db_helper.minio_client.make_bucket(config.bucket_name)
    

    yield
    
    print("Shutting down the Media Service...")


app = FastAPI(title="Media Service API", version="1.0.0", lifespan=lifespan)
app.include_router(media_router, tags=["media"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}