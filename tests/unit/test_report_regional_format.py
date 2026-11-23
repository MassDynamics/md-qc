"""Skyline reports and the PC's regional number format.

Skyline's "csv" follows the Windows regional format unless it is asked for the
invariant one. On a PC set to Danish, German, French and so on, that is
semicolons between columns and commas as decimal points. The agent read such a
report as "every target present, none detected, no acquisition time" and
called the run a success.

Both fixtures are the first rows of real SkylineCmd output for one raw file,
exported under a Danish format: one without ``--report-invariant`` and one with.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from mdqc.config.schema import SkylineConfig
from mdqc.extractor import Extractor, report
from mdqc.extractor.report import (
    ReportFormatError,
    collapse_transitions_to_peptides,
    parse_skyline_csv,
    parse_skyline_run_metadata,
)
from mdqc.extractor.skyline import SkylineRunResult, run_skyline
from mdqc.types import ExtractionStatus

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
DANISH = FIXTURES / "skyline_report_danish_format.csv"
INVARIANT = FIXTURES / "skyline_report_invariant.csv"


def test_a_semicolon_report_is_refused_not_read_as_empty() -> None:
    with pytest.raises(ReportFormatError, match="regional number format"):
        parse_skyline_csv(DANISH)
    with pytest.raises(ReportFormatError):
        parse_skyline_run_metadata(DANISH)


def test_the_invariant_report_reads_every_target() -> None:
    peptides = collapse_transitions_to_peptides(parse_skyline_csv(INVARIANT))
    assert len(peptides) == 3
    assert all(p.detected for p in peptides)
    assert peptides[0].retention_time == pytest.approx(1.9577779769897461)
    assert peptides[0].peak_area == pytest.approx(99832992)


@pytest.mark.parametrize("host_day_first", [True, False])
def test_the_invariant_date_is_month_first_on_any_host(
    monkeypatch: pytest.MonkeyPatch, host_day_first: bool
) -> None:
    """02/10/2026 is the 10th of February. Every field is 12 or less, so the
    values cannot settle the order, and a day-first host would read October."""
    monkeypatch.setattr(report, "locale_prefers_day_first", lambda: host_day_first)
    acquired, modified = parse_skyline_run_metadata(INVARIANT, invariant=True)
    assert acquired is not None and acquired.startswith("2026-02-10T11:07:23")
    assert modified is not None and modified.startswith("2026-11-17T08:27:02")


@pytest.mark.asyncio
async def test_skyline_is_asked_for_the_invariant_format(tmp_path: Path) -> None:
    template = tmp_path / "t.sky"
    template.write_text("<srm_settings/>")
    raw = tmp_path / "SSC_200SPD.raw"
    raw.write_text("r")
    proc = AsyncMock()
    proc.pid = 1
    proc.returncode = 0
    proc.communicate.return_value = (b"", b"")
    with (
        patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)) as spawn,
        patch("mdqc.extractor.skyline._apply_priority"),
    ):
        await run_skyline(
            skyline_exe=tmp_path / "SkylineCmd.exe",
            template=template,
            raw_file=raw,
            report_name="MD_QC_Report",
            output_csv=tmp_path / "out.csv",
        )
    assert "--report-invariant" in spawn.call_args.args


@pytest.mark.asyncio
async def test_an_unreadable_report_fails_the_extraction(tmp_path: Path) -> None:
    """Should Skyline still hand back a regional report, the run is FAILED
    with the reason, never a success with no targets."""
    template = tmp_path / "template.sky"
    template.write_text("t")
    raw = tmp_path / "SSC_200SPD.raw"
    raw.write_text("r")
    exe = tmp_path / "SkylineCmd.exe"
    exe.write_text("x")
    ex = Extractor(SkylineConfig(path=str(exe)), work_dir=tmp_path / "work")

    async def side_effect(**kwargs: object) -> SkylineRunResult:
        out = kwargs["output_csv"]
        assert isinstance(out, Path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(DANISH.read_bytes())
        return SkylineRunResult(returncode=0, stdout="ok", stderr="", duration_ms=1, version="26")

    with patch("mdqc.extractor.run_skyline", new=AsyncMock(side_effect=side_effect)):
        result = await ex.extract(template=template, raw_file=raw)

    assert result.status == ExtractionStatus.FAILED
    assert "regional number format" in (result.error_message or "")
