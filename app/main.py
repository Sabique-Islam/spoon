import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.logging import RequestLoggingMiddleware, setup_logging
from app.routes import router

setup_logging()
logger = logging.getLogger("spoon")

app = FastAPI(title="Spoon", version="1.0.0")
app.add_middleware(RequestLoggingMiddleware)
app.include_router(router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})
