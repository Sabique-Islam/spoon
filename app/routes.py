import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.auth.oauth import (
    build_authorization_url,
    exchange_code_for_token,
    store_oauth_token,
    validate_oauth_state,
)
from app.config import get_settings
from app.connectors.registry import SUPPORTED_PROVIDERS, get_connector
from app.logging import log_search, log_sync
from app.models import (
    HealthResponse,
    ProvidersResponse,
    SearchRequest,
    SearchResponse,
    SyncResponse,
)
from app.supermemory.search import search_documents

logger = logging.getLogger("spoon")
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/providers", response_model=ProvidersResponse)
async def providers() -> ProvidersResponse:
    return ProvidersResponse(providers=SUPPORTED_PROVIDERS)


@router.get("/auth/notion")
async def auth_notion() -> RedirectResponse:
    settings = get_settings()
    if not settings.oauth_configured:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "OAuth is not configured. Set SPOON_NOTION_CONNECTION_CLIENT_ID and SPOON_NOTION_CONNECTION_SECRET_ID."
            },
        )
    try:
        url = build_authorization_url()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)}) from exc
    return RedirectResponse(url=url, status_code=302)


@router.get("/auth/notion/callback")
async def auth_notion_callback(code: str | None = None, state: str | None = None):
    if not code:
        raise HTTPException(
            status_code=400, detail={"error": "Missing authorization code"}
        )
    if not state or not validate_oauth_state(state):
        raise HTTPException(status_code=400, detail={"error": "Invalid OAuth state"})

    try:
        token_response = await exchange_code_for_token(code)
        await store_oauth_token(token_response)
    except Exception as exc:
        logger.exception("OAuth token exchange failed")
        raise HTTPException(
            status_code=400, detail={"error": "Failed to exchange authorization code"}
        ) from exc

    return {"status": "ok", "message": "Notion connected successfully"}


async def _run_sync(provider: str) -> SyncResponse:
    connector = get_connector(provider)
    if not connector.is_authenticated():
        raise HTTPException(
            status_code=401,
            detail={"error": f"{provider} is not authenticated."},
        )

    start = time.perf_counter()
    result = await connector.sync()
    duration_ms = (time.perf_counter() - start) * 1000
    log_sync(provider, result.documents_processed, duration_ms, result.errors)

    return SyncResponse(
        provider=provider,
        documents_processed=result.documents_processed,
        errors=result.errors,
    )


@router.post("/sync/notion", response_model=SyncResponse)
async def sync_notion() -> SyncResponse:
    return await _run_sync("notion")


@router.post("/sync/linear", response_model=SyncResponse)
async def sync_linear() -> SyncResponse:
    return await _run_sync("linear")


@router.post("/sync/all", response_model=list[SyncResponse])
async def sync_all() -> list[SyncResponse]:
    responses: list[SyncResponse] = []
    for provider in SUPPORTED_PROVIDERS:
        connector = get_connector(provider)
        if not connector.is_authenticated():
            continue
        responses.append(await _run_sync(provider))

    if not responses:
        raise HTTPException(
            status_code=401,
            detail={"error": "No providers connected."},
        )
    return responses


@router.post("/search", response_model=SearchResponse)
async def search(body: SearchRequest) -> SearchResponse:
    start = time.perf_counter()
    try:
        results = search_documents(body.query, limit=body.limit)
    except Exception as exc:
        logger.exception("Search failed")
        raise HTTPException(
            status_code=502, detail={"error": "Search failed"}
        ) from exc
    log_search((time.perf_counter() - start) * 1000)
    return SearchResponse(results=results)
