"""
Product photos uploaded from the dashboard, stored in Supabase Storage.

Photos live in the public `product-images` bucket (migration 008) under
`<store_id>/<random>.<ext>`, and the product keeps the photo's public URL in
`image_url`, so the storefront and the bot use it like any pasted link.
The browser shrinks photos before upload; the size cap here is a backstop.
"""

import logging
from uuid import uuid4

from supabase import Client

logger = logging.getLogger(__name__)

BUCKET = "product-images"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
CACHE_SECONDS = 60 * 60 * 24 * 365  # every upload gets a new path, so cache for long


class PhotoError(ValueError):
    """The uploaded file is not an acceptable photo; the message is shown to the admin."""


def detect_photo_type(data: bytes) -> tuple[str, str] | None:
    """(mime type, extension) from the file's first bytes, or None if not JPEG/PNG/WebP."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def public_prefix(supabase_url: str) -> str:
    return f"{supabase_url}/storage/v1/object/public/{BUCKET}/"


def upload_photo(db: Client, supabase_url: str, store_id: str, data: bytes) -> str:
    """Store a photo and return its public URL; raises PhotoError if it can't be used."""
    if not data:
        raise PhotoError("الملف المرفوع فارغ.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise PhotoError("حجم الصورة كبير جداً (الحد الأقصى 5 ميغابايت).")
    detected = detect_photo_type(data)
    if not detected:
        raise PhotoError("نوع الملف غير مدعوم. استخدم صورة JPG أو PNG أو WebP.")
    mime_type, ext = detected

    path = f"{store_id}/{uuid4().hex}.{ext}"
    try:
        db.storage.from_(BUCKET).upload(
            path, data, {"content-type": mime_type, "cache-control": str(CACHE_SECONDS)}
        )
    except Exception as e:
        logger.error("Product photo upload failed (is migration 008 applied?): %s", e)
        raise PhotoError("تعذر رفع الصورة. حاول مرة أخرى بعد قليل.") from e
    return public_prefix(supabase_url) + path


def delete_photo(db: Client, supabase_url: str, url: str | None) -> None:
    """Remove a photo this app uploaded; pasted links to other sites are left alone."""
    prefix = public_prefix(supabase_url)
    if not url or not url.startswith(prefix):
        return
    try:
        db.storage.from_(BUCKET).remove([url[len(prefix):]])
    except Exception as e:
        logger.warning("Could not delete product photo %s: %s", url, e)
