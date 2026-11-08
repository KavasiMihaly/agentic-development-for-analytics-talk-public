"""Fail if a TMDL model carries BPA ignore annotations.

    python tools/check_bpa_ignores.py "<model>.SemanticModel" [...]

te and TabularEditor.exe both honour BestPracticeAnalyzer_IgnoreRules, even with
--no-model-rules / -AX, so the gate runs this before BPA.
Exit 0 = clean, 1 = ignore annotation found, 2 = bad argument.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERN = re.compile(r"\bBestPracticeAnalyzer_IgnoreRules\b", re.IGNORECASE)


def find_ignores(model_dir: Path) -> list[str]:
    hits = []
    for path in sorted(Path(model_dir).rglob("*")):
        if path.suffix.lower() not in {".tmdl", ".bim", ".json"} or not path.is_file():
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
            if PATTERN.search(line):
                hits.append(f"{path.relative_to(model_dir).as_posix()}:{n}")
    return hits


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    found = False
    for arg in argv:
        model_dir = Path(arg)
        if not model_dir.is_dir():
            print(f"not a folder: {model_dir.name}")
            return 2
        for hit in find_ignores(model_dir):
            found = True
            print(f"::error::BPA ignore annotation in {model_dir.name}/{hit} - the gate does not accept suppressed rules")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
