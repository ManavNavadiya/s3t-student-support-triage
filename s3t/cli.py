"""
cli.py - command line:  python -m s3t <command>

  triage "text"            classify one message (JSON on screen)
  triage --file in.csv     classify a file: .csv (needs a `text` column), .jsonl or .txt
                           (one message per line); --out results.jsonl to save
  evaluate --csv f.csv     score labelled data (e.g. classmates' messages) with the asset
  serve                    start the HTTP API  (default http://127.0.0.1:8000, docs at /docs)
  info                     which model / thresholds are loaded
  schema                   print the JSON Schema of the request and result
  calibrate                choose review thresholds from training-set cross-validation
  verify                   run all checks and write reports/week6_verification.md
"""
import argparse
import csv
import json
import sys
from pathlib import Path

from .config import MAX_BATCH, __version__


def _read_inputs(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if "text" not in (reader.fieldnames or []):
                raise SystemExit(f"{path}: needs a 'text' column (found {reader.fieldnames})")
            return [(r.get("id") or None, r["text"]) for r in reader if (r["text"] or "").strip()]
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if suffix == ".jsonl":
        out = []
        for l in lines:
            d = json.loads(l)
            out.append((d.get("id"), d["text"]))
        return out
    return [(None, l.strip()) for l in lines]


def cmd_triage(a):
    from .triage import Triage
    t = Triage(model=a.model, thresholds=tuple(a.thresholds) if a.thresholds else None,
               extended_crisis=not a.core_crisis)
    if a.file:
        items = _read_inputs(Path(a.file))
        results = []
        for i in range(0, len(items), MAX_BATCH):
            chunk = items[i:i + MAX_BATCH]
            results += t.predict_batch([x[1] for x in chunk], ids=[x[0] for x in chunk])
        lines = [json.dumps(r.model_dump(), ensure_ascii=False) for r in results]
        if a.out:
            Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
            n_rev = sum(r.human_review.required for r in results)
            print(f"{len(results)} messages -> {a.out}  ({n_rev} flagged for human review)")
        else:
            print("\n".join(lines))
    elif a.text:
        print(json.dumps(t.predict(a.text).model_dump(), indent=2, ensure_ascii=False))
    else:
        raise SystemExit("give a message or --file")


def cmd_evaluate(a):
    from .evaluation import evaluate_rows, read_rows, render_markdown
    from .triage import Triage
    t = Triage(model=a.model, thresholds=tuple(a.thresholds) if a.thresholds else None)
    rows = read_rows(a.csv, a.text_col, a.category_col, a.urgency_col)
    md = render_markdown(evaluate_rows(t, rows), f"Evaluation of {Path(a.csv).name}")
    print(md)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(md, encoding="utf-8")
        print(f"\nSaved {a.out}")


def cmd_serve(a):
    import os
    try:
        import uvicorn
    except ImportError:
        raise SystemExit("pip install 's3t[api]' to run the HTTP service")
    os.environ["S3T_MODEL"] = a.model
    uvicorn.run("s3t.api:app", host=a.host, port=a.port)


def cmd_info(a):
    from .triage import Triage
    print(json.dumps(Triage(model=a.model).info(), indent=2))


def cmd_schema(a):
    from .schemas import BatchRequest, TriageRequest, TriageResult
    print(json.dumps({"TriageRequest": TriageRequest.model_json_schema(),
                      "BatchRequest": BatchRequest.model_json_schema(),
                      "TriageResult": TriageResult.model_json_schema()}, indent=2))


def cmd_calibrate(a):
    from .calibrate import calibrate
    calibrate(target=a.target, folds=a.folds, report_dir=a.report_dir,
              urgency_trigger=a.urgency_trigger)


def cmd_verify(a):
    from .verify import run
    sys.exit(0 if run(a.report_dir) else 1)


def main(argv=None):
    p = argparse.ArgumentParser(prog="s3t", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"s3t {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        sp = sub.add_parser(name, **kw)
        sp.set_defaults(fn=fn)
        return sp

    def model_opt(sp):
        sp.add_argument("--model", default="auto", choices=["auto", "baseline", "sbert", "sbert+tfidf"])

    sp = add("triage", cmd_triage, help="classify messages"); model_opt(sp)
    sp.add_argument("text", nargs="?"); sp.add_argument("--file"); sp.add_argument("--out")
    sp.add_argument("--thresholds", nargs=2, type=float, metavar=("CAT", "URG"),
                    help="override the review thresholds")
    sp.add_argument("--core-crisis", action="store_true", help="use only the Week 3 crisis phrases")

    sp = add("evaluate", cmd_evaluate, help="score a labelled CSV"); model_opt(sp)
    sp.add_argument("--csv", required=True); sp.add_argument("--out")
    sp.add_argument("--text-col", default="text"); sp.add_argument("--category-col", default="category")
    sp.add_argument("--urgency-col", default="urgency")
    sp.add_argument("--thresholds", nargs=2, type=float, metavar=("CAT", "URG"))

    sp = add("serve", cmd_serve, help="start the HTTP API"); model_opt(sp)
    sp.add_argument("--host", default="127.0.0.1"); sp.add_argument("--port", type=int, default=8000)
    sp = add("info", cmd_info, help="show loaded model"); model_opt(sp)
    add("schema", cmd_schema, help="print JSON Schema")
    sp = add("calibrate", cmd_calibrate, help="choose review thresholds")
    sp.add_argument("--target", type=float, default=0.05,
                    help="max share of messages that may be wrong AND unflagged (default 0.05)")
    sp.add_argument("--folds", type=int, default=5); sp.add_argument("--report-dir", default="reports")
    sp.add_argument("--urgency-trigger", action="store_true",
                    help="also use the urgency score as a review trigger (off by default: the "
                         "score is not informative; High urgency is reviewed by rule R4)")
    sp = add("verify", cmd_verify, help="run all checks")
    sp.add_argument("--report-dir", default="reports")

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()