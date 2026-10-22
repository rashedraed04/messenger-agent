"""
Image downloads for product recognition.

Customers often open the chat with a photo or screenshot of a product. The
photo (from Meta's CDN) and the catalog's product photos are downloaded here
and passed to the AI model, which matches the photo against the catalog.
"""

import logging
import time
from urllib.parse import urlparse

import httpx

from app.ai.provider_interface import ImageInput

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 5 * 1024 * 1024
SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}

# Messenger attachment URLs are served from Meta's CDNs only
MESSENGER_IMAGE_HOSTS = ("fbcdn.net", "fbsbx.com", "facebook.com")

CATALOG_CACHE_TTL_SECONDS = 3600
_catalog_cache: dict[str, tuple[float, ImageInput | None]] = {}


def _url_allowed(url: str, allowed_hosts: tuple[str, ...] | None) -> bool:
    parsed = urlparse(url)
    if allowed_hosts is None:
        return parsed.scheme in ("http", "https") and bool(parsed.hostname)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(
        host == allowed or host.endswith(f".{allowed}") for allowed in allowed_hosts
    )


async def fetch_image(
    url: str,
    allowed_hosts: tuple[str, ...] | None = None,
    timeout: float = 10.0,
) -> ImageInput | None:
    """Download an image; None if the URL, response, type or size is not acceptable."""
    if not url or not _url_allowed(url, allowed_hosts):
        logger.warning("Refusing to fetch image from %r", url)
        return None

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream("GET", url) as resp:
                # Redirects must not leave the allowed hosts either
                if resp.status_code != 200 or not _url_allowed(str(resp.url), allowed_hosts):
                    logger.warning("Image fetch failed (%s) for %s", resp.status_code, url)
                    return None
                mime_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                if mime_type not in SUPPORTED_MIME_TYPES:
                    logger.warning("Unsupported image type %r from %s", mime_type, url)
                    return None
                data = bytearray()
                async for chunk in resp.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        logger.warning("Image larger than %d bytes: %s", MAX_IMAGE_BYTES, url)
                        return None
    except httpx.HTTPError as e:
        logger.warning("Image fetch error for %s: %s", url, e)
        return None

    return ImageInput(data=bytes(data), mime_type=mime_type, source_url=url)


async def fetch_messenger_image(url: str) -> ImageInput | None:
    """Download a photo a customer sent on Messenger."""
    return await fetch_image(url, allowed_hosts=MESSENGER_IMAGE_HOSTS)


async def fetch_catalog_image(url: str) -> ImageInput | None:
    """Download a catalog product photo, cached so repeat photos don't re-download it."""
    now = time.monotonic()
    cached = _catalog_cache.get(url)
    if cached and now - cached[0] < CATALOG_CACHE_TTL_SECONDS:
        return cached[1]
    image = await fetch_image(url)
    _catalog_cache[url] = (now, image)
    return image
