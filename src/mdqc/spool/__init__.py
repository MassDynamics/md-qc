"""Durable on-disk spool for QC payloads.

Payloads move between pending/uploading/completed/failed with os.replace,
so a crash can never leave one half-written or in two places at once.
"""

from __future__ import annotations

from mdqc.spool.prune import prune_spool, recover_orphans
from mdqc.spool.store import Spool, SpoolError, SpoolFull

__all__ = [
    "Spool",
    "SpoolError",
    "SpoolFull",
    "prune_spool",
    "recover_orphans",
]
