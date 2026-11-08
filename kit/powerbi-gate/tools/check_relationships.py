"""Relationship check for TMDL models: one active filter path between any two tables.

    python tools/check_relationships.py "<model>.SemanticModel" [...]

te validate does not report ambiguous active paths, so the gate runs this as well.
Prints one JSON object per model. Exit 0 = clean, 1 = ambiguous paths or bad references, 2 = usage.
"""

from __future__ import annotations

import json
import sys
from itertools import permutations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tmdl_lite import load_model  # noqa: E402


def filter_edges(relationships) -> dict[str, list[str]]:
    edges: dict[str, list[str]] = {}
    for r in relationships:
        if not r.is_active:
            continue
        (many, _), (one, _) = r.from_ref, r.to_ref
        edges.setdefault(one, []).append(many)
        if r.both_directions:
            edges.setdefault(many, []).append(one)
    return edges


def count_paths(edges: dict[str, list[str]], src: str, dst: str, seen: frozenset) -> int:
    if src == dst:
        return 1
    return sum(count_paths(edges, n, dst, seen | {n}) for n in edges.get(src, ()) if n not in seen)


def check(model: Path) -> dict:
    loaded = load_model(model)
    tables, rels = loaded["tables"], loaded["relationships"]
    broken = []
    for r in rels:
        for table, column in (r.from_ref, r.to_ref):
            if table not in tables or column not in tables[table].columns:
                broken.append({"relationship": r.name, "missing": f"'{table}'[{column}]"})
    edges = filter_edges(r for r in rels if r.name not in {b["relationship"] for b in broken})
    ambiguous = []
    for a, b in permutations(sorted(tables), 2):
        n = count_paths(edges, a, b, frozenset({a}))
        if n > 1:
            ambiguous.append({"from": a, "to": b, "paths": n})
    return {
        "model": Path(model).name,
        "relationships": len(rels),
        "active": sum(r.is_active for r in rels),
        "both_directions": [r.name for r in rels if r.both_directions],
        "broken": broken,
        "ambiguous": ambiguous,
        "ok": not ambiguous and not broken,
    }


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    ok = True
    for arg in argv:
        try:
            result = check(Path(arg))
        except (FileNotFoundError, ValueError) as exc:
            print(json.dumps({"model": Path(arg).name, "ok": False, "error": str(exc)}))
            return 2
        print(json.dumps(result, indent=1))
        ok = ok and result["ok"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
