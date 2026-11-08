"""Offline PBIR validator: schema, structure, names, page order, field references, roles and layout.

    python tools/validate_pbir.py "<folder>.Report" [--model "<folder>.SemanticModel"] [--strict] [--output FILE]

Field references are checked against the semantic model's TMDL: --model, or by default the
definition.pbir byPath target. Prints one JSON report.
Exit code: 0 clean, 1 errors (or warnings with --strict), 2 usage.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import jsonschema
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tmdl_lite import field_list  # noqa: E402
SCHEMA_BASE = "https://developer.microsoft.com/json-schemas/"
REPORT_SCHEMA_PREFIX = SCHEMA_BASE + "fabric/item/report/"
NAME_RE = re.compile(r"^[\w-]+$")
NAME_RULE = "Names must be word characters (letters, digits, underscores) or hyphens only."
SCHEMA_URL_RE = re.compile(r"^https://developer\.microsoft\.com/json-schemas/(.+)/(\d+\.\d+\.\d+)/schema\.json$")
CANVAS = (1280, 720)
GUTTER = 8
MAX_VISUALS_PER_PAGE = 6
MAX_ERRORS_PER_FILE = 25

EXPECTED_SCHEMA = {
    "definition.pbir": "fabric/item/report/definitionProperties",
    ".platform": "fabric/gitIntegration/platformProperties",
    "definition/report.json": "fabric/item/report/definition/report",
    "definition/version.json": "fabric/item/report/definition/versionMetadata",
    "definition/reportExtensions.json": "fabric/item/report/definition/reportExtension",
    "definition/pages/pages.json": "fabric/item/report/definition/pagesMetadata",
    "definition/bookmarks/bookmarks.json": "fabric/item/report/definition/bookmarksMetadata",
    ".pbi/localSettings.json": "fabric/item/report/localSettings",
}

# Data roles per core visualType: (required, multiple, accepted kinds). Source: pbir CLI 0.9.32 catalog 0.1.1.
ROLES = {
    "card": {"Values": (True, True, "CM")},
    "cardVisual": {"Data": (True, True, "CM"), "Rows": (False, False, "C"), "Tooltips": (False, True, "CM")},
    "multiRowCard": {"Values": (True, True, "CM")},
    "kpi": {"Indicator": (True, False, "M"), "TrendLine": (False, False, "C"), "Goal": (False, True, "M")},
    "gauge": {"Y": (True, False, "M"), "TargetValue": (False, False, "M"), "MinValue": (False, False, "M"),
              "MaxValue": (False, False, "M"), "Tooltips": (False, True, "CM")},
    "lineChart": {"Category": (True, False, "C"), "Y": (True, True, "M"), "Y2": (False, True, "M"),
                  "Rows": (False, False, "C"), "Tooltips": (False, True, "CM")},
    "areaChart": {"Category": (True, False, "C"), "Y": (True, True, "M"), "Y2": (False, True, "M"),
                  "Rows": (False, False, "C"), "Tooltips": (False, True, "CM")},
    "barChart": {"Category": (True, False, "C"), "Y": (True, True, "M"), "Series": (False, False, "C"),
                 "Rows": (False, False, "C"), "Tooltips": (False, True, "CM")},
    "pieChart": {"Category": (True, False, "C"), "Y": (True, False, "M"), "Series": (False, False, "C"),
                 "Tooltips": (False, True, "CM")},
    "scatterChart": {"Category": (False, True, "C"), "X": (True, True, "M"), "Y": (True, True, "M"),
                     "Size": (False, True, "M"), "Series": (False, True, "C"), "Play": (False, True, "C"),
                     "Tooltips": (False, True, "CM")},
    "slicer": {"Values": (True, True, "C")},
    "listSlicer": {"Values": (True, True, "C"), "Tooltips": (False, True, "CM")},
    "advancedSlicerVisual": {"Values": (True, True, "C"), "Label": (False, False, "CM"), "Tooltips": (False, True, "CM")},
    "pivotTable": {"Rows": (False, True, "C"), "Columns": (False, True, "C"), "Values": (True, True, "M")},
    "tableEx": {"Values": (True, True, "CM")},
    "map": {"Category": (True, False, "C"), "X": (False, False, "M"), "Y": (False, False, "M"),
            "Size": (False, False, "M"), "Series": (False, False, "C"), "Tooltips": (False, True, "CM")},
    "azureMap": {"Category": (True, False, "C"), "X": (False, False, "M"), "Y": (False, False, "M"),
                 "Size": (False, False, "M"), "Series": (False, False, "C"), "PathID": (False, False, "C"),
                 "PointOrder": (False, False, "C"), "Tooltips": (False, True, "CM")},
    "filledMap": {"Category": (True, True, "C"), "X": (False, True, "M"), "Y": (False, True, "M"),
                  "Series": (False, True, "C"), "Tooltips": (False, True, "CM")},
    "textbox": {}, "image": {}, "actionButton": {}, "shape": {}, "basicShape": {},
}
for _t in ("stackedAreaChart", "clusteredBarChart", "columnChart", "clusteredColumnChart", "ribbonChart",
           "hundredPercentStackedBarChart", "hundredPercentStackedColumnChart"):
    ROLES[_t] = ROLES["barChart"]
ROLES["donutChart"] = ROLES["pieChart"]
for _t in ("lineClusteredColumnComboChart", "lineStackedColumnComboChart"):
    ROLES[_t] = {"Category": (True, False, "C"), "Y": (False, True, "M"), "Y2": (False, True, "M"),
                 "Series": (False, False, "C"), "Rows": (False, False, "C"), "Tooltips": (False, True, "CM")}
OTHER_CORE_TYPES = {"treemap", "funnel", "waterfallChart", "shapeMap", "decompositionTreeVisual", "keyDriversVisual",
                    "qnaVisual", "scriptVisual", "pythonVisual", "aiNarratives", "bookmarkNavigator", "pageNavigator",
                    "textSlicer", "scorecard", "rdlVisual"}
TYPE_HINTS = {"matrix": "pivotTable", "table": "tableEx", "bar": "clusteredBarChart", "line": "lineChart",
              "bubbleMap": "map", "newCard": "cardVisual"}


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, code, file, msg, ptr=""):
        self.errors.append({"code": code, "file": file, "path": ptr, "message": msg})

    def warn(self, code, file, msg, ptr=""):
        self.warnings.append({"code": code, "file": file, "path": ptr, "message": msg})


class SchemaStore:
    def __init__(self, root):
        self.root = root
        self.ids = {}
        registry = Registry()
        for p in sorted(root.glob("fabric/**/*.json")):
            contents = json.loads(p.read_text(encoding="utf-8-sig"))
            url = SCHEMA_BASE + p.relative_to(root).as_posix()
            res = Resource.from_contents(contents, default_specification=DRAFT7)
            registry = registry.with_resource(url, res)
            if res.id() and res.id() != url:
                registry = registry.with_resource(res.id(), res)
            self.ids[url] = contents
        self.registry = registry.crawl()
        self.validators = {}

    def validator(self, url):
        if url not in self.ids:
            return None
        if url not in self.validators:
            schema = self.ids[url]
            cls = jsonschema.validators.validator_for(schema, default=jsonschema.Draft7Validator)
            self.validators[url] = cls(schema, registry=self.registry)
        return self.validators[url]


def dicts(x):
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


def esc(key):
    return str(key).replace("~", "~0").replace("/", "~1")


def load_json(path, rel, rep):
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        rep.warn("JSON_BOM", rel, "File starts with a UTF-8 BOM; Power BI Desktop writes UTF-8 without BOM.")
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as ex:
        rep.error("JSON_INVALID", rel, f"Not valid JSON: {ex}")
        return None


def schema_type(url):
    m = SCHEMA_URL_RE.match(url or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def expected_type(rel):
    if rel in EXPECTED_SCHEMA:
        return EXPECTED_SCHEMA[rel]
    if rel.startswith("definition/pages/"):
        if rel.endswith("/page.json"):
            return "fabric/item/report/definition/page"
        if rel.endswith("/visual.json"):
            return "fabric/item/report/definition/visualContainer"
        if rel.endswith("/mobile.json"):
            return "fabric/item/report/definition/visualContainerMobileState"
    if rel.startswith("definition/bookmarks/") and rel.endswith(".bookmark.json"):
        return "fabric/item/report/definition/bookmark"
    return None


def validate_schema(doc, rel, store, rep, versions):
    url = doc.get("$schema") if isinstance(doc, dict) else None
    exp = expected_type(rel)
    if not isinstance(url, str) or not url:
        if exp or rel.startswith("definition/"):
            rep.error("SCHEMA_MISSING", rel, "No \"$schema\" property.")
        return
    stype, sver = schema_type(url)
    if stype:
        versions.setdefault(stype.rsplit("/", 1)[-1], set()).add(sver)
    if exp and stype != exp:
        rep.error("SCHEMA_WRONG_TYPE", rel, f"$schema is {url}; this file must use {exp}/<version>/schema.json.")
    v = store.validator(url)
    if v is None:
        if url.startswith(REPORT_SCHEMA_PREFIX) or exp:
            rep.error("SCHEMA_UNKNOWN", rel, f"$schema {url} is not a published schema (none vendored under schemas/).")
        else:
            rep.warn("SCHEMA_NOT_VENDORED", rel, f"$schema {url} is not vendored; file not schema-validated.")
        return
    n = 0
    for err in sorted(v.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        n += 1
        if n > MAX_ERRORS_PER_FILE:
            rep.error("SCHEMA_INVALID", rel, "Further schema errors suppressed.")
            break
        if err.context and all(e.validator == "const" for e in err.context):
            msg = f"{err.instance!r} is not one of {[e.validator_value for e in err.context]}"
        elif err.context:
            msg = f"{err.message[:200]} | closest: {jsonschema.exceptions.best_match(err.context).message}"
        else:
            msg = err.message
        ptr = "/" + "/".join(esc(p) for p in err.absolute_path)
        rep.error("SCHEMA_INVALID", rel, msg[:600], ptr)


def load_fields(model_dir):
    data = field_list(model_dir)
    model = {}
    for t in data["tables"]:
        model[t["name"]] = {
            "column": {c["name"]: c for c in t.get("columns", [])},
            "measure": {m["name"]: m for m in t.get("measures", [])},
            "hierarchy": {h["name"]: h for h in t.get("hierarchies", [])},
        }
    return data, model


def resolve_entity(expr, aliases):
    if not isinstance(expr, dict):
        return None
    if "SourceRef" in expr and isinstance(expr["SourceRef"], dict):
        sr = expr["SourceRef"]
        if "Entity" in sr:
            return sr.get("Schema"), sr["Entity"]
        if "Source" in sr:
            return aliases.get(sr["Source"], ("?alias", sr["Source"]))
    if "PropertyVariationSource" in expr:
        pvs = expr["PropertyVariationSource"]
        return resolve_entity(pvs.get("Expression"), aliases)
    return None


def collect_refs(doc, rel):
    refs = []

    def walk(node, ptr, aliases):
        if isinstance(node, dict):
            if isinstance(node.get("From"), list):
                aliases = dict(aliases)
                for s in node["From"]:
                    if isinstance(s, dict) and "Name" in s and "Entity" in s:
                        aliases[s["Name"]] = (s.get("Schema"), s["Entity"])
            for key, val in node.items():
                p = f"{ptr}/{esc(key)}"
                if key in ("Column", "Measure") and isinstance(val, dict) and "Property" in val:
                    expr = val.get("Expression")
                    if isinstance(expr, dict) and "PropertyVariationSource" in expr:
                        pvs = expr["PropertyVariationSource"]
                        ent = resolve_entity(pvs.get("Expression"), aliases)
                        refs.append(("column", ent, pvs.get("Property"), rel, p))
                    else:
                        refs.append((key.lower(), resolve_entity(expr, aliases), val["Property"], rel, p))
                elif key == "Hierarchy" and isinstance(val, dict) and isinstance(val.get("Hierarchy"), str):
                    expr = val.get("Expression")
                    if isinstance(expr, dict) and "PropertyVariationSource" in expr:
                        pvs = expr["PropertyVariationSource"]
                        refs.append(("column", resolve_entity(pvs.get("Expression"), aliases), pvs.get("Property"), rel, p))
                    else:
                        refs.append(("hierarchy", resolve_entity(expr, aliases), val["Hierarchy"], rel, p))
                walk(val, p, aliases)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{ptr}/{i}", aliases)

    walk(doc, "", {})
    return refs


def check_refs(refs, model, ext_measures, rep):
    for kind, ent, prop, rel, ptr in refs:
        if ent is None:
            rep.warn("FIELD_SOURCE_UNRESOLVED", rel, f"{kind} '{prop}' has no table source the validator understands.", ptr)
            continue
        schema, table = ent
        label = f"'{table}'[{prop}]"
        if schema == "?alias":
            rep.error("FIELD_ALIAS_UNKNOWN", rel, f"SourceRef alias '{table}' is not declared in an enclosing From.", ptr)
            continue
        if schema == "extension":
            if kind != "measure" or (table, prop) not in ext_measures:
                rep.error("FIELD_EXTENSION_MISSING", rel, f"Extension {kind} {label} not in reportExtensions.json.", ptr)
            continue
        if table not in model:
            near = [t for t in model if t.lower() == str(table).lower()]
            hint = f" (case differs: '{near[0]}')" if near else ""
            rep.error("FIELD_TABLE_MISSING", rel, f"Table '{table}' is not in the model{hint}.", ptr)
            continue
        t = model[table]
        if prop in t[kind]:
            if kind == "column" and t["column"][prop].get("isHidden"):
                rep.warn("FIELD_HIDDEN", rel, f"Column {label} is hidden in the model.", ptr)
            continue
        other = [k for k in ("column", "measure", "hierarchy") if k != kind and prop in t[k]]
        if other:
            rep.error("FIELD_KIND_MISMATCH", rel, f"{label} is a {other[0]} but is referenced as a {kind}.", ptr)
            continue
        near = [n for k in ("column", "measure", "hierarchy") for n in t[k] if n.lower() == str(prop).lower()]
        hint = f" (case differs: '{near[0]}')" if near else ""
        rep.error("FIELD_MISSING", rel, f"{kind.capitalize()} {label} is not in the model{hint}.", ptr)


def projection_kind(field):
    if not isinstance(field, dict):
        return None
    if "Measure" in field or "Aggregation" in field:
        return "M"
    if "Column" in field or "HierarchyLevel" in field:
        return "C"
    return None


def check_visual(doc, rel, rep, page_size, boxes, registered_custom):
    vis = doc.get("visual")
    if not isinstance(vis, dict):
        return
    vtype = vis.get("visualType")
    roles = ROLES.get(vtype)
    if roles is None:
        if vtype in OTHER_CORE_TYPES or vtype in registered_custom:
            pass
        elif vtype in TYPE_HINTS:
            rep.warn("VISUAL_TYPE_UNKNOWN", rel, f"visualType '{vtype}' is not a Power BI visual id; use '{TYPE_HINTS[vtype]}'.", "/visual/visualType")
        else:
            rep.warn("VISUAL_TYPE_UNKNOWN", rel, f"visualType '{vtype}' is not a core visual and is not registered in report.json.", "/visual/visualType")
    qs = (vis.get("query") or {}).get("queryState") or {}
    if roles is not None:
        for role, state in qs.items():
            p = f"/visual/query/queryState/{esc(role)}"
            if role not in roles:
                rep.warn("ROLE_UNKNOWN", rel, f"Role '{role}' is not a data role of {vtype} (valid: {', '.join(roles) or 'none'}).", p)
                continue
            req, multiple, accepts = roles[role]
            projs = state.get("projections", []) if isinstance(state, dict) else []
            if not multiple and len(projs) > 1:
                rep.warn("ROLE_CARDINALITY", rel, f"Role '{role}' of {vtype} takes one field; found {len(projs)}.", p)
            for i, pr in enumerate(projs):
                k = projection_kind(pr.get("field"))
                if k and k not in accepts:
                    want = "a measure or aggregation" if accepts == "M" else "a column"
                    rep.warn("ROLE_KIND", rel, f"Role '{role}' of {vtype} expects {want}.", f"{p}/projections/{i}")
        for role, (req, _, _) in roles.items():
            if req and not (qs.get(role) or {}).get("projections"):
                rep.warn("ROLE_REQUIRED_MISSING", rel, f"{vtype} needs a field in role '{role}'.", "/visual/query/queryState")
    seen = set()
    for role, state in qs.items():
        for pr in (state.get("projections", []) if isinstance(state, dict) else []):
            qr = pr.get("queryRef")
            if qr is not None and qr in seen:
                rep.warn("QUERYREF_DUPLICATE", rel, f"queryRef '{qr}' is used twice in one visual.")
            seen.add(qr)
            f = pr.get("field") or {}
            inner = f.get("Column") or f.get("Measure")
            if isinstance(inner, dict):
                sr = (inner.get("Expression") or {}).get("SourceRef") or {}
                if qr is not None and "Entity" in sr and qr != f"{sr['Entity']}.{inner.get('Property')}":
                    rep.warn("QUERYREF_MISMATCH", rel, f"queryRef '{qr}' does not match {sr['Entity']}.{inner.get('Property')}.")
    if doc.get("isHidden"):
        rep.warn("VISUAL_HIDDEN", rel, "Visual is hidden.")
    pos = doc.get("position") or {}
    try:
        x, y, w, h = (float(pos[k]) for k in ("x", "y", "width", "height"))
    except (KeyError, TypeError, ValueError):
        return
    if doc.get("parentGroupName"):
        return
    W, H = page_size
    if x < 0 or y < 0 or x + w > W + 0.5 or y + h > H + 0.5:
        rep.warn("LAYOUT_OFF_CANVAS", rel, f"Visual box ({x:g},{y:g},{w:g}x{h:g}) leaves the {W:g}x{H:g} canvas.")
    elif min(x, y, W - x - w, H - y - h) < GUTTER - 0.5:
        rep.warn("LAYOUT_GUTTER", rel, f"Visual is closer than {GUTTER}px to the canvas edge.")
    boxes.append((rel, x, y, w, h))


def check_layout(boxes, rep, page_rel):
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            ax2, ay2, bx2, by2 = a[1] + a[3], a[2] + a[4], b[1] + b[3], b[2] + b[4]
            gx = max(b[1] - ax2, a[1] - bx2)
            gy = max(b[2] - ay2, a[2] - by2)
            if gx < 0 and gy < 0:
                rep.warn("LAYOUT_OVERLAP", page_rel, f"{a[0].split('/')[-2]} overlaps {b[0].split('/')[-2]}.")
            elif (gx < 0 <= gy < GUTTER - 0.5) or (gy < 0 <= gx < GUTTER - 0.5):
                rep.warn("LAYOUT_GUTTER", page_rel, f"{a[0].split('/')[-2]} and {b[0].split('/')[-2]} are less than {GUTTER}px apart.")


def validate(report_dir, model_dir, schemas_dir):
    rep = Report()
    versions = {}
    store = SchemaStore(schemas_dir)
    fields_meta, model = {}, {}
    docs = {}
    counts = {"json_files": 0, "pages": 0, "visuals": 0, "field_refs": 0}

    if not report_dir.name.endswith(".Report"):
        rep.warn("STRUCTURE_FOLDER_NAME", ".", "Report folder name should end in '.Report'.")
    if (report_dir / "report.json").exists():
        rep.error("STRUCTURE_LEGACY", "report.json", "Root report.json is the PBIR-Legacy format; PBIR keeps the definition in definition/.")
    for req in ("definition.pbir", "definition/report.json", "definition/version.json"):
        if not (report_dir / req).is_file():
            rep.error("STRUCTURE_MISSING", req, "Required file is missing.")
    if not (report_dir / "definition/pages/pages.json").is_file():
        rep.warn("STRUCTURE_PAGES_JSON_MISSING", "definition/pages/pages.json",
                 "No pages.json: Desktop orders pages by display name and opens the first.")

    for path in sorted(report_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(report_dir).as_posix()
        if rel.startswith(".pbi/") and rel != ".pbi/localSettings.json":
            continue
        is_json = path.suffix.lower() == ".json" or rel in ("definition.pbir", ".platform")
        if not is_json:
            if rel.startswith("definition/"):
                rep.warn("STRUCTURE_UNEXPECTED", rel, "Non-JSON file inside definition/.")
            continue
        counts["json_files"] += 1
        doc = load_json(path, rel, rep)
        if doc is None:
            continue
        docs[rel] = doc
        validate_schema(doc, rel, store, rep, versions)

    pbir = docs.get("definition.pbir")
    if isinstance(pbir, dict):
        ds = pbir.get("datasetReference") if isinstance(pbir.get("datasetReference"), dict) else {}
        by_path = (ds.get("byPath") or {}).get("path") if isinstance(ds.get("byPath"), dict) else None
        if not by_path:
            rep.error("BYPATH_REQUIRED", "definition.pbir", "Bind the report to its model with datasetReference.byPath; byConnection carries IDs.")
        elif model_dir is not None:
            if Path(by_path).name != model_dir.name:
                rep.error("BYPATH_MODEL_MISMATCH", "definition.pbir", f"byPath '{by_path}' does not name the model {model_dir.name}.")
        else:
            target = (report_dir / by_path).resolve()
            if not target.is_dir():
                rep.error("BYPATH_TARGET_MISSING", "definition.pbir", f"byPath '{by_path}' does not resolve to a folder next to the report.")
            elif not (target / "definition.pbism").is_file():
                rep.error("BYPATH_TARGET_INVALID", "definition.pbir", f"byPath '{by_path}' has no definition.pbism.")
            else:
                model_dir = target
        ver = str(pbir.get("version", ""))
        m = re.match(r"^(\d+)\.", ver)
        if ver and (not m or int(m.group(1)) < 4):
            rep.error("PBIR_VERSION", "definition.pbir", f"version '{ver}': the definition/ folder (PBIR) needs 4.0 or higher; 1.0 means PBIR-Legacy.")

    registered_custom = set()
    report_json = docs.get("definition/report.json")
    if isinstance(report_json, dict):
        items = {}
        for pkg in dicts(report_json.get("resourcePackages")):
            for it in dicts(pkg.get("items")):
                items[it.get("name")] = it
                p = report_dir / "StaticResources" / str(pkg.get("type", pkg.get("name"))) / str(it.get("path", ""))
                if not p.is_file():
                    rep.error("RESOURCE_MISSING", "definition/report.json",
                              f"Resource '{it.get('path')}' in package '{pkg.get('name')}' is not under StaticResources/.")
        for slot in ("baseTheme", "customTheme"):
            tc = report_json.get("themeCollection")
            th = tc.get(slot) if isinstance(tc, dict) else None
            if isinstance(th, dict) and th.get("name") not in items:
                rep.warn("THEME_UNREGISTERED", "definition/report.json", f"themeCollection.{slot} '{th.get('name')}' has no resourcePackages item.")
        for key in ("publicCustomVisuals", "organizationCustomVisuals"):
            vals = report_json.get(key)
            registered_custom |= {v for v in vals if isinstance(v, str)} if isinstance(vals, list) else set()

    ext_measures = set()
    ext = docs.get("definition/reportExtensions.json")
    if isinstance(ext, dict):
        for ent in dicts(ext.get("entities")):
            for m in dicts(ent.get("measures")):
                ext_measures.add((ent.get("name"), m.get("name")))

    pages_dir = report_dir / "definition" / "pages"
    page_folders = sorted(p.name for p in pages_dir.iterdir() if p.is_dir()) if pages_dir.is_dir() else []
    counts["pages"] = len(page_folders)
    if not page_folders:
        rep.error("STRUCTURE_NO_PAGES", "definition/pages", "The report has no page folders.")
    page_names = {}
    for pf in page_folders:
        page = docs.get(f"definition/pages/{pf}/page.json")
        name = page.get("name") if isinstance(page, dict) else None
        page_names[pf] = name if isinstance(name, str) else pf
    names = list(page_names.values())
    for dup in sorted({n for n in names if names.count(n) > 1}):
        rep.error("NAME_DUPLICATE", "definition/pages", f"Two pages share the name '{dup}'.")

    pages_json = docs.get("definition/pages/pages.json")
    if isinstance(pages_json, dict):
        order = pages_json.get("pageOrder")
        if not isinstance(order, list):
            rep.warn("PAGEORDER_MISSING", "definition/pages/pages.json", "No pageOrder: Desktop orders pages by display name.")
        else:
            order = [p for p in order if isinstance(p, str)]
            dupes = sorted({p for p in order if order.count(p) > 1})
            if dupes:
                rep.error("PAGEORDER_DUPLICATE", "definition/pages/pages.json", f"Duplicate pages in pageOrder: {dupes}.")
            missing = sorted(set(names) - set(order))
            extra = sorted(set(order) - set(names))
            if missing:
                rep.error("PAGEORDER_MISMATCH", "definition/pages/pages.json", f"Pages not in pageOrder: {missing}.")
            if extra:
                rep.error("PAGEORDER_MISMATCH", "definition/pages/pages.json", f"pageOrder entries with no page: {extra}.")
        for key in ("activePageName", "landingPageName"):
            if isinstance(pages_json.get(key), str) and pages_json[key] not in names:
                rep.warn("PAGEORDER_ACTIVE", "definition/pages/pages.json", f"{key} '{pages_json[key]}' is not a page (Desktop resets it).")

    for pf in page_folders:
        prel = f"definition/pages/{pf}/page.json"
        if not NAME_RE.match(pf):
            rep.error("NAME_INVALID", f"definition/pages/{pf}", NAME_RULE + " Desktop ignores this page folder.")
        page = docs.get(prel)
        if not (pages_dir / pf / "page.json").is_file():
            rep.error("STRUCTURE_MISSING", prel, "Page folder has no page.json.")
        page_size = CANVAS
        if isinstance(page, dict):
            if isinstance(page.get("name"), str) and not NAME_RE.match(page["name"]):
                rep.error("NAME_INVALID", prel, f"Page name '{page['name']}': " + NAME_RULE)
            elif page.get("name") != pf:
                rep.warn("NAME_FOLDER_MISMATCH", prel, f"page.json name '{page.get('name')}' differs from its folder '{pf}'.")
            try:
                page_size = (float(page.get("width")), float(page.get("height")))
            except (TypeError, ValueError):
                page_size = CANVAS
            if page_size != CANVAS:
                rep.warn("PAGE_SIZE", prel, f"Canvas is {page_size[0]:g}x{page_size[1]:g}; the report standard is {CANVAS[0]}x{CANVAS[1]}.")
        vdir = pages_dir / pf / "visuals"
        vfolders = sorted(p.name for p in vdir.iterdir() if p.is_dir()) if vdir.is_dir() else []
        boxes, groups, vnames, n_visuals = [], set(), [], 0
        vdocs = {}
        for vf in vfolders:
            vrel = f"definition/pages/{pf}/visuals/{vf}/visual.json"
            if not NAME_RE.match(vf):
                rep.error("NAME_INVALID", f"definition/pages/{pf}/visuals/{vf}", NAME_RULE + " Desktop ignores this visual folder.")
            if not (vdir / vf / "visual.json").is_file():
                rep.error("STRUCTURE_MISSING", vrel, "Visual folder has no visual.json.")
                continue
            v = docs.get(vrel)
            if not isinstance(v, dict):
                continue
            vdocs[vf] = (vrel, v)
            vname = v.get("name")
            vnames.append(vname)
            if isinstance(vname, str) and not NAME_RE.match(vname):
                rep.error("NAME_INVALID", vrel, f"Visual name '{vname}': " + NAME_RULE)
            elif vname != vf:
                rep.warn("NAME_FOLDER_MISMATCH", vrel, f"visual.json name '{vname}' differs from its folder '{vf}'.")
            if "visualGroup" in v:
                groups.add(vname)
            elif "visual" in v:
                n_visuals += 1
        for dup in sorted({n for n in vnames if vnames.count(n) > 1 and n is not None}):
            rep.error("NAME_DUPLICATE", prel, f"Two visuals on this page share the name '{dup}'.")
        for vf, (vrel, v) in vdocs.items():
            parent = v.get("parentGroupName")
            if parent and parent not in groups:
                rep.error("GROUP_MISSING", vrel, f"parentGroupName '{parent}' is not a visual group on this page.")
            try:
                check_visual(v, vrel, rep, page_size, boxes, registered_custom)
            except (AttributeError, TypeError, KeyError, ValueError) as ex:
                rep.error("VISUAL_UNREADABLE", vrel, f"Visual shape could not be checked ({type(ex).__name__}: {ex}).")
        check_layout(boxes, rep, prel)
        counts["visuals"] += n_visuals
        if n_visuals > MAX_VISUALS_PER_PAGE:
            rep.warn("PAGE_TOO_MANY_VISUALS", prel, f"{n_visuals} visuals; the standard is at most {MAX_VISUALS_PER_PAGE}.")
        if isinstance(page, dict):
            for i, vi in enumerate(dicts(page.get("visualInteractions"))):
                for end in ("source", "target"):
                    if vi.get(end) not in vnames:
                        rep.error("INTERACTION_TARGET_MISSING", prel, f"visualInteractions {end} '{vi.get(end)}' is not a visual on this page.", f"/visualInteractions/{i}/{end}")

    bdir = report_dir / "definition" / "bookmarks"
    if bdir.is_dir():
        bnames = set()
        for p in sorted(bdir.glob("*.bookmark.json")):
            stem = p.name[: -len(".bookmark.json")]
            brel = f"definition/bookmarks/{p.name}"
            bdoc = docs.get(brel)
            bname = bdoc.get("name") if isinstance(bdoc, dict) else stem
            bnames.add(bname)
            if not NAME_RE.match(stem):
                rep.error("NAME_INVALID", brel, NAME_RULE + " Desktop ignores this bookmark file.")
            elif bname != stem:
                rep.warn("NAME_FOLDER_MISMATCH", brel, f"Bookmark name '{bname}' differs from its file name.")
        bmeta = docs.get("definition/bookmarks/bookmarks.json")
        if isinstance(bmeta, dict):
            for it in dicts(bmeta.get("items")):
                kids = it.get("children") if "children" in it else [it.get("name")]
                for n in kids if isinstance(kids, list) else []:
                    if n not in bnames:
                        rep.error("BOOKMARK_MISSING", "definition/bookmarks/bookmarks.json", f"Bookmark '{n}' has no .bookmark.json file.")

    refs = []
    for rel, doc in docs.items():
        if rel.startswith("definition/"):
            refs.extend(collect_refs(doc, rel))
    counts["field_refs"] = len(refs)
    if model_dir is not None:
        try:
            fields_meta, model = load_fields(model_dir)
        except (OSError, ValueError) as ex:
            rep.error("MODEL_UNREADABLE", "definition.pbir", f"Model {model_dir.name} could not be read: {ex}")
        else:
            check_refs(refs, model, ext_measures, rep)

    for t, vs in versions.items():
        if len(vs) > 1:
            rep.warn("SCHEMA_VERSION_MIXED", ".", f"{t} uses several versions: {sorted(vs)}.")
    return rep, counts, {t: sorted(v) for t, v in sorted(versions.items())}, fields_meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="Offline PBIR validator.")
    ap.add_argument("report", help="Path to the <name>.Report folder")
    ap.add_argument("--model", help="The <name>.SemanticModel folder to check fields against (default: the byPath target)")
    ap.add_argument("--schemas", default=str(HERE / "schemas"), help="Vendored schema root (default: tools/schemas/)")
    ap.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    ap.add_argument("--output", help="Also write the JSON report to this file")
    args = ap.parse_args(argv)

    report_dir = Path(args.report)
    if not report_dir.is_dir():
        print(json.dumps({"ok": False, "usage_error": f"Not a folder: {report_dir.name}"}))
        return 2
    model_dir = Path(args.model).resolve() if args.model else None
    schemas_dir = Path(args.schemas)
    if (model_dir is not None and not (model_dir / "definition").is_dir()) or not (schemas_dir / "fabric").is_dir():
        print(json.dumps({"ok": False, "usage_error": "model folder (with definition/) or schemas/ not found"}))
        return 2

    try:
        rep, counts, versions, fields_meta = validate(report_dir.resolve(), model_dir, schemas_dir)
    except Exception as ex:  # a malformed report must never exit 0
        print(json.dumps({"report": report_dir.resolve().name, "ok": False,
                          "internal_error": f"{type(ex).__name__}: {ex}"}))
        return 1
    failing = rep.errors + (rep.warnings if args.strict else [])
    out = {
        "report": report_dir.resolve().name,
        "ok": not failing,
        "strict": args.strict,
        "model": fields_meta.get("model"),
        "counts": {**counts, "errors": len(rep.errors), "warnings": len(rep.warnings)},
        "schema_versions": versions,
        "errors": rep.errors,
        "warnings": rep.warnings,
    }
    text = json.dumps(out, indent=1)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    return 0 if not failing else 1


if __name__ == "__main__":
    sys.exit(main())
