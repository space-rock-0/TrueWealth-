import time
import re
import os
from typing import Literal, Optional
from dotenv import load_dotenv

# Load runtime configuration before importing modules that read environment values.
load_dotenv()

import uvicorn
from cachetools import TTLCache
from app.core.cache import answer_cache, cache_get, cache_set, used_live_market_data
from app.core.config import (MODEL_ANSWER, RATE_LIMIT, RATE_LIMIT_ENABLED)
from app.core.db import (get_history, get_review_queue, get_stats, init_db,
                         log_query, submit_review)
from app.core.logger import logger
from app.core.review import needs_review
from app.core.rate_limit import limiter
from app.core.email_delivery import email_configured
from app.core.state import initialize_state
from app.core.workflow import get_workflow_app
from app.auth import get_current_user, require_csrf, router as auth_router
from app.statements import router as statements_router, recover_interrupted_analyses
from app.core.db import AppUser
from app.tools.model_gateway import (DEFAULT_PROVIDER_MODELS,
                                     reset_request_model_config,
                                     set_request_model_config)
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

app = FastAPI(title="TrueWealth AI API", version="2.0")


@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    return response
_allowed_origins = [origin.strip() for origin in os.getenv(
    "APP_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-LLM-Provider", "X-LLM-Model", "X-LLM-API-Key"],
)

_MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,149}$")
_SUPPORTED_PROVIDERS = set(DEFAULT_PROVIDER_MODELS)


def _request_model_settings(provider, model, api_key):
    if provider is None and model is None and api_key is None:
        return None

    provider = (provider or "groq").strip().lower()
    if provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported AI provider.")
    model = (model or DEFAULT_PROVIDER_MODELS[provider]).strip()
    if (not _MODEL_ID_PATTERN.fullmatch(model) or ".." in model or "//" in model
            or model.startswith("/") or model.endswith("/")):
        raise HTTPException(status_code=400, detail="Invalid model ID.")
    api_key = api_key.strip() if api_key else None
    if api_key and len(api_key) > 8192:
        raise HTTPException(status_code=400, detail="API key is too long.")
    return {"provider": provider, "model": model, "api_key": api_key}


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter.enabled = RATE_LIMIT_ENABLED
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Initialize workflow
logger.info("Initializing TrueWealth AI Workflow...")
ai_workflow = get_workflow_app()
init_db()
recover_interrupted_analyses()
conversation_states = TTLCache(maxsize=128, ttl=21600)

if os.getenv("APP_ENV", "development").lower() == "production":
    if os.getenv("EMAIL_VERIFICATION_REQUIRED", "true").lower() != "true":
        raise RuntimeError("Production requires verified email accounts.")
    if not RATE_LIMIT_ENABLED:
        raise RuntimeError("Production requires rate limiting.")
if os.getenv("APP_ENV", "development").lower() == "production" and not os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://", "postgresql+psycopg://")):
    raise RuntimeError("Production requires DATABASE_URL pointing to PostgreSQL so account and chat data persist across restarts.")


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    session_id: str = Field(default='default', min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    portfolio: Optional[list] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    source: str
    degraded: Optional[str] = None
    compliance: Optional[dict] = None
    verification: Optional[dict] = None
    portfolio_analysis: Optional[dict] = None


@app.post("/api/chat", response_model=ChatResponse)
@limiter.limit(RATE_LIMIT)
async def api_chat(
    request: Request,
    chat_request: ChatRequest,
    llm_provider: Optional[str] = Header(default=None, alias="X-LLM-Provider"),
    llm_model: Optional[str] = Header(default=None, alias="X-LLM-Model"),
    llm_api_key: Optional[str] = Header(default=None, alias="X-LLM-API-Key"),
    user: AppUser = Depends(get_current_user),
    _: None = Depends(require_csrf),
):
    """API endpoint for chat"""
    request_settings = _request_model_settings(llm_provider, llm_model, llm_api_key)
    model_token = None
    if request_settings:
        model_token = set_request_model_config(**request_settings)

    cache_provider = request_settings["provider"] if request_settings else "groq"
    cache_model = request_settings["model"] if request_settings else MODEL_ANSWER
    answer_cache_key = f"{user.id}:{cache_provider}:{cache_model}:{chat_request.message}"
    # Requests from a browser-selected provider bypass the shared answer cache so a
    # customer's paid key is never silently bypassed by another request's result.
    allow_answer_cache = request_settings is None
    try:
        user_input = chat_request.message
        session_id = chat_request.session_id

        cached = cache_get(answer_cache, answer_cache_key) if allow_answer_cache else None
        if cached is not None:
            log_query(
                session_id=session_id,
                question=user_input,
                answer=cached['generation'],
                source=cached['source'],
                agents_run=["cache"],
                latency_ms=0.0,
                degraded=cached.get('degraded') or None,
                compliance_violations=(cached.get('compliance') or {}).get('violations'),
                verification_risk=(cached.get('verification') or {}).get('risk'),
                needs_review=needs_review(
                    cached.get('verification'), cached.get('compliance'),
                    cached.get('degraded'), cached['source']
                ), user_id=user.id
            )
            return ChatResponse(
                response=cached['generation'],
                session_id=session_id,
                source=cached['source'],
                degraded=cached.get('degraded') or None,
                compliance=cached.get('compliance'),
                verification=cached.get('verification')
            )

        state_key = f"{user.id}:{session_id}"
        if state_key not in conversation_states:
            logger.info(f"Creating new conversation state for user {user.id}")
            conversation_states[state_key] = initialize_state()

        state = conversation_states[state_key]

        state.update({
            "question": user_input,
            "generation": "",
            "documents": [],
            "source": "",
            "retry_count": 0,
            "degraded": "",
            "tokens_used": 0,
            "model_used": "",
            "fallback_used": False,
            "compliance": None,
            "verification": None,
            "portfolio_input": chat_request.portfolio,
            "portfolio_analysis": None,
            "session_id": session_id,
            "user_id": user.id
        })

        # Invoke workflow
        logger.info(f"Invoking advisor workflow for user {user.id}")
        start = time.perf_counter()
        result = await ai_workflow.ainvoke(state)
        latency_ms = (time.perf_counter() - start) * 1000
        state.update(result)

        generation = state.get('generation', '')
        source = state.get('source', '')
        degraded = state.get('degraded') or None
        compliance = state.get('compliance')
        verification = state.get('verification')
        portfolio_analysis = state.get('portfolio_analysis')

        agents_run = [
            name for name, attempted in (
                ("llm", state.get('llm_attempted')),
                ("rag", state.get('rag_attempted')),
                ("yfinance", state.get('yfinance_attempted')),
                ("duckduckgo", state.get('ddg_attempted')),
                ("portfolio_analyst", source == 'portfolio_analysis'),
                ("market_desk", source == 'market_desk'),
            ) if attempted
        ]

        log_query(
            session_id=session_id,
            question=user_input,
            answer=generation,
            source=source,
            agents_run=agents_run,
            latency_ms=latency_ms,
            tokens_used=state.get('tokens_used') or None,
            degraded=degraded,
            model_used=state.get('model_used') or None,
            fallback_used=state.get('fallback_used', False),
            compliance_violations=(compliance or {}).get('violations'),
            verification_risk=(verification or {}).get('risk'),
            needs_review=needs_review(verification, compliance, degraded, source), user_id=user.id
        )

        if allow_answer_cache and not used_live_market_data(source):
            cache_set(answer_cache, answer_cache_key, {
                'generation': generation, 'source': source, 'degraded': degraded,
                'compliance': compliance, 'verification': verification
            })

        return ChatResponse(
            response=generation,
            session_id=session_id,
            source=source,
            degraded=degraded,
            compliance=compliance,
            verification=verification,
            portfolio_analysis=portfolio_analysis
        )
    except Exception as e:
        logger.error(f"Error in api_chat ({type(e).__name__})")
        raise HTTPException(status_code=500, detail="Chat request failed. Check provider and API key settings.")
    finally:
        if model_token is not None:
            reset_request_model_config(model_token)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/api/history")
async def api_history(limit: int = 50, offset: int = 0, user: AppUser = Depends(get_current_user)):
    """Paginated query audit log"""
    rows = get_history(limit=min(max(limit, 1), 100), offset=max(offset, 0), user_id=user.id)
    return [row.model_dump() for row in rows]


@app.get("/api/stats")
async def api_stats(user: AppUser = Depends(get_current_user)):
    """Aggregate stats over the query audit log"""
    return get_stats(user_id=user.id)


class ReviewSubmission(BaseModel):
    verdict: Literal["approved", "rejected", "needs_correction"]


@app.get("/api/review")
async def api_review_queue(limit: int = 50, offset: int = 0, status: str = "pending", user: AppUser = Depends(get_current_user)):
    """Paginated review queue for the signed-in account."""
    rows = get_review_queue(limit=min(max(limit, 1), 100), offset=max(offset, 0), status=status, user_id=user.id)
    return [row.model_dump() for row in rows]


@app.post("/api/review/{query_id}")
@limiter.limit(RATE_LIMIT)
async def api_submit_review(request: Request, query_id: int, submission: ReviewSubmission, user: AppUser = Depends(get_current_user), _: None = Depends(require_csrf)):
    """Records a human verdict alongside the model's original answer, never overwriting it"""
    entry = submit_review(query_id, submission.verdict, user_id=user.id)
    if entry is None:
        raise HTTPException(status_code=404, detail="query not found")
    return entry.model_dump()


app.include_router(auth_router)
app.include_router(statements_router)


if __name__ == '__main__':  # pragma: no cover
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "5001")))
