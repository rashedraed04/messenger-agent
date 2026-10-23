"""
Dashboard FAQs management routes.
"""

from typing import Any

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from supabase import Client

from app.config import Settings
from app.dashboard.middleware import require_auth
from app.db.repositories.faqs import FAQRepository
from app.dependencies import get_config, get_db
from app.models.faq import FAQCreate, FAQUpdate

router = APIRouter(prefix="/dashboard/faqs", tags=["dashboard_faqs"])


@router.get("", response_class=HTMLResponse)
def list_faqs(
    request: Request,
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """List all FAQs with inline add/edit modal or table."""
    store_id = user.get("store_id") or config.default_store_id
    faq_repo = FAQRepository(db)
    faqs = faq_repo.list_all(store_id)

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "dashboard/faqs/list.html",
        {
            "request": request,
            "user": user,
            "faqs": faqs,
            "active_page": "faqs",
        },
    )


@router.post("/new")
def create_faq(
    question_ar: str = Form(...),
    answer_ar: str = Form(...),
    sort_order: int = Form(0),
    is_active: bool = Form(True),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Create a new FAQ."""
    store_id = user.get("store_id") or config.default_store_id
    faq_repo = FAQRepository(db)
    faq_repo.create(
        store_id,
        FAQCreate(
            store_id=store_id,
            question_ar=question_ar,
            answer_ar=answer_ar,
            sort_order=sort_order,
            is_active=is_active,
        ),
    )

    return RedirectResponse(
        url="/dashboard/faqs?msg=created",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{faq_id}/edit")
def edit_faq(
    faq_id: str,
    question_ar: str = Form(...),
    answer_ar: str = Form(...),
    sort_order: int = Form(0),
    is_active: bool = Form(False),
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Update an existing FAQ."""
    store_id = user.get("store_id") or config.default_store_id
    faq_repo = FAQRepository(db)
    faq_repo.update(
        store_id=store_id,
        faq_id=faq_id,
        updates=FAQUpdate(
            question_ar=question_ar,
            answer_ar=answer_ar,
            sort_order=sort_order,
            is_active=is_active,
        ),
    )

    return RedirectResponse(
        url="/dashboard/faqs?msg=updated",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{faq_id}/delete")
def delete_faq(
    faq_id: str,
    user: dict[str, Any] = Depends(require_auth),
    db: Client = Depends(get_db),
    config: Settings = Depends(get_config),
):
    """Delete an FAQ."""
    store_id = user.get("store_id") or config.default_store_id
    faq_repo = FAQRepository(db)
    faq_repo.delete(store_id, faq_id)

    return RedirectResponse(
        url="/dashboard/faqs?msg=deleted",
        status_code=status.HTTP_303_SEE_OTHER,
    )
