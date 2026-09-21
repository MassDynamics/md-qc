"""Merge the 48-peptide K562/HeLa diagnostic peptide list into the library-aware
5-peptide template skeleton.

Output: a single .sky file with
  - All settings from the 5-peptide template (libraries, isolation scheme,
    measured-RT predictor, mass tolerance)
  - All <peptide_list> sections from the 48-peptide working document, but
    with imported-result references stripped (Skyline can re-import freshly).

Usage: python scripts/build_hybrid_template.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

# Both inputs are site-specific Skyline documents, so they come from the
# environment rather than one machine's folder layout:
#   MDQC_SRC_LIBRARY_SKY  the library-aware template (carries the .blib refs)
#   MDQC_SRC_PEPTIDE_SKY  the document holding the peptide list to merge in
#   MDQC_OUT_SKY          where to write the hybrid (default: the methods dir)
SRC_LIB = Path(os.environ.get("MDQC_SRC_LIBRARY_SKY", ""))
SRC_PEP = Path(os.environ.get("MDQC_SRC_PEPTIDE_SKY", ""))
OUT = Path(os.environ.get(
    "MDQC_OUT_SKY", str(Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
                        / "MassDynamics" / "QC" / "methods" / "QC_Method_hybrid.sky")))


def main() -> int:
    if not SRC_LIB.is_file():
        print(f"ERROR: missing {SRC_LIB}", file=sys.stderr)
        return 1
    if not SRC_PEP.is_file():
        print(f"ERROR: missing {SRC_PEP}", file=sys.stderr)
        return 1

    # Parse the library-aware 5-peptide template (skeleton)
    skeleton_tree = ET.parse(SRC_LIB)
    skeleton_root = skeleton_tree.getroot()

    # Parse the 48-peptide populated document
    pep_tree = ET.parse(SRC_PEP)
    pep_root = pep_tree.getroot()

    # Collect all <peptide_list> elements from the populated doc
    peptide_lists = pep_root.findall("peptide_list")
    print(f"Found {len(peptide_lists)} <peptide_list> blocks in {SRC_PEP.name}")

    total_peptides = 0
    for pl in peptide_lists:
        # Strip any chromatogram/result references — keep only peptide+precursor+transition
        # Skyline writes <peptide_result_*> children inside <peptide> when results are
        # imported; remove them so the document is "clean".
        for elem in pl.iter():
            for child in list(elem):
                if "result" in child.tag.lower() or "chromatogram" in child.tag.lower():
                    elem.remove(child)
        total_peptides += len(pl.findall("peptide"))

    print(f"Total peptides after cleanup: {total_peptides}")

    # Remove the existing peptide_lists from the skeleton
    for pl in skeleton_root.findall("peptide_list"):
        skeleton_root.remove(pl)

    # Append the cleaned peptide_lists from the populated doc
    for pl in peptide_lists:
        skeleton_root.append(pl)

    # Also strip any <measured_results> / <data_settings annotation_value> that
    # references imported replicates from the populated file. The skeleton
    # shouldn't have these but defensively check.
    for tag in ("measured_results",):
        for el in skeleton_root.findall(f".//{tag}"):
            parent_map = {c: p for p in skeleton_root.iter() for c in p}
            if el in parent_map:
                parent_map[el].remove(el)

    # Write output
    OUT.parent.mkdir(parents=True, exist_ok=True)
    skeleton_tree.write(OUT, encoding="utf-8", xml_declaration=True)

    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
