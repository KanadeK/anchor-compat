"""Historical addresses, derived from built HTML rather than guessed Markdown slugs."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import stat
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote

MAX_FILE = 10 * 1024 * 1024
MAX_PAGES = 10_000
MAX_ANCHORS = 200_000
MAX_BASELINE = 32 * 1024 * 1024


class InputError(ValueError):
    """Input is unreadable, incomplete or outside supported bounds."""


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors: dict[str, int] = {}
        self.findings: list[dict] = []
        self.template_depth = 0
        self.rawtext = None

    def handle_starttag(self, tag, attrs):
        if self.rawtext:
            return
        raw = tag in {
            "script",
            "style",
            "textarea",
            "title",
            "xmp",
            "iframe",
            "noembed",
            "noframes",
            "noscript",
            "plaintext",
        }
        if self.template_depth:
            if tag == "template":
                self.template_depth += 1
            elif raw:
                self.rawtext = tag
            return
        values = [v for k, v in attrs if k == "id"]
        if len(values) > 1:
            self.findings.append({"code": "duplicate-id-attribute", "line": self.getpos()[0]})
        # An anchor with id=x and name=x is one target, not a duplicate target.
        if tag == "a":
            values += [v for k, v in attrs if k == "name"]
        for value in dict.fromkeys(values):
            if value is None or value == "":
                continue
            if any(c in value for c in " \t\r\n\f\x00"):
                self.findings.append(
                    {"code": "invalid-anchor", "line": self.getpos()[0], "anchor": value}
                )
            if value in self.anchors:
                self.findings.append(
                    {
                        "code": "duplicate-anchor",
                        "line": self.getpos()[0],
                        "anchor": value,
                        "first_line": self.anchors[value],
                    }
                )
            else:
                self.anchors[value] = self.getpos()[0]
            if len(self.anchors) > MAX_ANCHORS:
                raise InputError("anchor count exceeds limit")
        if tag == "template":
            self.template_depth = 1
        elif raw:
            self.rawtext = tag

    def handle_startendtag(self, tag, attrs):
        # HTML void elements can carry IDs; template is not a void element.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.rawtext:
            if tag == self.rawtext and tag != "plaintext":
                self.rawtext = None
            return
        if tag == "template" and self.template_depth:
            self.template_depth -= 1


def route_for(relative: str, mode: str) -> str:
    route = "/" + quote(relative, safe="/")
    if mode == "pretty" and relative.endswith("index.html"):
        if relative == "index.html" or relative.endswith("/index.html"):
            route = route[: -len("index.html")]
    return route


def scan(root: Path, *, mode: str = "pretty", exclude: tuple[str, ...] = ()) -> dict:
    if mode not in {"pretty", "file"}:
        raise InputError("unknown URL mode")
    if (
        root.is_symlink()
        or not root.is_dir()
        or getattr(root.lstat(), "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise InputError("HTML root must be an existing, non-symlink directory")
    pages: dict[str, dict] = {}
    findings = []
    count = 0

    def fail_walk(error):
        raise InputError("cannot enumerate HTML root") from error

    for directory, dirs, files in os.walk(root, followlinks=False, onerror=fail_walk):
        for name in sorted(dirs + files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if any(fnmatch.fnmatchcase(relative, pattern) for pattern in exclude):
                if name in dirs:
                    dirs.remove(name)
                continue
            if (
                path.is_symlink()
                or getattr(path.lstat(), "st_file_attributes", 0)
                & stat.FILE_ATTRIBUTE_REPARSE_POINT
            ):
                raise InputError(f"symlink/reparse entry is unsupported: {relative!r}")
        for name in sorted(files):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if any(fnmatch.fnmatchcase(relative, pattern) for pattern in exclude):
                continue
            if path.suffix.lower() not in {".html", ".htm"}:
                continue
            if not path.is_file():
                raise InputError(f"non-regular HTML entry: {relative!r}")
            with path.open("rb") as stream:
                data = stream.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                raise InputError(f"HTML file exceeds 10 MiB: {relative!r}")
            parser = Anchors()
            try:
                parser.feed(data.decode("utf-8-sig", errors="strict"))
                parser.close()
            except UnicodeError as exc:
                raise InputError(f"HTML is not UTF8: {relative!r}") from exc
            route = route_for(relative, mode)
            if route in pages:
                raise InputError("multiple HTML files resolve to one route")
            count += len(parser.anchors)
            if len(pages) >= MAX_PAGES or count > MAX_ANCHORS:
                raise InputError("site page/anchor count exceeds limit")
            pages[route] = {
                "file": relative,
                "anchors": dict(sorted(parser.anchors.items())),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
            findings.extend({"file": relative, **finding} for finding in parser.findings)
    if not pages:
        raise InputError("no HTML files found")
    return {
        "schema": 1,
        "url_mode": mode,
        "exclude": list(exclude),
        "pages": dict(sorted(pages.items())),
        "findings": findings,
    }


def load_baseline(path: Path) -> dict:
    with path.open("rb") as stream:
        data = stream.read(MAX_BASELINE + 1)
    if len(data) > MAX_BASELINE:
        raise InputError("baseline exceeds 32 MiB")
    try:
        baseline = json.loads(data)
        if (
            type(baseline) is not dict
            or baseline.get("schema") != 1
            or type(baseline["schema"]) is not int
        ):
            raise ValueError
        if baseline["url_mode"] not in {"pretty", "file"}:
            raise ValueError
        if type(baseline["exclude"]) is not list or not all(
            isinstance(x, str) for x in baseline["exclude"]
        ):
            raise ValueError
        pages = baseline["pages"]
        if (
            type(pages) is not dict
            or not 1 <= len(pages) <= MAX_PAGES
            or baseline.get("findings") != []
        ):
            raise ValueError
        count = 0
        for route, page in pages.items():
            if (
                not isinstance(route, str)
                or not route.startswith("/")
                or "#" in route
                or "?" in route
            ):
                raise ValueError
            if (
                type(page) is not dict
                or not isinstance(page["file"], str)
                or type(page["anchors"]) is not dict
            ):
                raise ValueError
            if not isinstance(page["sha256"], str) or len(page["sha256"]) != 64:
                raise ValueError
            for anchor, line in page["anchors"].items():
                if not isinstance(anchor, str) or not anchor or type(line) is not int or line < 1:
                    raise ValueError
            count += len(page["anchors"])
        if count > MAX_ANCHORS:
            raise ValueError
        return baseline
    except (ValueError, KeyError, TypeError, RecursionError) as exc:
        raise InputError("invalid or unhealthy schema-1 baseline") from exc


def addresses(inventory: dict) -> dict[str, dict]:
    result = {}
    for route, page in inventory["pages"].items():
        result[route] = {"file": page["file"], "line": 1}
        for anchor, line in page["anchors"].items():
            result[route + "#" + quote(anchor, safe="")] = {"file": page["file"], "line": line}
    return result


def compare(baseline: dict, current: dict, allowed: tuple[str, ...] = ()) -> dict:
    before, after = addresses(baseline), addresses(current)
    removed = before.keys() - after.keys()
    unused = set(allowed) - removed
    if unused:
        raise InputError(
            f"retirement allowance is not an actual removed address: {sorted(unused)!r}"
        )
    missing = [
        {"address": address, **before[address]} for address in sorted(removed - set(allowed))
    ]
    return {
        "schema": 1,
        "ok": not missing and not current["findings"],
        "missing": missing,
        "retired": sorted(allowed),
        "added": sorted(after.keys() - before.keys()),
        "findings": current["findings"],
        "pages_checked": len(current["pages"]),
    }
