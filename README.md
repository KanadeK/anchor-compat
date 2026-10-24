# anchor-compat

Preserve published documentation deep links when headings or pages change.

Most link checkers inspect links in the current build. A removed `#installation` anchor can therefore pass CI after every internal link is updated, while external bookmarks still break. `anchor-compat` records the page and fragment addresses in a known-good HTML build and checks the next build against that contract. It reads actual HTML IDs, including generated heading IDs, without guessing your Markdown renderer's slug rules.

[简体中文](README.zh-CN.md) · [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

## Install and prove the workflow

Python 3.11+; no runtime dependencies. In a virtual environment:

```sh
git clone https://github.com/KanadeK/anchor-compat.git
cd anchor-compat
python -m pip install .
anchor-compat snapshot examples/old -o anchors.json
anchor-compat check examples/changed --baseline anchors.json
# FAIL: /#installation was removed; exit 1
anchor-compat check examples/fixed --baseline anchors.json
# PASS: the explicit alias preserves the old address; exit 0
```

PowerShell runs these commands as written; check `$LASTEXITCODE` after each check. `python -m anchor_compat` is equivalent to the installed command. The example HTML is synthetic and contains no external resources.

## Use with your documentation generator

Build the current published version into a directory, then run `snapshot` once. Commit the baseline JSON. After each new Sphinx, MkDocs, Hugo, or other static HTML build:

```sh
anchor-compat check site --baseline anchors.json --json
```

The tool never runs your generator or serves your files. The baseline records relative filenames, IDs, line locations and content hashes; a content change alone is harmless. Snapshot output uses exclusive creation, so an existing baseline is never overwritten. After reviewing intentional breaking changes, create a new baseline at a new filename and replace the old one yourself.

`snapshot --url-mode pretty` (default) maps `index.html` to `/` and `guide/index.html` to `/guide/`. Other paths keep their extension. Use `--url-mode file` for servers that expose index filenames literally. URL paths are relative to your site's mount point, so the same baseline works under `/docs/` or another deployment prefix. Path and fragment characters are percent-encoded; IDs are case-sensitive. The mode and exclusions are saved in the baseline and reused during checks.

Exclude explicitly unstable generated pages at snapshot time with repeated `--exclude` glob patterns. Patterns match the whole POSIX relative path using Python `fnmatchcase`, including slashes; excluding a directory name prunes its subtree. An unreadable or oversized input fails the scan instead of silently disappearing.

Intentional retirement can be explicit for a single check:

```sh
anchor-compat check site --baseline anchors.json --allow-removed '/#installation'
```

Each allowance is an exact, percent-encoded address. Removed pages and their fragments are separate addresses. Unused allowances fail as input errors, which catches stale exceptions and typos. Preserving an old ID alias in the HTML is usually the most durable repair.

## Output and limits

Exit `0`: all old addresses remain or are explicitly retired, with no current duplicate/invalid IDs. Exit `1`: compatibility or HTML ID findings. Exit `2`: input, schema, I/O or limit error. `--json` emits one JSON object; text output escapes untrusted addresses.

Schema 1 reports include `ok`, `missing` (baseline file and line), `retired`, `added`, `findings`, and `pages_checked`. Snapshot refuses duplicate IDs, whitespace in IDs, and duplicate ID attributes. Legacy `<a name>` is included. Template contents, comments, raw text elements and noscript contents are excluded. Empty IDs are ignored.

The version 0.1.1 boundary is deliberately small:

- UTF8 static `.html` and `.htm` only; no browser, JavaScript execution, network requests or redirect verification. Runtime-generated IDs, shadow DOM and noscript-dependent behavior need browser tests.
- ID presence is checked; semantic equivalence, visibility and successful navigation are not proved. This is not an HTML validator or an accessibility audit.
- Symlinks and Windows junction entries are refused. Do not scan a tree being modified concurrently; this is a local build artifact checker, not a hostile filesystem sandbox.
- Maximum 10 MiB per HTML file, 10,000 HTML pages, 200,000 anchors total, and 32 MiB baseline. Scan and compare memory scales with address count. Invalid UTF8 or incomplete enumeration is an error.
- No extensionless-route rewrite rules are inferred. Match the URL mode to your host.

## Why another tool?

[lychee](https://github.com/lycheeverse/lychee) is a mature current-link checker and complements this tool. [sphinxext-rediraffe](https://github.com/sphinx-doc/sphinxext-rediraffe) manages page redirects in Sphinx. This tool adds a persistent, generator-neutral contract for **previously published fragment addresses**, including addresses no longer referenced anywhere in the new build. Broken/renamed anchors are a real maintenance issue, for example [pvlib issue 2489](https://github.com/pvlib/pvlib-python/issues/2489). No source from those projects is copied.

## Development and cleanup

```sh
python -m pip install -e . -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m build
python -m pip uninstall anchor-compat
```

Delete the demonstration `anchors.json` when finished. The tool writes only the explicitly requested snapshot file, uses no cache or user configuration directory, and makes no changes during `check`. Tests create and clean temporary synthetic sites. CI tests Python 3.11 and 3.14 on Windows, Linux and macOS. See [MIT license](LICENSE) and [third-party notes](THIRD_PARTY.md).
