"""Minimal TMDL reader for the gate tools: tables, columns, measures, hierarchies, partitions,
relationships and shared expressions. Not a general TMDL parser."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

OBJECT_RE = re.compile(
    r"^(column|measure|partition|hierarchy)\s+('(?:[^']|'')*'|[^\s=]+)\s*(?:=\s*(.*))?$"
)
PROP_RE = re.compile(r"^([A-Za-z]+)\s*:\s*(.*)$")


def unquote(name: str) -> str:
    name = name.strip()
    if len(name) >= 2 and name.startswith("'") and name.endswith("'"):
        return name[1:-1].replace("''", "'")
    return name


def _depth(line: str) -> int:
    return len(line) - len(line.lstrip("\t"))


@dataclass
class Obj:
    kind: str
    name: str
    header_value: str = ""
    description: str = ""
    props: dict = field(default_factory=dict)
    flags: set = field(default_factory=set)
    expression_lines: list = field(default_factory=list)
    source: dict = field(default_factory=dict)

    @property
    def expression(self) -> str:
        if self.header_value and self.header_value != "```":
            return self.header_value
        return "\n".join(self.expression_lines).strip()

    @property
    def hidden(self) -> bool:
        return "isHidden" in self.flags or self.props.get("isHidden", "").lower() == "true"


@dataclass
class Table:
    name: str
    description: str = ""
    props: dict = field(default_factory=dict)
    flags: set = field(default_factory=set)
    columns: dict = field(default_factory=dict)
    measures: dict = field(default_factory=dict)
    hierarchies: dict = field(default_factory=dict)
    partitions: dict = field(default_factory=dict)

    @property
    def hidden(self) -> bool:
        return "isHidden" in self.flags or self.props.get("isHidden", "").lower() == "true"


def parse_table(path: Path) -> Table:
    table = None
    pending_desc: list[str] = []
    current: Obj | None = None
    in_source = False
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if not raw.strip():
            continue
        d = _depth(raw)
        text = raw.strip()
        if d == 0:
            if text.startswith("///"):
                pending_desc.append(text[3:].strip())
                continue
            if text.startswith("table "):
                table = Table(name=unquote(text[len("table "):]), description=" ".join(pending_desc))
                pending_desc = []
            continue
        if table is None:
            continue
        if d == 1:
            in_source = False
            if text.startswith("///"):
                pending_desc.append(text[3:].strip())
                continue
            m = OBJECT_RE.match(text)
            if m:
                kind, name, value = m.group(1), unquote(m.group(2)), (m.group(3) or "").strip()
                current = Obj(kind=kind, name=name, header_value=value, description=" ".join(pending_desc))
                pending_desc = []
                bucket = {"column": table.columns, "measure": table.measures, "hierarchy": table.hierarchies,
                          "partition": table.partitions}[kind]
                bucket[name] = current
                continue
            current = None
            pending_desc = []
            pm = PROP_RE.match(text)
            if pm:
                table.props[pm.group(1)] = pm.group(2).strip()
            elif not text.startswith(("annotation", "changedProperty")):
                table.flags.add(text)
            continue
        if current is None:
            continue
        if d == 2:
            if current.kind == "partition" and text == "source":
                in_source = True
                continue
            in_source = False
            pm = PROP_RE.match(text)
            if pm and not text.startswith("annotation"):
                current.props[pm.group(1)] = pm.group(2).strip()
            elif not text.startswith(("annotation", "changedProperty")):
                current.flags.add(text)
            continue
        if in_source and current.kind == "partition":
            pm = PROP_RE.match(text)
            if pm:
                current.source[pm.group(1)] = pm.group(2).strip()
            continue
        if current.kind == "measure":
            current.expression_lines.append(raw[3:] if raw.startswith("\t\t\t") else text)
    if table is None:
        raise ValueError(f"no table declaration in {path.name}")
    return table


@dataclass
class Relationship:
    name: str
    props: dict = field(default_factory=dict)

    @staticmethod
    def _split(ref: str) -> tuple[str, str]:
        ref = ref.strip()
        if ref.startswith("'"):
            i = 1
            while True:
                j = ref.index("'", i)
                if j + 1 < len(ref) and ref[j + 1] == "'":
                    i = j + 2
                    continue
                break
            table, col = ref[: j + 1], ref[j + 2:]
        else:
            table, col = ref.split(".", 1)
        return unquote(table), unquote(col)

    @property
    def from_ref(self) -> tuple[str, str]:
        return self._split(self.props["fromColumn"])

    @property
    def to_ref(self) -> tuple[str, str]:
        return self._split(self.props["toColumn"])

    @property
    def is_active(self) -> bool:
        return self.props.get("isActive", "true").lower() != "false"

    @property
    def both_directions(self) -> bool:
        return self.props.get("crossFilteringBehavior", "oneDirection").lower() == "bothdirections"


def parse_relationships(path: Path) -> list[Relationship]:
    rels: list[Relationship] = []
    if not path.is_file():
        return rels
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if not raw.strip():
            continue
        text = raw.strip()
        if _depth(raw) == 0 and text.startswith("relationship "):
            rels.append(Relationship(name=unquote(text[len("relationship "):])))
        elif rels and _depth(raw) == 1:
            pm = PROP_RE.match(text)
            if pm:
                rels[-1].props[pm.group(1)] = pm.group(2).strip()
    return rels


def definition_dir(model: Path) -> Path:
    model = Path(model)
    if (model / "definition").is_dir():
        return model / "definition"
    if (model / "tables").is_dir() or (model / "model.tmdl").is_file():
        return model
    raise FileNotFoundError(f"{model.name}: not a TMDL model folder (no definition/)")


def load_model(model: Path) -> dict:
    definition = definition_dir(model)
    tables = {}
    for p in sorted((definition / "tables").glob("*.tmdl")):
        t = parse_table(p)
        tables[t.name] = t
    return {"tables": tables, "relationships": parse_relationships(definition / "relationships.tmdl")}


def field_list(model: Path) -> dict:
    """Tables, columns, measures and hierarchies in the shape the PBIR validator checks against."""
    loaded = load_model(model)
    folder = Path(model)
    name = folder.name[: -len(".SemanticModel")] if folder.name.endswith(".SemanticModel") else folder.name
    tables = []
    for t in loaded["tables"].values():
        tables.append({
            "name": t.name,
            "isHidden": t.hidden,
            "columns": [{"name": c.name, "dataType": c.props.get("dataType"), "isHidden": c.hidden,
                         "dataCategory": c.props.get("dataCategory")} for c in t.columns.values()],
            "measures": [{"name": m.name, "isHidden": m.hidden} for m in t.measures.values()],
            "hierarchies": [{"name": h.name} for h in t.hierarchies.values()],
        })
    return {"model": name, "tables": tables}
