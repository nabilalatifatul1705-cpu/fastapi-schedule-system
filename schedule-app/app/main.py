"""Entry point FastAPI: uvicorn app.main:app --reload"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import models  # noqa: F401  (registrasi model ke metadata)
from app.config import settings
from app.database import Base, engine
from app.routers.schedule import router as schedule_router
from app.services import ServiceError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Penjadwalan kuliah, deteksi bentrok 3D, Observer Pattern, AI Rescheduler, "
    "dan integrasi invalidasi KRS.",
    lifespan=lifespan,
)


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.message, **exc.payload}
    )


@app.get("/", tags=["health"])
def root():
    return {"service": settings.app_name, "version": settings.app_version, "docs": "/docs"}


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}


app.include_router(schedule_router)
