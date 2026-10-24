"""Console entry point."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .core import InputError, compare, load_baseline, scan


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Preserve published HTML page and fragment addresses."
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    snapshot = sub.add_parser("snapshot", help="record a healthy built HTML tree")
    snapshot.add_argument("root", type=Path)
    snapshot.add_argument("-o", "--output", type=Path, required=True)
    snapshot.add_argument("--url-mode", choices=["pretty", "file"], default="pretty")
    snapshot.add_argument("--exclude", action="append", default=[])
    check = sub.add_parser("check", help="check a new build against the historical baseline")
    check.add_argument("root", type=Path)
    check.add_argument("--baseline", type=Path, required=True)
    check.add_argument("--allow-removed", action="append", default=[])
    for child in [snapshot, check]:
        child.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            result = scan(args.root, mode=args.url_mode, exclude=tuple(args.exclude))
            if result["findings"]:
                report = {"ok": False, "findings": result["findings"], "baseline_written": False}
            else:
                # Exclusive creation prevents accidental loss of the historical contract.
                with args.output.open("x", encoding="utf-8", newline="\n") as stream:
                    json.dump(result, stream, ensure_ascii=True, indent=2)
                    stream.write("\n")
                report = {"ok": True, "pages": len(result["pages"]), "baseline_written": True}
        else:
            baseline = load_baseline(args.baseline)
            current = scan(args.root, mode=baseline["url_mode"], exclude=tuple(baseline["exclude"]))
            report = compare(baseline, current, tuple(args.allow_removed))
        if args.json:
            print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        else:
            print("PASS" if report["ok"] else "FAIL")
            for item in report.get("missing", []):
                print(
                    f"removed {json.dumps(item['address'])} (baseline {item['file']}:{item['line']})"
                )
            for item in report.get("findings", []):
                print(json.dumps(item, ensure_ascii=True, sort_keys=True))
        return 0 if report["ok"] else 1
    except (InputError, OSError, UnicodeError) as exc:
        error = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(error, ensure_ascii=True))
        else:
            print(f"anchor-compat: {str(exc)!r}", file=sys.stderr)
        return 2
