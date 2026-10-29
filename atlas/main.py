import json
import logging
import sqlite3
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

import psycopg
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from atlas.api import router
from atlas.config import Settings
from atlas.database import ready
from atlas.errors import AtlasError
from atlas.postgres import PostgresDocumentService
from atlas.postgres import ready as postgres_ready
from atlas.providers import OllamaProvider
from atlas.schemas import Health
from atlas.security import RateLimiter
from atlas.services import DocumentService
from atlas.vector_retrieval import PostgresVectorService

logger = logging.getLogger("atlas.requests")


def error_response(code: str, message: str, status: int) -> JSONResponse:
    headers: dict[str, str] = {}
    if status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    if status == 429:
        headers["Retry-After"] = "60"
    return JSONResponse(
        {"error": {"code": code, "message": message}}, status_code=status, headers=headers
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    app = FastAPI(title="Atlas", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = config
    app.state.documents = (
        PostgresDocumentService(config, config.postgres_dsn.get_secret_value())
        if config.postgres_dsn
        else DocumentService(config)
    )
    provider = (
        OllamaProvider(config.ollama_url, config.embedding_model, config.generation_model)
        if config.generation_enabled or config.vector_enabled
        else None
    )
    app.state.provider = provider if config.generation_enabled else None
    app.state.vectors = (
        PostgresVectorService(app.state.documents, provider)
        if config.vector_enabled and provider is not None
        else None
    )
    app.state.limiter = RateLimiter(config.requests_per_minute)
    app.include_router(router)

    @app.middleware("http")
    async def observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            # Deliberately omit exception values, URLs, headers and user text.
            logger.error(
                json.dumps(
                    {
                        "event": "request_failure",
                        "request_id": request_id,
                        "exception_type": type(exc).__name__,
                    }
                )
            )
            response = error_response("internal_error", "Request could not be completed.", 500)
        response.headers.update(
            {
                "X-Request-ID": request_id,
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
                "Referrer-Policy": "no-referrer",
            }
        )
        if config.frontend_dir is not None and not (
            request.url.path.startswith("/v1/") or request.url.path.startswith("/health/")
        ):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            )
        logger.info(
            json.dumps(
                {
                    "event": "request",
                    "request_id": request_id,
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            )
        )
        return response

    @app.exception_handler(AtlasError)
    async def application_error(request: Request, exc: AtlasError) -> JSONResponse:
        return error_response(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response("validation_error", "Invalid request parameters.", 422)

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(psycopg.Error)
    async def storage_error(request: Request, exc: sqlite3.Error | psycopg.Error) -> JSONResponse:
        return error_response(
            "storage_unavailable", "Storage is unavailable. Try again later.", 503
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response("http_error", "Request could not be handled.", exc.status_code)

    @app.get("/health/live", response_model=Health)
    def live() -> Health:
        return Health(status="live")

    @app.get("/health/ready", response_model=Health)
    def readiness() -> Health:
        storage_ready = (
            postgres_ready(config.postgres_dsn.get_secret_value())
            if config.postgres_dsn
            else ready(config.database_path)
        )
        if not storage_ready:
            raise AtlasError("not_ready", "Storage is unavailable or requires migration.", 503)
        if provider is not None and not provider.ready(
            generation=config.generation_enabled, embeddings=config.vector_enabled
        ):
            raise AtlasError("not_ready", "Required local models are unavailable.", 503)
        return Health(status="ready")

    if config.frontend_dir is not None:
        app.mount("/", StaticFiles(directory=config.frontend_dir, html=True), name="frontend")
    return app
