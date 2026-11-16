"""The bundled Skyline template reaches the methods folder on start.

v1.2.1 shipped `ensure_bundled_assets` with no caller: every fresh install
had an empty methods folder, and its first QC run failed with "template not
found: QC_Method.sky".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mdqc.config import paths
from mdqc.types import Vendor

_NAMES = ("QC_Method.sky", "MD_QC_Report.skyr")
_TRANSITION = '<transition fragment_type="precursor" />'


@pytest.fixture()
def bundled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    src = tmp_path / "assets"
    src.mkdir()
    (src / "QC_Method.sky").write_text(f"bundled {_TRANSITION}", encoding="utf-8")
    (src / "MD_QC_Report.skyr").write_text("bundled report", encoding="utf-8")
    monkeypatch.setattr(paths, "bundled_assets_dir", lambda: src)
    return src


def test_copies_template_and_report_into_an_empty_methods_folder(
    bundled: Path, tmp_data_dir: Path
) -> None:
    paths.ensure_bundled_assets()
    for name in _NAMES:
        assert (paths.methods_dir() / name).read_text(encoding="utf-8").startswith("bundled")


def test_never_replaces_a_template_already_there(
    bundled: Path, tmp_data_dir: Path
) -> None:
    """A site keeps its own panel under the bundled name. An upgrade's files
    are newer by mtime, and the old newer-wins rule would have replaced it."""
    paths.methods_dir().mkdir(parents=True, exist_ok=True)
    site = paths.methods_dir() / "QC_Method.sky"
    site.write_text(f"site panel {_TRANSITION}", encoding="utf-8")
    report = paths.methods_dir() / "MD_QC_Report.skyr"
    report.write_text("site report", encoding="utf-8")

    paths.ensure_bundled_assets()

    assert site.read_text(encoding="utf-8").startswith("site panel")
    assert report.read_text(encoding="utf-8") == "site report"


def test_replaces_the_template_that_had_no_transitions(
    bundled: Path, tmp_data_dir: Path
) -> None:
    """The template shipped up to v1.2.1 listed peptides and no transitions,
    so every run came back 0 of 43. Copied in by hand, it must not survive."""
    paths.methods_dir().mkdir(parents=True, exist_ok=True)
    dud = paths.methods_dir() / "QC_Method.sky"
    dud.write_text("<peptide sequence='AAVPSGASTGIYEALELR' />", encoding="utf-8")

    paths.ensure_bundled_assets()

    assert dud.read_text(encoding="utf-8").startswith("bundled")
    kept = paths.methods_dir() / "QC_Method.no-transitions.bak"
    assert "AAVPSGASTGIYEALELR" in kept.read_text(encoding="utf-8")


def test_the_shipped_template_has_something_to_extract() -> None:
    """Guards the real asset: v1.2.1's had 43 peptides and 0 transitions."""
    shipped = Path(__file__).resolve().parents[2] / "assets" / "QC_Method.sky"
    text = shipped.read_text(encoding="utf-8")
    assert text.count("<peptide ") == 48
    assert text.count("<transition ") > 0
    # Nothing that ties the public template to a site or needs a side file.
    assert ".blib" not in text
    assert "panorama_publish_uri" not in text


@pytest.mark.asyncio
async def test_agent_start_puts_the_template_in_place(
    bundled: Path, tmp_data_dir: Path
) -> None:
    from mdqc.config.schema import Config
    from mdqc.service.lifecycle import _build_state

    await _build_state(Config())

    assert (paths.methods_dir() / "QC_Method.sky").exists()


@pytest.mark.parametrize(
    ("vendor", "pattern"),
    [
        (Vendor.THERMO, "*.raw"),
        (Vendor.BRUKER, "*.d"),
        (Vendor.SCIEX, "*.wiff"),
        (Vendor.WATERS, "*.raw"),
        (Vendor.AGILENT, "*.d"),
    ],
)
def test_default_file_pattern_is_the_vendor_extension(vendor: Vendor, pattern: str) -> None:
    assert vendor.default_file_pattern == pattern
