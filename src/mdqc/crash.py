"""Crash reporting: sys.excepthook + faulthandler + Windows MessageBoxW prompt.

Install both hooks early. A hand-rolled URL encoder is buggy on high-bit
characters; this module uses ``urllib.parse.quote`` instead.
"""

from __future__ import annotations

import contextlib
import faulthandler
import os
import platform
import sys
import tempfile
import traceback as _traceback
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any
from urllib.parse import quote

from mdqc import __version__ as _agent_version
from mdqc.config import paths
from mdqc.log import get_logger

log = get_logger(__name__)

GITHUB_ISSUE_URL = "https://github.com/MassDynamics/md-qc/issues/new"
SUPPORT_EMAIL = "engineering@massdynamics.com"

_installed = False
_original_excepthook: Any = None


def _compose_crash_report(
    exc_type: type[BaseException],
    exc_value: BaseException,
    traceback_obj: TracebackType | None,
) -> str:
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    tb_lines = _traceback.format_exception(exc_type, exc_value, traceback_obj)
    tb_text = "".join(tb_lines)
    return (
        "MD QC Agent Crash Report\n"
        "========================\n\n"
        f"Timestamp: {timestamp}\n"
        f"Agent version: {_agent_version}\n"
        f"Python version: {sys.version.split()[0]}\n"
        f"Platform: {platform.platform()}\n"
        f"Exception type: {exc_type.__name__}\n"
        f"Message: {exc_value}\n\n"
        "Traceback:\n"
        f"{tb_text}\n"
    )


def _truncate_for_url(report: str, max_chars: int = 1500) -> str:
    if len(report) <= max_chars:
        return report
    suffix = "\n...[truncated]"
    head = max_chars - len(suffix)
    if head < 0:
        head = 0
    return report[:head] + suffix


def _write_crash_report(report: str) -> Path | None:
    try:
        crashes = paths.crashes_dir()
        crashes.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target = crashes / f"crash_{ts}.txt"
        fd, tmp_str = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=str(crashes)
        )
        tmp_path = Path(tmp_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(report)
            os.replace(tmp_path, target)
        except Exception:
            with contextlib.suppress(FileNotFoundError):
                tmp_path.unlink()
            raise
        return target
    except Exception as exc:
        log.warning("crash_write_failed", error=str(exc))
        return None


def _compose_public_issue_body(exc_type: type[BaseException]) -> str:
    """The text prefilled into a *public* GitHub issue.

    Only the agent version, Python version, platform and exception type. The
    exception message and traceback stay in the local crash file: they can
    carry raw file names, instrument serials, sample names and paths, which
    must not be published without the user reviewing them first.
    """
    return (
        "MD QC Agent crash\n\n"
        f"Agent version: {_agent_version}\n"
        f"Python version: {sys.version.split()[0]}\n"
        f"Platform: {platform.platform()}\n"
        f"Exception type: {exc_type.__name__}\n\n"
        "This issue is public. The full traceback is in the crash file named "
        "in the error dialog. Paste the parts that help, after removing "
        "serial numbers, raw file names, sample or site names and file paths. "
        "If the details can't be made public, email "
        f"{SUPPORT_EMAIL} instead.\n"
    )


def _build_issue_url(exc_type: type[BaseException]) -> str:
    title = f"Crash: {exc_type.__name__}"
    body = _truncate_for_url(_compose_public_issue_body(exc_type))
    return f"{GITHUB_ISSUE_URL}?title={quote(title)}&body={quote(body)}"


def _show_messagebox(crash_path: Path | None, url: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        MB_YESNO = 4
        MB_ICONERROR = 16
        IDYES = 6
        path_str = str(crash_path) if crash_path is not None else "<not written>"
        message = (
            "MD QC Agent has crashed.\n\n"
            f"Crash report: {path_str}\n\n"
            "Open a public GitHub issue? Only the agent, Python and Windows "
            "versions and the error type are filled in; the crash report "
            "stays on this PC. For "
            f"confidential details, email {SUPPORT_EMAIL} instead."
        )
        result = ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0,
            message,
            "MD QC Agent — Crash",
            MB_YESNO | MB_ICONERROR,
        )
        if result == IDYES:
            try:
                webbrowser.open(url)
            except Exception as exc:
                log.warning("crash_browser_failed", error=str(exc))
            return True
        return False
    except Exception as exc:
        log.warning("crash_messagebox_failed", error=str(exc))
        return False


def _excepthook(
    exc_type: type[BaseException],
    exc_value: BaseException,
    traceback_obj: TracebackType | None,
) -> None:
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        if _original_excepthook is not None:
            _original_excepthook(exc_type, exc_value, traceback_obj)
        return

    report = _compose_crash_report(exc_type, exc_value, traceback_obj)
    crash_path = _write_crash_report(report)
    log.error(
        "unhandled_exception",
        exc_type=exc_type.__name__,
        message=str(exc_value),
        crash_file=str(crash_path) if crash_path else None,
    )

    if _show_messagebox_enabled:
        url = _build_issue_url(exc_type)
        _show_messagebox(crash_path, url)

    if _original_excepthook is not None:
        with contextlib.suppress(Exception):
            _original_excepthook(exc_type, exc_value, traceback_obj)


_show_messagebox_enabled = True


def install_crash_handlers(*, log_messagebox: bool = True) -> None:
    global _installed, _original_excepthook, _show_messagebox_enabled
    if _installed:
        return
    _show_messagebox_enabled = log_messagebox
    _original_excepthook = sys.excepthook
    sys.excepthook = _excepthook
    try:
        faulthandler.enable()
    except Exception as exc:
        log.warning("faulthandler_enable_failed", error=str(exc))
    _installed = True


__all__ = [
    "GITHUB_ISSUE_URL",
    "SUPPORT_EMAIL",
    "install_crash_handlers",
]
