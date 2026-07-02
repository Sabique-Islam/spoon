import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from app.auth.providers import OAUTH_PROVIDERS
from app.auth.state import pop_oauth_state
from app.auth.store import delete_provider_token
from app.config import get_settings
from app.connectors.registry import SUPPORTED_PROVIDERS, get_connector
from app.core.errors import sanitize_sync_errors
from app.core.security import require_api_key
from app.logging import log_audit, log_search, log_sync
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


@router.get("/providers", response_model=ProvidersResponse, dependencies=[Depends(require_api_key)])
async def providers() -> ProvidersResponse:
    return ProvidersResponse(providers=SUPPORTED_PROVIDERS)


@router.get("/auth/{provider}", dependencies=[Depends(require_api_key)])
async def auth_provider(provider: str) -> RedirectResponse:
    spec = OAUTH_PROVIDERS.get(provider)
    if not spec:
        raise HTTPException(status_code=404, detail={"error": f"Unknown provider: {provider}"})

    settings = get_settings()
    if not spec.configured(settings):
        raise HTTPException(
            status_code=400,
            detail={"error": f"OAuth is not configured. Set {spec.env_hint}."},
        )
    try:
        url = spec.build_authorization_url()
    except ValueError:
        raise HTTPException(
            status_code=400, detail={"error": "OAuth is not configured"}
        ) from None
    return RedirectResponse(url=url, status_code=302)


# OAuth callbacks must not require an API key: the browser redirect from Google,
# Slack, etc. cannot attach X-API-Key. CSRF state (+ PKCE where used) protects
# this route instead.
@router.get("/auth/{provider}/callback")
async def auth_provider_callback(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    spec = OAUTH_PROVIDERS.get(provider)
    if not spec:
        raise HTTPException(status_code=404, detail={"error": f"Unknown provider: {provider}"})

    if error:
        logger.warning("OAuth error provider=%s error=%s", provider, error)
        raise HTTPException(
            status_code=400,
            detail={"error": "OAuth authorization was denied or failed"},
        )

    if not code:
        raise HTTPException(
            status_code=400, detail={"error": "Missing authorization code"}
        )

    state_entry = pop_oauth_state(state or "")
    if not state_entry:
        raise HTTPException(status_code=400, detail={"error": "Invalid OAuth state"})

    try:
        token_response = await spec.exchange_code_for_token(
            code, pkce_verifier=state_entry.pkce_verifier
        )
        await spec.store_oauth_token(token_response)
    except Exception as exc:
        logger.exception("OAuth token exchange failed provider=%s", provider)
        raise HTTPException(
            status_code=400, detail={"error": "Failed to exchange authorization code"}
        ) from exc

    log_audit("oauth_connect", provider=provider)
    return {"status": "ok", "message": spec.success_message}


@router.delete("/auth/{provider}", dependencies=[Depends(require_api_key)])
async def disconnect_provider(provider: str) -> dict[str, str]:
    if provider not in OAUTH_PROVIDERS:
        raise HTTPException(status_code=404, detail={"error": f"Unknown provider: {provider}"})
    delete_provider_token(provider)
    log_audit("oauth_disconnect", provider=provider)
    return {"status": "ok", "message": f"{provider} disconnected"}


async def _run_sync(provider: str) -> SyncResponse:
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=404, detail={"error": f"Unknown provider: {provider}"})

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
    log_audit(
        "sync",
        provider=provider,
        documents=result.documents_processed,
        errors=len(result.errors),
    )

    return SyncResponse(
        provider=provider,
        documents_processed=result.documents_processed,
        errors=sanitize_sync_errors(result.errors, provider=provider),
    )


@router.post("/sync/{provider}", response_model=SyncResponse, dependencies=[Depends(require_api_key)])
async def sync_provider(provider: str) -> SyncResponse:
    return await _run_sync(provider)


@router.post("/sync/all", response_model=list[SyncResponse], dependencies=[Depends(require_api_key)])
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


@router.post("/search", response_model=SearchResponse, dependencies=[Depends(require_api_key)])
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
