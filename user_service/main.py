from contextlib import asynccontextmanager

from core.db import db_helper
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from users.routes import router as users_router

from core.config import config

from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
import redis.asyncio as redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    r = await redis.from_url(config.redis_url)
    await FastAPILimiter.init(r)
    yield
    await db_helper.dispose()


app = FastAPI(
    title="Task Manager API",
    description="A task management API with JWT authentication",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(users_router, prefix="/users")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8002"],
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=True,
)





@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    print(f"{request.method} {request.url.path}")
    response = await call_next(request)
    return response


@app.exception_handler(HTTPException)
async def exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error": True,
            "path": request.url.path,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "error": True,
            "path": request.url.path,
        },
    )


@app.get("/health")
async def health_check():
    return {"status": "ok"}
