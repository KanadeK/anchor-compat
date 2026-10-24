import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from anchor_compat.cli import main
from anchor_compat.core import Anchors, InputError, addresses, compare, load_baseline, scan


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.site = self.root / "site"
        self.site.mkdir()

    def page(self, name="index.html", text='<h2 id="install">Install</h2>'):
        path = self.site / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_historical_anchor_removed_without_any_current_inbound_link(self):
        self.page()
        before = scan(self.site)
        self.page(text='<h2 id="setup">Setup</h2>')
        report = compare(before, scan(self.site))
        self.assertFalse(report["ok"])
        self.assertEqual(
            report["missing"], [{"address": "/#install", "file": "index.html", "line": 1}]
        )
        self.assertEqual(report["added"], ["/#setup"])

    def test_preserved_alias_repairs_the_contract(self):
        self.page()
        before = scan(self.site)
        self.page(text='<span id="install"></span><h2 id="setup">Setup</h2>')
        self.assertTrue(compare(before, scan(self.site))["ok"])

    def test_page_removal_also_reports_fragment(self):
        self.page("old.html")
        before = scan(self.site)
        (self.site / "old.html").unlink()
        self.page("new.html")
        self.assertEqual(
            [x["address"] for x in compare(before, scan(self.site))["missing"]],
            ["/old.html", "/old.html#install"],
        )

    def test_exact_retirement_and_unused_allowance(self):
        self.page()
        before = scan(self.site)
        self.page(text="<p>changed</p>")
        current = scan(self.site)
        self.assertTrue(compare(before, current, ("/#install",))["ok"])
        with self.assertRaises(InputError):
            compare(before, current, ("/#typo",))

    def test_route_modes_and_unicode_percent_encoding(self):
        self.page("文档/index.html", '<h1 id="A &amp; B#%">x</h1>')
        self.assertIn("/%E6%96%87%E6%A1%A3/#A%20%26%20B%23%25", addresses(scan(self.site)))
        self.assertIn("/%E6%96%87%E6%A1%A3/index.html", scan(self.site, mode="file")["pages"])

    def test_comments_script_and_template_are_not_targets(self):
        self.page(
            text='<!-- <i id="comment"> --><script>"<i id=script>"</script><template id="outer"><h2 id="inert"></h2><template><a name="deep"></a></template></template><a name="legacy" id="legacy"></a>'
        )
        result = scan(self.site)
        self.assertEqual(set(result["pages"]["/"]["anchors"]), {"outer", "legacy"})
        self.assertEqual(result["findings"], [])

    def test_duplicate_targets_and_invalid_whitespace(self):
        self.page(text='<div id="x"></div>\n<div id="x"></div><b id="white space"></b>')
        findings = scan(self.site)["findings"]
        self.assertEqual([x["code"] for x in findings], ["duplicate-anchor", "invalid-anchor"])
        self.assertEqual(findings[0]["first_line"], 1)
        self.assertEqual(findings[0]["line"], 2)

    def test_duplicate_attribute(self):
        parser = Anchors()
        parser.feed('<b id="x" id="y">')
        self.assertEqual(parser.findings[0]["code"], "duplicate-id-attribute")

    def test_rawtext_and_noscript_do_not_create_proven_targets(self):
        self.page(
            text='<title><b id="fake1"></title><textarea id="active"><b id="fake2"></textarea><noscript><b id="conditional"></b></noscript><template><textarea></template><b id="still-inert"></textarea></template><b id="real"></b>'
        )
        self.assertEqual(set(scan(self.site)["pages"]["/"]["anchors"]), {"active", "real"})

    def test_excluded_subtree(self):
        self.page()
        self.page("drafts/x.html", '<div id="x"></div><div id="x"></div>')
        result = scan(self.site, exclude=("drafts",))
        self.assertEqual(list(result["pages"]), ["/"])

    def test_empty_and_invalid_encoding_are_not_clean_scans(self):
        with self.assertRaises(InputError):
            scan(self.site)
        (self.site / "broken.html").write_bytes(b"\xff")
        with self.assertRaises(InputError):
            scan(self.site)

    def test_symlink_refused_where_supported(self):
        self.page()
        try:
            os.symlink(self.site / "index.html", self.site / "link.html")
        except OSError:
            self.skipTest("symlinks unavailable for this Windows account")
        with self.assertRaises(InputError):
            scan(self.site)

    def test_large_html_refused(self):
        from unittest.mock import patch

        self.page(text="0123456789")
        with patch("anchor_compat.core.MAX_FILE", 4), self.assertRaises(InputError):
            scan(self.site)

    def test_cli_end_to_end_and_exclusive_baseline(self):
        self.page()
        baseline = self.root / "anchors.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["snapshot", str(self.site), "-o", str(baseline), "--json"]), 0)
            self.assertEqual(main(["snapshot", str(self.site), "-o", str(baseline), "--json"]), 2)
            self.assertEqual(
                main(["check", str(self.site), "--baseline", str(baseline), "--json"]), 0
            )
            self.page(text="<p>gone</p>")
            self.assertEqual(
                main(["check", str(self.site), "--baseline", str(baseline), "--json"]), 1
            )
        self.assertIn("install", load_baseline(baseline)["pages"]["/"]["anchors"])

    def test_invalid_snapshot_does_not_write_baseline(self):
        self.page(text='<div id="x"></div><div id="x"></div>')
        baseline = self.root / "baseline.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["snapshot", str(self.site), "-o", str(baseline), "--json"]), 1)
        self.assertFalse(baseline.exists())

    def test_malformed_or_unhealthy_baselines(self):
        self.page()
        good = scan(self.site)
        for content in [
            "{",
            "[]",
            "[" * 2000 + "]" * 2000,
            json.dumps({**good, "schema": True}),
            json.dumps({**good, "findings": [{}]}),
            json.dumps({**good, "pages": {}}),
        ]:
            with self.subTest(content=content):
                path = self.root / "baseline.json"
                path.write_text(content, encoding="utf-8")
                with self.assertRaises(InputError):
                    load_baseline(path)


if __name__ == "__main__":
    unittest.main()
