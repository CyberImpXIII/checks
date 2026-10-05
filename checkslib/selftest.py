"""`checks fixtures`: every check against its two fixtures, through the same
run_one and checks.json path a real run takes. A refused check (no failing
fixture among the reasons) is a failure here too, so a check that cannot be
shown red is never counted."""
import importlib.util
import shutil
import tempfile
from pathlib import Path

from checkslib import decl, runner


def _module(path):
    spec = importlib.util.spec_from_file_location(f"fixture_{path.stem.replace('-', '_')}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _one(entry, kind, build, entries):
    tmp = Path(tempfile.mkdtemp(prefix=f"checks-fx-{entry.name}-"))
    try:
        fx = build(tmp)
        params, faults = runner.load_params(fx.repo, entries)
        if faults:
            return {"check": entry.name, "fixture": kind, "ok": False, "why": f"fixture's checks.json: {faults}"}
        r = runner.run_one(entry, fx.repo, fx.workspace, params.get(entry.name), fx.names, env=fx.env)
        want = "ok" if kind == "passing" else "fail"
        if r["status"] != want:
            return {"check": entry.name, "fixture": kind, "ok": False,
                    "why": f"came back {r['status']}, wanted {want}: {' | '.join(r['lines'][:4])}"}
        if kind == "failing":
            if not fx.expect:
                return {"check": entry.name, "fixture": kind, "ok": False,
                        "why": "the failing fixture names no expected finding (expect=...)"}
            text = "\n".join(r["lines"])
            missing = [e for e in fx.expect if e not in text]
            if missing:
                return {"check": entry.name, "fixture": kind, "ok": False,
                        "why": f"failed, but not for the stated reason: {missing} not in {r['lines'][:4]}"}
        return {"check": entry.name, "fixture": kind, "ok": True, "why": ""}
    except Exception as e:      # a fixture that cannot build is a red row, never a skipped one
        return {"check": entry.name, "fixture": kind, "ok": False, "why": f"fixture raised {type(e).__name__}: {e}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run(source=runner.DEFAULT_SOURCE):
    entries, refused, faults = decl.load(source)
    rows = []
    for e in entries:
        try:
            mod = _module(e.fixture)
        except Exception as x:      # a fixture file that will not load is a red row, never a crash
            rows.append({"check": e.name, "fixture": "-", "ok": False,
                         "why": f"fixture file did not load: {type(x).__name__}: {x}"})
            continue
        for kind in ("passing", "failing"):
            rows.append(_one(e, kind, getattr(mod, kind), entries))
    rows += [{"check": n, "fixture": "-", "ok": False, "why": f"refused: {why}"} for n, why in sorted(refused.items())]
    rows += [{"check": "-", "fixture": "-", "ok": False, "why": f} for f in faults]
    return rows
