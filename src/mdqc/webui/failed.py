"""Failed-files manager: view, retry, clear."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from mdqc.webui._deps import common_context, get_state, get_templates

log = logging.getLogger(__name__)

router = APIRouter(prefix="/failed")


def _entries(state: Any) -> list[Any]:
    failed = getattr(state, "failed", None)
    if failed is None:
        return []
    entries = getattr(failed, "entries", None)
    if entries is None:
        return []
    return list(entries)


def _render_table(request: Request, message: str | None = None) -> HTMLResponse:
    templates = get_templates(request)
    state = get_state(request)
    ctx = common_context(request)
    ctx["entries"] = _entries(state)
    ctx["message"] = message
    return templates.TemplateResponse(request, "failed/_table.html", ctx)


async def _requeue(state: Any, path: str) -> str:
    """Put one failed file back through extraction; returns what to tell the operator."""
    from mdqc.service.lifecycle import _vendor_for_path

    target = Path(path)
    finalizer = getattr(state, "finalizer", None)
    if finalizer is None:
        return "The agent is not ready to retry yet."
    if not target.exists():
        return f"{target.name} is no longer in the watch folder, so it cannot be retried."
    vendor = _vendor_for_path(state, target)
    if vendor is None:
        return f"No instrument watches the folder {target.parent}."
    await finalizer.observe(target, vendor, force=True)
    return (
        f"Retrying {target.name}. It appears under Recent activity on the "
        "dashboard in a minute or two, and leaves this list if it succeeds."
    )


@router.get("", response_class=HTMLResponse)
async def failed_index(request: Request) -> HTMLResponse:
    templates = get_templates(request)
    state = get_state(request)
    ctx = common_context(request)
    ctx["entries"] = _entries(state)
    return templates.TemplateResponse(request, "failed/index.html", ctx)


@router.post("/retry/{path:path}", response_class=HTMLResponse)
async def failed_retry(request: Request, path: str) -> HTMLResponse:
    state = get_state(request)
    failed = getattr(state, "failed", None)
    message: str | None = None
    # Only a file on the list: the path comes from the URL, and without this
    # the route would run Skyline on any file named in a request.
    if failed is not None and failed.find(path) is not None:
        try:
            message = await _requeue(state, path)
        except Exception as exc:
            log.warning("failed_retry_dispatch_failed", extra={"error": str(exc)})
            message = f"Could not retry: {exc}"
    elif failed is not None:
        message = "That file is no longer on this list."
    return _render_table(request, message)


@router.post("/clear", response_class=HTMLResponse)
async def failed_clear(request: Request) -> HTMLResponse:
    state = get_state(request)
    failed = getattr(state, "failed", None)
    if failed is not None:
        try:
            failed.clear()
        except Exception as exc:
            log.warning("failed_clear_failed", extra={"error": str(exc)})
    return _render_table(request)


__all__ = ["router"]
