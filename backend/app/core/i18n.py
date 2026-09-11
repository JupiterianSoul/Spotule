"""Backend localization for API error messages and worker-generated text (milestone titles,
backup playlist names, emails). The UI has its own catalogue in frontend/messages/*.json.

Locale resolution order: explicit `?lang=` → user preference → Accept-Language → default.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.core.config import settings

_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locales"
_CATALOG: dict[str, dict[str, Any]] = {}


def _load() -> None:
    if _CATALOG:
        return
    for code in settings.supported_locales:
        path = _LOCALE_DIR / f"{code}.json"
        _CATALOG[code] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def negotiate_locale(accept_language: str | None, preferred: str | None = None) -> str:
    if preferred in settings.supported_locales:
        return preferred  # type: ignore[return-value]
    if accept_language:
        for part in accept_language.split(","):
            code = part.split(";")[0].strip().lower()[:2]
            if code in settings.supported_locales:
                return code
    return settings.default_locale


def _walk(catalog: dict[str, Any], segments: Sequence[str]) -> Any:
    node: Any = catalog
    for segment in segments:
        node = node.get(segment) if isinstance(node, dict) else None
        if node is None:
            return None
    return node


def t(key: str | Sequence[str], locale: str | None = None, **params: Any) -> str:
    """Translate a dotted key, e.g. t("errors.not_authenticated", "fr"), or a sequence of
    segments when one segment itself contains dots: t(("tools", "playlist.true_shuffle", "title"))."""
    _load()
    segments = key.split(".") if isinstance(key, str) else list(key)
    locale = locale if locale in _CATALOG else settings.default_locale
    node = _walk(_CATALOG.get(locale, {}), segments)
    if node is None:  # fall back to default locale, then to the key itself
        node = _walk(_CATALOG.get(settings.default_locale, {}), segments)
    if node is None:
        return key if isinstance(key, str) else ".".join(segments)
    return str(node).format(**params) if params else str(node)
