"""
FastAPI application factory.

Creates and configures the main application with:
- Lifespan events (startup/shutdown)
- Route registration
- Static file serving
- Jinja2 template engine
- CSRF protection for dashboard/auth forms
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.dashboard.csrf import CSRFCookieMiddleware, csrf_input, csrf_protect, get_csrf_token
from app.dashboard.middleware import block_demo_writes
from app.dashboard.routes import auth_router, dashboard_router
from app.routes.health import router as health_router
from app.routes.internal import router as internal_router
from app.routes.storefront import router as storefront_router
from app.routes.webhook import router as webhook_router
from app.services.branding import build_branding, get_branding

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("messenger_agent")

# ---------------------------------------------------------------------------
# Template context: store identity for every page
# ---------------------------------------------------------------------------
def branding_context(request) -> dict:
    """Expose `brand` (store name, tagline, storefront copy) to all templates."""
    from app.dependencies import get_config, get_db

    overrides = request.app.dependency_overrides
    config = overrides.get(get_config, get_config)()
    if config.app_env == "testing" and get_db not in overrides:
        # Unit tests run without a reachable database
        return {"brand": build_branding({})}
    ttl = 0 if config.app_env == "testing" else None
    try:
        db = overrides.get(get_db, get_db)()
        kwargs = {"ttl": ttl} if ttl is not None else {}
        return {"brand": get_branding(db, config.default_store_id, **kwargs)}
    except Exception as e:
        logger.info("Branding unavailable, using defaults: %s", e)
        return {"brand": build_branding({})}


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # project root
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "static"


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — runs once on startup and shutdown."""
    settings = get_settings()
    logger.info(
        "Starting Messenger Agent — env=%s, store=%s",
        settings.app_env,
        settings.default_store_id,
    )
    yield
    logger.info("Shutting down Messenger Agent")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title="Messenger Agent — Hajj & Umrah Gifts Store",
        description="Facebook Messenger AI sales agent and management dashboard",
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        lifespan=lifespan,
    )

    # --- Static files ---
    if STATIC_DIR.exists():
        application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # --- Templates ---
    if TEMPLATES_DIR.exists():
        templates = Jinja2Templates(directory=str(TEMPLATES_DIR), context_processors=[branding_context])
        templates.env.globals["csrf_input"] = csrf_input
        templates.env.globals["csrf_token"] = get_csrf_token
        application.state.templates = templates

    # --- CSRF token cookie for dashboard/auth pages ---
    application.add_middleware(CSRFCookieMiddleware, secure=settings.is_production)

    # --- Routers ---
    application.include_router(storefront_router)
    application.include_router(health_router)
    application.include_router(webhook_router)
    application.include_router(internal_router)
    application.include_router(auth_router, dependencies=[Depends(csrf_protect)])
    application.include_router(dashboard_router, dependencies=[Depends(csrf_protect), Depends(block_demo_writes)])

    return application


# ---------------------------------------------------------------------------
# Module-level app instance (used by uvicorn: app.main:app)
# ---------------------------------------------------------------------------
app = create_app()
