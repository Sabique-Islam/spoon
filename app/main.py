import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.security import RateLimitMiddleware
from app.core.startup import validate_startup_config
from app.logging import RequestLoggingMiddleware, setup_logging
from app.routes import router

setup_logging()
logger = logging.getLogger("spoon")

settings = get_settings()
app = FastAPI(
    title="Spoon",
    version="1.0.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

if settings.cors_origins_list:
    # CORS is opt-in and explicit: no middleware is added (i.e. cross-origin
    # browser requests stay blocked) unless SPOON_CORS_ALLOWED_ORIGINS is set.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["X-API-Key", "Authorization", "Content-Type"],
    )

app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.include_router(router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


validate_startup_config(settings)
