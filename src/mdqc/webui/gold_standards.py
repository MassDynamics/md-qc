"""Gold Standards page: SSC run review and per-(instrument, SPD) baseline selection.

Read/write against mdqc.gold_standards (agent-local storage, separate from
spool/completed). Does not touch QcPayload.baseline_context — see that
module's docstring for why the payload wiring is a later step.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from mdqc import gold_standards as gs
from mdqc import upload_gate
from mdqc.webui._deps import common_context, get_state, get_templates

router = APIRouter(prefix="/gold-standards")


def _instrument_ids(cfg: Any) -> list[str]:
    return [i.id for i in cfg.instruments]


def _resolve_instrument(requested: str | None, cfg: Any) -> str | None:
    ids = _instrument_ids(cfg)
    if requested and requested in ids:
        return requested
    return ids[0] if ids else None


def _parse_spd(raw: Any) -> int | None:
    if raw in (None, "", "unknown"):
        return None
    try:
        return int(str(raw))
    except ValueError:
        return None


def _resolve_spd(requested: str | None, available: list[int]) -> int | None:
    parsed = _parse_spd(requested)
    if parsed is not None and parsed in available:
        return parsed
    return available[0] if available else None


MIN_BASELINE_RUNS_ADVISED = 3
"""Below this a saved baseline carries a warning. Not a block: the site
decides how many runs make its reference."""


def _runs_without_targets(
    instrument_id: str | None, spd: int | None, run_ids: list[str]
) -> list[str]:
    """File names of the selected runs in which no target was detected."""
    chosen = set(run_ids)
    return [
        str(r.get("raw_file_name") or r["run_id"])
        for r in gs.list_ssc0_runs(instrument_id, spd)
        if r["run_id"] in chosen and r.get("targets_found") == 0
    ]


async def _page_context(
    request: Request,
    instrument_id: str | None,
    spd: int | None,
    saved: bool = False,
    error: str | None = None,
    released: int | None = None,
    notice: str | None = None,
    warning: str | None = None,
) -> dict[str, Any]:
    state = get_state(request)
    cfg = state.cfg
    ctx = common_context(request)

    runs = gs.list_ssc0_runs(instrument_id, spd) if instrument_id else []
    active = gs.get_active_baseline(instrument_id, spd) if instrument_id else None
    # Runs that arrived marked as gold standards are the ones to tick: that is
    # what the operator came here to save.
    marked = set(upload_gate.gold_run_ids(instrument_id, spd)) if instrument_id else set()
    known = {r["run_id"] for r in runs}
    if marked & known:
        default_checked = marked & known
    else:
        default_checked = (
            set(active["source_run_ids"]) if active else known
        )
    gate_reason = (
        upload_gate.hold_reason(instrument_id, spd)
        if instrument_id and upload_gate.enabled(cfg) else None
    )
    held_here = sum(
        1 for _p, d in state.spool.held_payloads()
        if (d.get("run") or {}).get("instrument_id") == instrument_id
        and (d.get("run") or {}).get("spd") == spd
    ) if getattr(state, "spool", None) is not None and instrument_id else 0

    # The heatmap shades against the same warn/fail percentages that decide a
    # run's payload verdict. Two sets of numbers for the same judgement is how
    # a page ends up disagreeing with the verdict it sits next to.
    th = cfg.thresholds_for(spd)
    ctx.update(
        {
            "instruments": _instrument_ids(cfg),
            "instrument_id": instrument_id,
            "available_spds": gs.list_available_spds(instrument_id) if instrument_id else [],
            "spd": spd,
            "runs_data": runs,
            "default_checked": sorted(default_checked),
            "active_baseline": active,
            "baselines": gs.list_baselines(instrument_id, spd) if instrument_id else [],
            "baseline_reference": (active or {}).get("per_peptide") or {},
            "dev_warn_pct": th.peak_area_deviation_pct_warn,
            "dev_fail_pct": th.peak_area_deviation_pct_fail,
            "rt_dev_pct_max": th.rt_deviation_pct_max,
            "saved": saved,
            "error": error,
            "notice": notice,
            "warning": warning,
            "gate_enabled": upload_gate.enabled(cfg),
            "gate_reason": gate_reason,
            "gate_reason_text": upload_gate.REASON_TEXT.get(gate_reason or "", ""),
            "gate_held_count": held_here,
            "released": released,
        }
    )
    return ctx


@router.get("", response_class=HTMLResponse)
async def gold_standards_index(request: Request) -> HTMLResponse:
    state = get_state(request)
    cfg = state.cfg
    instrument_id = _resolve_instrument(request.query_params.get("instrument"), cfg)
    available_spds = gs.list_available_spds(instrument_id) if instrument_id else []
    spd = _resolve_spd(request.query_params.get("spd"), available_spds)

    templates = get_templates(request)
    ctx = await _page_context(request, instrument_id, spd)
    return templates.TemplateResponse(request, "gold_standards/index.html", ctx)


@router.post("/runs/delete", response_class=HTMLResponse)
async def gold_standards_delete_run(request: Request) -> HTMLResponse:
    """Forget one recorded run - a test injection, or one recorded against the
    wrong instrument. Leaving it unticked keeps it out of a baseline but not
    out of the page."""
    form = await request.form()
    instrument_id = str(form.get("instrument_id") or "") or None
    spd = _parse_spd(form.get("spd"))
    run_id = str(form.get("run_id") or "")
    removed = gs.delete_ssc0_run(instrument_id, spd, run_id)
    ctx = await _page_context(
        request, instrument_id, spd,
        notice="Run removed from this page." if removed else None,
        error=None if removed else "That run was not found.",
    )
    return get_templates(request).TemplateResponse(request, "gold_standards/index.html", ctx)


@router.post("/baselines/delete", response_class=HTMLResponse)
async def gold_standards_delete_baseline(request: Request) -> HTMLResponse:
    """Remove a saved baseline. Deleting the active one promotes the newest
    remaining, so a gold standard saved by mistake is no longer permanent."""
    form = await request.form()
    instrument_id = str(form.get("instrument_id") or "") or None
    spd = _parse_spd(form.get("spd"))
    baseline_id = str(form.get("baseline_id") or "")
    removed = gs.delete_baseline(instrument_id, spd, baseline_id)
    notice: str | None = None
    if removed:
        now_active = gs.get_active_baseline(instrument_id, spd)
        notice = (
            f"Baseline deleted. \"{now_active.get('label')}\" is now the active baseline."
            if now_active
            else "Baseline deleted. There is no active baseline at this SPD now."
        )
    ctx = await _page_context(
        request, instrument_id, spd,
        notice=notice,
        error=None if removed else "That baseline was not found.",
    )
    return get_templates(request).TemplateResponse(request, "gold_standards/index.html", ctx)


@router.post("/save", response_class=HTMLResponse)
async def gold_standards_save(request: Request) -> HTMLResponse:
    state = get_state(request)
    cfg = state.cfg
    form = await request.form()

    instrument_id = str(form.get("instrument_id") or "") or None
    spd = _parse_spd(form.get("spd"))
    label = str(form.get("label") or "")
    run_ids = [str(r) for r in form.getlist("run_id")]

    error: str | None = None
    warning: str | None = None
    saved = False
    empty = _runs_without_targets(instrument_id, spd, run_ids)
    if not run_ids:
        error = "Select at least one SSC run before saving a baseline."
    elif empty:
        # Extraction "succeeded" on these but found no peptides, usually a
        # method that does not match the template. A baseline built on them
        # has no values, and every later comparison comes out blank.
        error = (
            "No targets were found in "
            + ", ".join(empty)
            + ", so a baseline cannot include "
            + ("it" if len(empty) == 1 else "them")
            + ". Untick "
            + ("it" if len(empty) == 1 else "them")
            + ", or check the acquisition method against the Skyline template."
        )
    else:
        gs.save_baseline(instrument_id, spd, run_ids, label, cfg.peptide_classes)
        saved = True
        if len(run_ids) < MIN_BASELINE_RUNS_ADVISED:
            warning = (
                f"This baseline rests on {len(run_ids)} run"
                f"{'s' if len(run_ids) != 1 else ''}. With fewer than "
                f"{MIN_BASELINE_RUNS_ADVISED} there is no measure of normal "
                "run-to-run variation; replace it once more SSC runs are in."
            )

    # A new baseline is what held runs were waiting for: re-score them
    # against it and let them upload.
    released: int | None = None
    if saved and getattr(state, "spool", None) is not None:
        released = upload_gate.release(cfg, state.spool, instrument_id, spd, rescore=True)

    templates = get_templates(request)
    ctx = await _page_context(
        request, instrument_id, spd, saved=saved, error=error, released=released,
        warning=warning,
    )
    return templates.TemplateResponse(request, "gold_standards/index.html", ctx)


@router.post("/gate/pause", response_class=HTMLResponse)
async def gold_standards_gate_pause(request: Request) -> HTMLResponse:
    """Hold uploads while a new baseline is set — for gold-standard runs that
    arrived without their marker, which the agent cannot recognise itself."""
    form = await request.form()
    instrument_id = str(form.get("instrument_id") or "") or None
    spd = _parse_spd(form.get("spd"))
    upload_gate.pause(instrument_id, spd)
    ctx = await _page_context(request, instrument_id, spd)
    return get_templates(request).TemplateResponse(request, "gold_standards/index.html", ctx)


@router.post("/gate/release", response_class=HTMLResponse)
async def gold_standards_gate_release(request: Request) -> HTMLResponse:
    """Upload the held runs as they are, without saving a new baseline."""
    state = get_state(request)
    form = await request.form()
    instrument_id = str(form.get("instrument_id") or "") or None
    spd = _parse_spd(form.get("spd"))
    released = upload_gate.release(state.cfg, state.spool, instrument_id, spd, rescore=False)
    ctx = await _page_context(request, instrument_id, spd, released=released)
    return get_templates(request).TemplateResponse(request, "gold_standards/index.html", ctx)


__all__ = ["router"]
