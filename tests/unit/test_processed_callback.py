"""What the agent records when a watched file reaches the pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mdqc.config.schema import Config, InstrumentConfig
from mdqc.service import lifecycle
from mdqc.types import (
    ExtractionResult,
    ExtractionStatus,
    RunMetrics,
    TargetMetric,
    Vendor,
)


class _StubExtractor:
    async def extract(self, template: Path, raw: Path, **_: Any) -> ExtractionResult:
        return ExtractionResult(
            raw_file_path=raw,
            template_path=template,
            target_metrics=[
                TargetMetric(
                    target_id="PEPA", peptide_sequence="PEPA", protein_name="Targets",
                    peak_area=1000.0, retention_time=5.0, detected=True,
                )
            ],
            run_metrics=RunMetrics(targets_found=1, targets_expected=1, target_recovery_pct=100.0),
        )


async def _state(tmp_path: Path) -> tuple[lifecycle.AppState, Path, list[tuple[str, dict]]]:
    watch = tmp_path / "watch"
    watch.mkdir()
    cfg = Config(
        instruments=[
            InstrumentConfig(
                id="astral-1", vendor=Vendor.THERMO, watch_path=watch,
                file_pattern="*.raw", template="QC_Method.sky",
            )
        ]
    )
    state = await lifecycle._build_state(cfg)
    state.extractor = _StubExtractor()  # type: ignore[assignment]
    events: list[tuple[str, dict]] = []
    state.events_pubsub.publish = lambda t, p: events.append((t, p))  # type: ignore[method-assign]
    return state, watch, events


@pytest.mark.asyncio
async def test_a_file_that_extracts_leaves_the_failed_list(
    tmp_path: Path, tmp_data_dir: Path
) -> None:
    """v1.2.1 kept the entry on the Failed page after the file had gone through."""
    state, watch, _events = await _state(tmp_path)
    raw = watch / "SSC_200SPD_r01.raw"
    raw.write_bytes(b"x")
    state.failed.add(str(raw), "astral-1", "template not found: QC_Method.sky")

    await state.finalizer._callback(raw, Vendor.THERMO)

    assert state.failed.find(str(raw)) is None
    assert state.activity.recent(1)[0].result is ExtractionStatus.SUCCESS


@pytest.mark.asyncio
async def test_a_skipped_sample_is_not_announced_as_an_extraction(
    tmp_path: Path, tmp_data_dir: Path
) -> None:
    """A skipped file published "extraction_completed", which the tray showed
    as an "Extraction completed" toast."""
    state, watch, events = await _state(tmp_path)
    sample = watch / "20261109_plasma_cohort_12.raw"
    sample.write_bytes(b"x")

    await state.finalizer._callback(sample, Vendor.THERMO)

    types = [t for t, _ in events]
    assert lifecycle.EVENT_FILE_SKIPPED in types
    assert lifecycle.EVENT_EXTRACTION_COMPLETED not in types
    entry = state.activity.recent(1)[0]
    assert entry.result is ExtractionStatus.SKIPPED
    assert entry.detail == "not a QC run"
