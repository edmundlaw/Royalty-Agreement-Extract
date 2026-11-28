"""Synthetic screen regressions and isolated summary-route integration."""
import contextlib
from datetime import date
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

from royalty_research import agreement_summary as summary
from royalty_research import royalty_screen as screen
from royalty_research.m13_production import licence_gate
from royalty_research.mapping import map_contract
from royalty_research.storage import read_json, sha256


PADDING = "The parties hereby agree to the applicable contractual notices.\n" * 38
REDACTED = "Licensee shall pay a royalty of [***]% of Net Sales."
URL = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/ex10.htm"


class ScreenTests(unittest.TestCase):
    def result(self, source, *, pad=True, raw=b"", parser="PLAIN_TEXT", verified_identity=True, limitation=""):
        text = (PADDING if pad else "") + source
        result = screen.classify(text, raw, parser, verified_identity=verified_identity, limitation=limitation)
        for row in result[1] + result[2] + result[3]:
            self.assertEqual(text[row["start"]:row["end"]], row["excerpt"])
        return result

    def test_rate_redaction_families(self):
        for clause, family in (
            ("Royalty Rate: [redacted]%", "R1"),
            ("Running Royalty Rate shall be [***]", "R9"),
            ("Licensee shall pay Licensor a royalty of [**] on Net Sales", "R2"),
            ("The royalty is calculated at [ * % ] of the gross selling price", "R4"),
            ("royalty = {***} × Net Sales", "R6"),
            ("Net Sales × [***] = royalty", "R6"),
            ("pay *** percent of proceeds as royalties", "R7"),
            ("Sublicensing consideration payable to licensor: [***]%", "R8"),
            ("Running Royalty\n(i) [***]% of sales in Territory A", "R8"),
            ("Licensee shall pay a royalty of US$*** per tonne produced", "PER_UNIT"),
            ("Royalty per building sold: $[***]", "PER_UNIT"),
            ("Market | Royalty Rate\nTerritory A | [***]", "T1"),
            ("Running Royalty | [***]", "T1"),
        ):
            with self.subTest(clause=clause):
                uncertain, redactions, safeguards, _ = self.result(clause)
                self.assertIn(family, {r["family"] for r in redactions})
                self.assertFalse(uncertain or safeguards)

    def test_disclosed_economics_override(self):
        for disclosed in (
            "Licensee shall pay a royalty of 5% above [***] of sales.",
            "Royalty rate: 3–5%.",
            "Royalty rate: five percent ([***]%).",
            "Royalty rate: one-half percent.",
            "Royalty rate: 250 basis points.",
            "Royalty rate: low single digit.",
            "Licensee shall pay a royalty of $2.50 per barrel extracted.",
            "Minimum annual royalty: $125,000.",
            "Annual licence fee: $75,000.",
            "Royalty advance: $10,000.",
            "Licensor receives 50% of royalties received.",
            "Royalty = 0.03 × Gross Revenue.",
            "Appendix A\nThis deed grants a perpetual royalty equal to 4% of Gross Revenue.",
            "The parties agree to a royalty of 5% of the sales price of SHAWOOD buildings.",
            "Parties enter a second agreement.\nRoyalty Rate | Market\n[***] | US\n0% | UK",
            "Running Royalty: Valid Claims | 5%\nRunning Royalty: No Valid Claim | 3%\n"
            "Non-Royalty Sublicensing Consideration | 20%",
            "Territory | Royalty Rate (%)\nUSA | [***]\nCanada | 4",
        ):
            with self.subTest(disclosed=disclosed):
                _, reds, safeguards, _ = self.result(REDACTED + "\n" + PADDING * 25 + disclosed)
                self.assertTrue(reds)
                self.assertTrue(safeguards)

    def test_unrelated_economics(self):
        full = (REDACTED + "\nA change of control means more than 50% of voting stock.\n"
                "Licensee may offset 50% of litigation expenses against royalties.\n"
                "Royalties payable shall not be reduced by more than 50%.\n"
                "The product specifications include a 50% concentration.\n"
                "The purchaser acquires 100% of the royalty interests.\n"
                "The buyer receives 100% of certain royalty receipts.\n"
                "The upfront fee is $50,000 and the milestone is $100,000.")
        uncertain, redactions, safeguards, rejected = self.result(full)
        self.assertTrue(redactions)
        self.assertFalse(uncertain or safeguards)
        self.assertGreaterEqual(len(rejected), 5)

    def test_no_evidence_from_non_rate_placeholders(self):
        for control in (
            "A royalty of 5% of sales of product [***].",
            "Royalty rate of five percent ([***]%).",
            "Royalty rate of 5% **.",
            "Purchase price of $*** million.",
            "Royalty reporting date: [***].",
            "Royalty payment date: [†].",
            "Exhibit [###].",
            "Amounts replaced with [***] have been omitted.",
            "Milestone | Amount\nFirst sale | [***]",
        ):
            with self.subTest(control=control):
                self.assertFalse(self.result(control)[1])

    def test_unpriced_net_proceeds(self):
        uncertain, redactions, safeguards, _ = self.result(
            "The licence is non-royalty-bearing. The Net Royalty Fee equals Net Proceeds "
            "from a future sublicense. The sublicense fee remains to be negotiated.")
        self.assertFalse(uncertain or redactions or safeguards)

    def test_hypothetical_rate_and_unmapped_page_number(self):
        hypothetical = ("For clarity and by way of example, if Third Party Royalties of [***]% of "
                        "Net Sales are payable, the revenue share is reduced.")
        uncertain, redactions, _, _ = self.result(hypothetical)
        self.assertIn("ILLUSTRATIVE_RATE_POSITION", uncertain)
        self.assertFalse(redactions)
        for table in ("Royalty Rate\n30", "Royalty Rate\nSales tier | Product A | Product B\n30"):
            with self.subTest(table=table):
                uncertain, _, safeguards, _ = self.result(table)
                self.assertIn("TABLE_HEADER_MAPPING_UNCERTAIN", uncertain)
                self.assertFalse(safeguards)

    def test_uncertainty(self):
        for source, kwargs, reason in (
            (REDACTED, {"pad": False}, "SHORT_OR_EMPTY_SOURCE"),
            (REDACTED, {"raw": b"<html>", "parser": "HTML_TEXT"}, "HTML_END_NOT_ESTABLISHED"),
            (REDACTED, {"raw": b"<DOCUMENT>\n<TEXT>\n<html></html>", "parser": "HTML_TEXT"},
             "INCOMPLETE_SEC_WRAPPER"),
            (REDACTED, {"verified_identity": False}, "SOURCE_IDENTITY_UNVERIFIED"),
            (REDACTED, {"limitation": "embedded images"}, "UNSUPPORTED_OR_UNREADABLE_SOURCE"),
            (REDACTED + "\n[DOCUMENT TRUNCATED]", {}, "INCOMPLETE_SOURCE"),
            (REDACTED + "\nOther royalty rates are set forth in Annex X.", {}, "MISSING_SCHEDULE_OR_APPENDIX"),
            (REDACTED + "\nEXHIBIT D\nCLINICAL SUPPLY AGREEMENT\n[***]", {}, "MISSING_SCHEDULE_OR_APPENDIX"),
            (REDACTED + "\nThe licence agreement is attached hereto as Exhibit A; and",
             {}, "MISSING_SCHEDULE_OR_APPENDIX"),
            (REDACTED + "\nThe licence agreement is attached to this Agreement as Schedule 2.1.\n"
                        "Schedule 2.1 | Licence Agreement | 25", {}, "MISSING_SCHEDULE_OR_APPENDIX"),
            (REDACTED + "\nRoyalty Rate: [###]", {}, "UNSUPPORTED_RATE_MARKER"),
            (REDACTED + "\nThe royalty payable on this item may be 1.5%.", {}, "AMBIGUOUS_ROYALTY_PERCENTAGE"),
            (REDACTED, {"parser": "PDF_TEXT"}, "UNSUPPORTED_OR_UNREADABLE_SOURCE"),
        ):
            with self.subTest(reason=reason):
                self.assertIn(reason, self.result(source, **kwargs)[0])


def stub_frozen_source(raw):
    return SimpleNamespace(Fetcher=lambda _: SimpleNamespace(
        get=lambda url: SimpleNamespace(url=url, body=raw, issue=None)))


def frozen_keep(_, document, number):
    return {'source_url': document.url, 'decision': 'KEEP', 'flags': ['pointer_ok'],
            'extractor_status': 'not_sent'}


def hit(url, file_type="EX-10.1"):
    return {"source_url": url, "file_type": file_type}


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.context = tempfile.TemporaryDirectory()
        self.addCleanup(self.context.cleanup)
        self.root = Path(self.context.name)
        self.meta = dict(parser="PLAIN_TEXT", limitation="", source_url=URL, document_id="TEST", source_sha256="test")

    def test_sublicensing_taxonomy_and_exact_source(self):
        source = PADDING + REDACTED + "\nLicensee shall pay 20% of Sublicensing Consideration."
        self.assertEqual(screen.audit_screen(self.root, source, b"", self.meta, verified_identity=True)["status"], "KEEP")
        record = read_json(self.root / "royalty_screen.json")
        self.assertIn("SUBLICENSE_SHARE_ONLY_TAXONOMY_PENDING", record["flags"])
        self.assertEqual(record["safeguards"][0]["value"], "20%")
        self.assertEqual(record["screened_sha256"], sha256((self.root / record["screened_source"]).read_bytes()))

    def test_failure_keeps(self):
        source = PADDING + REDACTED
        for function, exception in (("atomic_json", OSError), ("read_json", OSError), ("classify", RuntimeError)):
            with self.subTest(function=function), patch.object(screen, function, side_effect=exception), contextlib.redirect_stderr(io.StringIO()):
                record = screen.audit_screen(self.root, source, b"", self.meta, verified_identity=True)
                self.assertFalse(screen.record_exclusion(self.root, record))
                if (self.root / "royalty_screen.json").exists():
                    self.assertEqual(read_json(self.root / "royalty_screen.json")["status"], "KEEP")

    def test_summary_batch_dispatch_and_failure_fallback(self):
        cases = (
            ("dry-run", REDACTED, False, False, False, None),
            ("default", REDACTED, True, False, True, None),
            ("exclude", REDACTED, True, True, False, "WOULD_SKIP"),
            ("keep", "The royalty rate is 5%.", True, True, True, "KEEP"),
            ("missing", REDACTED + "</p><p>EXHIBIT D</p><p>CLINICAL SUPPLY AGREEMENT</p><p>[***]",
             True, True, True, "KEEP"),
            ("screen-error", REDACTED, True, True, True, "KEEP"),
            ("audit-write", REDACTED, True, True, True, None),
            ("receipt-write", REDACTED, True, True, True, "WOULD_SKIP"),
            ("receipt-readback", REDACTED, True, True, True, "WOULD_SKIP"),
            ("source-changed", REDACTED, True, True, True, "WOULD_SKIP"),
            ("screened-source-changed", REDACTED, True, True, True, "WOULD_SKIP"),
            ("audit-changed", REDACTED, True, True, True, "WOULD_SKIP"),
            ("prompt-changed", REDACTED, True, True, True, "WOULD_SKIP"),
            ("rollback", REDACTED, True, False, True, None),
        )
        make_temp = tempfile.mkdtemp
        real_exclusion = summary.record_exclusion
        real_classify = screen.classify
        real_write = screen.atomic_json
        real_read = screen.read_json
        for case, clause, execute, opt_in, calls_reader, status in cases:
            sample = self.root / case
            raw = ("<html><body><p>" + PADDING + clause + "</p></body></html>").encode()

            def make_run(*args, **kwargs):
                if kwargs.get("prefix", "").startswith("runs_summary_"):
                    return str(sample)
                return make_temp(*args, **kwargs)

            def exclusion_with_fault(run, audit):
                stale = {"source-changed": "source.htm", "screened-source-changed": "screened_source.txt",
                         "prompt-changed": "prompt.txt", "audit-changed": "royalty_screen.json"}
                if case in stale:
                    p = run / stale[case]
                    p.write_bytes(p.read_bytes() + b" ")
                    if case == "audit-changed":
                        real_write(p, {**audit, "source_url": URL + "x"})
                return real_exclusion(run, audit)

            def write_with_fault(path, obj):
                fault = {"audit-write": "royalty_screen.json", "receipt-write": "royalty_exclusion.json"}
                if path.name == fault.get(case):
                    raise OSError("test write failure")
                real_write(path, obj)

            def read_with_fault(path):
                result = real_read(path)
                if case == "receipt-readback" and path.name == "royalty_exclusion.json":
                    result["decision"] = "KEEP"
                return result

            with self.subTest(case=case), contextlib.ExitStack() as stack:
                workbook = stack.enter_context(patch.object(summary, "write_workbook"))
                invocation = stack.enter_context(patch.object(summary.subprocess, "run"))
                for manager in (
                    patch.object(summary, "sec_user_agent", return_value="test"),
                    patch.object(summary, "SECClient"),
                    patch.object(summary.frozen, "load_screen", return_value=stub_frozen_source(raw)),
                    patch.object(summary.frozen, "screen_document", side_effect=frozen_keep),
                    patch.object(summary, "discover", return_value=[hit(URL)]),
                    patch.object(summary, "gics_names", return_value={}),
                    patch.object(summary, "_preflight_subscription"),
                    patch.object(summary, "load_agreements"),
                    patch.object(summary.shutil, "which", return_value="/codex"),
                    patch.object(summary.tempfile, "mkdtemp", side_effect=make_run),
                    patch.object(summary, "download_gics", return_value=(b"gics", "saved")),
                    patch.object(summary, "record_exclusion", side_effect=exclusion_with_fault),
                    patch.object(screen, "classify", side_effect=RuntimeError if case == "screen-error" else real_classify),
                    patch.object(screen, "atomic_json", side_effect=write_with_fault),
                    patch.object(screen, "read_json", side_effect=read_with_fault),
                ):
                    stack.enter_context(manager)
                run = sample / "exhibit-001"
                invocation.return_value.returncode = 0

                def save_response(*_args, **_kwargs):
                    (run / "raw_response.txt").write_text("mock response")
                    return invocation.return_value

                invocation.side_effect = save_response
                summary.batch(date(2026, 11, 16), date(2026, 11, 16), 1, execute=execute,
                              exclude_royalty_screen=screen.SCREEN_VERSION if opt_in else None)
                self.assertEqual(invocation.call_count, int(calls_reader))
                self.assertEqual((run / "raw_response.txt").exists(), calls_reader)
                self.assertEqual(workbook.call_count, int(calls_reader))
                if calls_reader:
                    self.assertEqual(workbook.call_args.args[0], [run])
                    self.assertEqual(invocation.call_args.kwargs["input"], (run / "prompt.txt").read_text())
                if status is not None:
                    record = read_json(run / "royalty_screen.json")
                    self.assertEqual((record["decision"], record["status"]), ("KEEP", status))
                    if case not in {"source-changed", "screened-source-changed", "prompt-changed"}:
                        self.assertEqual(record["raw_sha256"], sha256((run / "source.htm").read_bytes()))
                        self.assertEqual(record["prompt_sha256"], sha256((run / "prompt.txt").read_bytes()))
                        prompt_exhibit = (run / "prompt.txt").read_text().split("\n\nSEC EXHIBIT TEXT\n\n", 1)[1]
                        normalized = "\n".join(line.split("] ", 1)[1] for line in prompt_exhibit.splitlines() if line)
                        self.assertEqual(normalized, (run / "screened_source.txt").read_text())
                else:
                    self.assertFalse((run / "royalty_screen.json").exists())
                receipt_path = run / "royalty_exclusion.json"
                self.assertEqual(receipt_path.is_file(), case == "exclude")
                if case == "exclude":
                    receipt = read_json(receipt_path)
                    self.assertEqual((receipt["decision"], receipt["status"]), ("SKIP", "SKIPPED"))
                    self.assertEqual(receipt["screen_version"], screen.SCREEN_VERSION)
                    self.assertEqual(receipt["screened_sha256"], sha256(normalized.encode()))
                    self.assertTrue(receipt["entire_source_scanned"])
                    self.assertFalse(receipt["uncertainty"])
                    for evidence in receipt["redactions"]:
                        self.assertEqual(normalized[evidence["start"]:evidence["end"]], evidence["excerpt"])

    def test_invalid_prepare_source_never_reaches_reader(self):
        prototype = summary.frozen.load_screen()
        with (
            patch.object(summary, "sec_user_agent", return_value="test"),
            patch.object(summary, "SECClient"),
            patch.object(prototype.Fetcher, "get",
                         return_value=prototype.RawDocument(URL, b"<html><body></body></html>")),
            patch.object(summary, "discover", return_value=[hit(URL)]),
            patch.object(summary, "candidate_rank", return_value=0),
            patch.object(summary.tempfile, "mkdtemp", return_value=str(self.root)),
            patch.object(summary, "read") as reader,
        ):
            code = summary.batch(date(2026, 11, 16), date(2026, 11, 16), 1, execute=True,
                                 exclude_royalty_screen=screen.SCREEN_VERSION)
            self.assertEqual(code, 1)
            reader.assert_not_called()
            row, = read_json(self.root / "screening_log.json")["documents"]
            self.assertEqual((row["decision"], row["flags"]), ("REVIEW", ["unreadable_source"]))

    def test_preparation_limits_preserve_frozen_evidence_for_review(self):
        candidates = [URL, URL.replace("ex10.htm", "ex11.htm"), URL.replace("ex10.htm", "ex12.htm")]
        failures = [summary.SourceTooLarge("Above 300,000 characters"), summary.ParseError("No readable text found"),
                    RuntimeError("Writing prompt failed")]

        def screen_candidate(_, document, number):
            return dict(frozen_keep(_, document, number), prescreen_decision="KEEP", captured_rate_text="7%")

        with (
            patch.object(summary, "sec_user_agent", return_value="test"),
            patch.object(summary, "SECClient"),
            patch.object(summary.frozen, "load_screen", return_value=stub_frozen_source(b"source")),
            patch.object(summary.frozen, "screen_document", side_effect=screen_candidate) as frozen_screen,
            patch.object(summary, "discover", return_value=[hit(url) for url in candidates]),
            patch.object(summary, "candidate_rank", return_value=0),
            patch.object(summary, "prepare", side_effect=failures),
            patch.object(summary, "read") as reader,
        ):
            self.assertEqual(summary.batch(date(2026, 1, 1), date(2026, 1, 10), 2, execute=True,
                                           output_root=self.root), 1)
            self.assertEqual(frozen_screen.call_count, 3)
            reader.assert_not_called()
        log, = self.root.glob("*/screening_log.json")
        report = read_json(log)
        self.assertNotIn("preparation_failures", report)
        for row, flags in zip(report["documents"],
                              (["pointer_ok", "source_too_large"], ["pointer_ok", "unreadable_source"],
                               ["pointer_ok"]), strict=True):
            self.assertEqual((row["prescreen_decision"], row["decision"]), ("KEEP", "REVIEW"))
            self.assertEqual(row["captured_rate_text"], "7%")
            self.assertEqual(row["flags"], flags)
            self.assertEqual(row["failure_stage"], "prepare")

    def test_non_ex10_is_excluded_before_fetch_or_screen(self):
        non_ex10 = [hit(URL, "EX-99.1"), hit(URL.replace("ex10.htm", "form.htm"), "8-K"),
                    hit(URL.replace("ex10.htm", "offer.htm"), "424B3"),
                    hit(URL.replace("ex10.htm", "xbrl.htm"), "EX-101.INS"),
                    hit(URL.replace("ex10.htm", "unknown.htm"), None)]
        eligible = hit(URL.replace("ex10.htm", "description.htm"), "ex-10.17")
        fetcher = SimpleNamespace(get=lambda url: SimpleNamespace(url=url, body=b"source", issue=None))
        with (
            patch.object(summary, "sec_user_agent", return_value="test"),
            patch.object(summary, "SECClient"),
            patch.object(summary.frozen, "load_screen", return_value=SimpleNamespace(Fetcher=lambda _: fetcher)),
            patch.object(fetcher, "get", wraps=fetcher.get) as fetch,
            patch.object(summary.frozen, "screen_document", side_effect=frozen_keep) as frozen_screen,
            patch.object(summary, "discover", return_value=[*non_ex10, eligible, non_ex10[0]]),
            patch.object(summary, "prepare") as prepare,
        ):
            self.assertEqual(summary.batch(date(2026, 1, 1), date(2026, 1, 10), 1, output_root=self.root), 0)
            fetch.assert_called_once_with(eligible["source_url"])
            frozen_screen.assert_called_once()
            self.assertEqual(frozen_screen.call_args.args[1].url, eligible["source_url"])
            prepare.assert_called_once()
            self.assertEqual(prepare.call_args.args[0], eligible["source_url"])
        path, = self.root.glob("*/screening_log.json")
        rows = {row["source_url"]: row for row in read_json(path)["documents"]}
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[eligible["source_url"]]["document_type"], "EX-10.17")
        for item in non_ex10:
            row = rows[item["source_url"]]
            self.assertEqual((row["decision"], row["prescreen_decision"], row["extractor_status"]),
                             ("EXCLUDED", None, "not_sent"))
            self.assertEqual(row["document_type"], item["file_type"] or "Unknown")
            self.assertEqual(row["reason"], "not EX-10" if item["file_type"] else "document type unverified")

    def test_explicit_urls_get_document_types_from_filing_index(self):
        prototype = summary.frozen.load_screen()
        base = URL.rsplit("/", 1)[0]
        index_url = base + "/0000000001-26-000001-index.htm"
        html = b"""<html><body><table>
            <tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th></tr>
            <tr><td>1</td><td>Current report with disclosures</td><td><a href="form.htm">form.htm</a></td><td>8-K</td></tr>
            <tr><td>2</td><td>Contract agreement</td><td><a href="ex10.htm">ex10.htm</a></td><td>EX-10.1</td></tr>
            <tr><td>3</td><td>Press release</td><td><a href="release.htm">release.htm</a></td><td>EX-99.1</td></tr>
            </table></body></html>"""
        fetcher = SimpleNamespace(get=lambda url: prototype.RawDocument(url, html))
        rows, warnings = summary.frozen.filing_documents(prototype, fetcher, index_url)
        self.assertFalse(warnings)
        self.assertEqual(dict(rows), {base + "/form.htm": "8-K", URL: "EX-10.1", base + "/release.htm": "EX-99.1"})
        self.assertEqual(summary.frozen.filing_documents(prototype, fetcher, base + "/release.htm"),
                         ([(base + "/release.htm", "EX-99.1")], []))

    def test_opt_in_title_filter_keeps_unknown_and_excludes_known_nonmatches(self):
        names = ("agreement", "warrant", "unknown", "press", "royalty", "technology", "trademark", "brand")
        kinds = ("EX-4.31", "EX-4.8", "EX-10.1", "EX-99.1", "EX-4.1", "EX-4.2", "EX-4.3", "EX-4.4")
        titles = ("License Agreement", "Common Stock Warrant", "EXHIBIT 10.1", "Press Release",
                  "Royalty", "Technology", "Trademark", "Brand Name")
        candidates = [dict(hit(URL.replace("ex10", name), kind), file_description=title)
                      for name, kind, title in zip(names, kinds, titles)]
        fetcher = SimpleNamespace(get=lambda url: SimpleNamespace(
            url=url, body=b"<html><body><p>Exhibit 10.1</p></body></html>", issue=None))
        with (
            patch.object(summary, "sec_user_agent", return_value="test"),
            patch.object(summary, "SECClient"),
            patch.object(summary.frozen, "load_screen", return_value=SimpleNamespace(Fetcher=lambda _: fetcher)),
            patch.object(summary.frozen, "screen_document", side_effect=frozen_keep) as frozen_screen,
            patch.object(summary, "discover", return_value=candidates),
            patch.object(summary, "prepare") as prepare,
            patch.object(summary, "read") as reader,
        ):
            self.assertEqual(summary.batch(date(2026, 1, 1), date(2026, 1, 31), 10, output_root=self.root,
                                           exhibits=summary.exhibit_prefixes("ex-10, EX-4"),
                                           contract_title_only=True), 0)
            self.assertEqual(frozen_screen.call_count, 6)
            self.assertEqual(prepare.call_count, 6)
            reader.assert_not_called()
        path, = self.root.glob("*/screening_log.json")
        rows = {Path(row["source_url"]).stem: row for row in read_json(path)["documents"]}
        self.assertEqual(rows["agreement"]["title"], "License Agreement")
        self.assertEqual(rows["warrant"]["decision"], "EXCLUDED_NOT_CONTRACT_TITLE")
        self.assertEqual(rows["warrant"]["title"], "Common Stock Warrant")
        self.assertEqual(rows["unknown"]["decision"], "KEEP")
        self.assertEqual(rows["unknown"]["title_status"], "TITLE_UNKNOWN")
        self.assertIn("TITLE_UNKNOWN", rows["unknown"]["flags"])
        self.assertEqual(rows["press"]["decision"], "EXCLUDED")
        for name, title in zip(names[-4:], titles[-4:]):
            with self.subTest(title=title):
                self.assertEqual(rows[name]["title"], title)
                self.assertEqual(rows[name]["decision"], "KEEP")

    def test_new_title_keywords_are_recognized_in_source_only_when_enabled(self):
        for title in ("Royalty", "Technology", "Trademark", "Brand Name"):
            with self.subTest(title=title):
                document = SimpleNamespace(url=URL, issue=None, body=f"<h1>{title}</h1>".encode())
                self.assertEqual(summary.candidate_title(document, "", contract_title_only=True), title)
                self.assertEqual(summary.candidate_title(document, ""), "")
        document = SimpleNamespace(url=URL, issue=None,
                                   body=b"<p>Example Royalties Corporation</p><h1>Credit Facilities</h1>")
        self.assertEqual(summary.candidate_title(document, "", contract_title_only=True), "Credit Facilities")

    def test_exhibit_prefixes_match_number_families(self):
        prefixes = summary.exhibit_prefixes("EX-10, EX-4,424b2")
        for kind in ("EX-10", "EX-10.1", "EX-4.31", "424B2"):
            self.assertTrue(summary.matches_exhibit(kind, prefixes))
        for kind in ("EX-101.INS", "EX-40", "EX-99.1", "424B3"):
            self.assertFalse(summary.matches_exhibit(kind, prefixes))

    def test_candidate_title_checks_source_when_sec_description_is_shorthand(self):
        document = SimpleNamespace(url=URL, issue=None,
                                   body=b"<p>Information contained in this exhibit has been excluded.</p>"
                                        b"<p>EXAMPLE COMPANY, as Parent</p>"
                                        b"<h1>Trust and Servicing Agreement</h1>")
        self.assertEqual(summary.candidate_title(document, "Series 2026 TSA"), "Trust and Servicing Agreement")
        document.body = b"<p>EXAMPLE COMPANY, as Parent</p>"
        self.assertEqual(summary.candidate_title(document, ""), "")

    def test_exclusions_require_execution_and_exact_version(self):
        for execute, version in ((False, screen.SCREEN_VERSION), (True, "royalty-screen.stale")):
            with self.subTest(execute=execute, version=version), patch.object(summary, "discover") as discover:
                with self.assertRaisesRegex(ValueError, "Exclusions require"):
                    summary.batch(date(2026, 11, 16), date(2026, 11, 16), 1, execute=execute,
                                  exclude_royalty_screen=version)
                discover.assert_not_called()

    def test_reader_error_preserves_partial_workbook_name(self):
        other = URL.replace("ex10.htm", "ex11.htm")
        with (
            patch.object(summary, "sec_user_agent", return_value="test"),
            patch.object(summary, "SECClient"),
            patch.object(summary.frozen, "load_screen", return_value=stub_frozen_source(b"source")),
            patch.object(summary.frozen, "screen_document", side_effect=frozen_keep),
            patch.object(summary, "discover", return_value=[hit(URL), hit(other)]),
            patch.object(summary, "candidate_rank", return_value=0),
            patch.object(summary.tempfile, "mkdtemp", return_value=str(self.root)),
            patch.object(summary, "prepare"),
            patch.object(summary, "read", side_effect=[None, RuntimeError("reader unavailable")]),
            patch.object(summary, "write_workbook") as workbook,
        ):
            self.assertEqual(summary.batch(date(2026, 11, 16), date(2026, 11, 16), 2, execute=True), 1)
            workbook.assert_called_once_with([self.root / "exhibit-001"],
                                             self.root / "Royalty_Agreement_Summary_partial.xlsx")

    def test_readable_reviews_export_without_changing_screen_decisions(self):
        raw = ("<html><body><p>License Agreement</p><p>" + PADDING
               + REDACTED + "</p><p>Final source clause.</p></body></html>").encode()
        cases = {
            "review": ("REVIEW", [], "REVIEW_SOURCE_OR_RATE_UNCERTAIN", "Royalty scope needs confirmation"),
            "mismatch": ("REVIEW", ["pointer_mismatch"], "DISCLOSED_CONTRACTUAL_RATE", ""),
            "unreadable": ("REVIEW", ["unreadable_source", "pointer_uncheckable"], "DISCLOSED_CONTRACTUAL_RATE",
                           "Missing text"),
            "fetch": ("REVIEW", ["unreadable_source"], "REVIEW_FETCH_FAILURE", ""),
            "keep": ("KEEP", ["pointer_ok"], "DISCLOSED_CONTRACTUAL_RATE", ""),
            "skip": ("SKIP", [], "REDACTED_NUMERICAL_RATE", ""),
        }
        urls = {key: URL.replace("ex10.htm", f"{key}.htm") for key in cases}

        def fetch(url):
            issue = SimpleNamespace(detail="HTTP 504", reason="REVIEW_FETCH_FAILURE") if url == urls["fetch"] else None
            return SimpleNamespace(url=url, body=b"" if issue else raw, issue=issue)

        def decision(_, document, number):
            key = Path(document.url).stem
            outcome, flags, reason, caveat = cases[key]
            return dict(source_url=document.url, decision=outcome,
                        prescreen_decision="KEEP" if key in {"mismatch", "unreadable"} else outcome,
                        prescreen_reason=reason, prescreen_caveat=caveat, flags=flags,
                        captured_rate_text="99%", captured_excerpt="Screener excerpt",
                        evidence_pointer=f"{document.url} # block 3", extractor_status="not_sent")

        agreement = {key: "" for _, key, _ in summary.COLUMNS if key not in {"industry", "source_url"}}
        agreement.update(title="Mock agreement", source_type="Agreement", transaction_type="Licence",
                         gics_code="Not stated", royalty_rate_percent="Undisclosed", royalty_basis="Net Sales",
                         royalty_structure="Not stated", exclusivity="Not stated")
        sent = {}

        def mock_reader(command, **kwargs):
            destination = Path(command[command.index("--output-last-message") + 1])
            prompt = kwargs["input"]
            meta = read_json(destination.parent / "prepared.json")
            key = Path(meta["source_url"]).stem
            sent[key] = prompt
            response = dict(agreement, title=key, other_material_conditions="Existing contract details.")
            if key == "review":
                response["other_material_conditions"] = "Preserve these contract details. " * 180
            destination.write_text(json.dumps({"agreements": [response]}))
            return SimpleNamespace(returncode=0)

        with (
            patch.object(summary, "sec_user_agent", return_value="test"),
            patch.object(summary, "SECClient"),
            patch.object(summary, "discover", return_value=[hit(url) for url in urls.values()]),
            patch.object(summary, "candidate_rank", return_value=0),
            patch.object(summary.frozen, "load_screen",
                         return_value=SimpleNamespace(FETCH_FAILURE="REVIEW_FETCH_FAILURE",
                                                      Fetcher=lambda _: SimpleNamespace(get=fetch))),
            patch.object(summary.frozen, "screen_document", side_effect=decision),
            patch.object(summary.frozen, "verified_sources"),
            patch.object(summary, "gics_names", return_value={}),
            patch.object(summary, "_preflight_subscription"),
            patch.object(summary.shutil, "which", return_value="/codex"),
            patch.object(summary.subprocess, "run", side_effect=mock_reader),
        ):
            gics = self.root / "reference.xlsx"
            gics.write_bytes(b"stub")
            self.assertEqual(summary.batch(date(2026, 11, 16), date(2026, 11, 16), 6, execute=True,
                                           gics_reference=gics, output_root=self.root), 0)
        root, = self.root.glob("runs_summary_*")
        self.assertEqual(set(sent), {"review", "mismatch", "keep"})
        self.assertTrue(sent["mismatch"].startswith(summary.REVIEW_INSTRUCTIONS))
        stored = (root / "exhibit-002" / "prompt.txt").read_text()
        self.assertEqual(sent["mismatch"], summary.REVIEW_INSTRUCTIONS + stored)
        self.assertIn(REDACTED, stored)
        self.assertIn("Final source clause.", stored)
        self.assertNotIn("99%", sent["mismatch"])
        self.assertNotIn(summary.REVIEW_INSTRUCTIONS, sent["keep"])

        log = read_json(root / "screening_log.json")
        records = {Path(r["source_url"]).stem: r for r in log["documents"]}
        for key, (outcome, flags, _, _) in cases.items():
            self.assertEqual((records[key]["decision"], records[key]["flags"]), (outcome, flags))
        self.assertEqual(records["review"]["prescreen_reason"], "REVIEW_SOURCE_OR_RATE_UNCERTAIN")
        self.assertEqual(records["mismatch"]["evidence_pointer"], f'{urls["mismatch"]} # block 3')
        self.assertEqual(records["mismatch"]["captured_excerpt"], "Screener excerpt")
        self.assertEqual(records["fetch"]["error"], "HTTP 504")
        for key in {"unreadable", "fetch", "skip"}:
            self.assertEqual(records[key]["extractor_status"], "not_sent")
        for key in {"review", "mismatch"}:
            self.assertEqual(records[key]["extractor_status"], "completed")

        workbook = load_workbook(log["workbook"])
        self.assertEqual(workbook.sheetnames, ["Agreement Summary"])
        sheet = workbook.active
        self.assertEqual((sheet.max_row, sheet.max_column), (4, 16))
        self.assertEqual(tuple(c.value for c in sheet[1]), tuple(heading for heading, _, _ in summary.COLUMNS))
        for row, title in zip(range(2, 5), ("review", "mismatch", "keep")):
            self.assertEqual(sheet.cell(row, 1).value, title)
            self.assertEqual(sheet.cell(row, 8).value, "Undisclosed")
        self.assertIn("PENDING HUMAN REVIEW — REVIEW_SOURCE_OR_RATE_UNCERTAIN", sheet["O2"].value)
        self.assertIn("Preserve these contract details. " * 179, sheet["O2"].comment.text)
        self.assertTrue(sheet["O3"].value.startswith("Existing contract details.\n"))
        self.assertIn("PENDING HUMAN REVIEW — pointer_mismatch", sheet["O3"].value)
        self.assertEqual(sheet["O4"].value, "Existing contract details.")

    def test_malformed_html_recovery_with_saved_and_synthetic_sources(self):
        prototype = summary.frozen.load_screen()
        title = "<h1>Patent Licence and Royalty Agreement</h1>"
        clauses = (
            "<p>This Agreement is made between Example Licensor and Example Licensee for the use of patented devices.</p>"
            "<p>Licensor hereby grants Licensee an exclusive licence to manufacture and sell the patented devices.</p>"
            "<p>Licensee shall pay a royalty of [***]% of Net Sales under the licence for each accounted period.</p>"
            "<p>The parties shall retain royalty records for inspection following termination of this Agreement.</p>"
        )
        body = "<html><body>" + title + clauses
        recovered = (body + "</body>").encode()
        test_sources = {
            "recoverable": (recovered, None),
            "empty": (b"", None),
            "snippet": (("<html><body>" + title + "<p>Royalty rate: 8%.</p></body>").encode(), None),
            "binary": (b"\xff\xd8\x00" + recovered, None),
            "denied": (("<html><head><title>503 Service Unavailable</title></head><body>"
                        + title + clauses * 12 + "</body>").encode(), None),
            "truncated": ((body + "<p>[DOCUMENT TRUNCATED]</p></body>").encode(), None),
            "cutoff": ((body + "<p>Licensee shall provide a final report to").encode(), None),
            "open_wrapper": (b"<DOCUMENT><TEXT>" + recovered, None),
            "hidden": ((body + "<script>unfinished</body>").encode(), None),
            "partial_http": (recovered, prototype.SourceIssue(prototype.UNREADABLE, "HTTP partial content")),
            "fetch": (b"", prototype.SourceIssue(prototype.FETCH_FAILURE, "HTTP 504")),
            "former_gate": ((body.replace(title, "<h1>Asset Purchase Agreement</h1>")
                             .replace("[***]%", "7%") + "</body></html>").encode(), None),
            "oversized": ((body + clauses * 900 + "</body>").encode(), None),
        }
        urls = {key: URL.replace("ex10.htm", f"{key}.htm") for key in test_sources}
        historical = (Path(__file__).resolve().parents[1]
                      / "runs_summary_2024-06-01_2024-06-30_152435_j6b_9o0n")
        original = historical / "exhibit-012" / "source.htm"
        reference = summary.SAVED_GICS
        if original.is_file():
            meta = read_json(original.with_name("prepared.json"))
            urls["saved_rmed"] = meta["source_url"]
            test_sources["saved_rmed"] = (original.read_bytes(), None)
            self.assertEqual(sha256(test_sources["saved_rmed"][0]), meta["source_sha256"])
            reference = original.with_name("gics_reference.xlsx")
            print(f"Saved rmed original: {len(test_sources['saved_rmed'][0])} bytes, SHA-256 {meta['source_sha256']}")
        else:
            print("Saved rmed original unavailable. Cases below use synthetic sources.")

        keys = {url: key for key, url in urls.items()}
        documents = {url: prototype.RawDocument(url, *test_sources[key]) for url, key in keys.items()}
        former_gate_raw = test_sources["former_gate"][0]
        paragraphs, parser = summary.parse_document(former_gate_raw, "former_gate.htm")
        mapping = map_contract(paragraphs, {"document_id": "DOC-TEST", "source_url": urls["former_gate"]},
                               raw_hash=sha256(former_gate_raw), parser_type=parser)
        self.assertFalse(licence_gate(mapping)["passed"])
        original_rows = {}
        screen_document = summary.frozen.screen_document

        def capture_decision(reader, document, number):
            row = screen_document(reader, document, number)
            if keys[document.url] == "recoverable":
                self.assertEqual(row["decision"], "REVIEW")
                row.update(captured_rate_text="99.99%", captured_excerpt="Seeded false rate: 99.99%",
                           evidence_pointer=f"{document.url} # block 1")
            original_rows[keys[document.url]] = row.copy()
            return row

        sent = {}
        conditions = "Preserve these mock contract details. " * 180

        def mock_reader(command, **kwargs):
            destination = Path(command[command.index("--output-last-message") + 1])
            meta = read_json(destination.parent / "prepared.json")
            key = keys[meta["source_url"]]
            sent[key] = kwargs["input"]
            agreement = {field: "" for _, field, _ in summary.COLUMNS
                         if field not in {"industry", "source_url"}}
            agreement.update(title=f"Mock output for {key}", source_type="Agreement", transaction_type="Licence",
                             gics_code="Not stated", royalty_rate_percent="Undisclosed", royalty_basis="Net Sales",
                             royalty_structure="Not stated", exclusivity="Not stated", other_material_conditions=conditions)
            destination.write_text(json.dumps({"agreements": [agreement]}), encoding="utf-8")
            return SimpleNamespace(returncode=0)

        with (
            patch.object(summary, "sec_user_agent", return_value="local-evidence-test"),
            patch.object(summary, "SECClient"),
            patch.object(summary, "discover", return_value=[hit(url) for url in urls.values()]),
            patch.object(summary, "candidate_rank", return_value=0),
            patch.object(prototype.Fetcher, "get", side_effect=documents.__getitem__),
            patch.object(summary.frozen, "screen_document", side_effect=capture_decision),
            patch.object(summary, "download_gics", side_effect=AssertionError("No network allowed")),
            patch.object(summary, "_preflight_subscription"),
            patch.object(summary.shutil, "which", return_value="/mock-codex"),
            patch.object(summary.subprocess, "run", side_effect=mock_reader),
        ):
            if not reference.is_file():
                from openpyxl import Workbook

                reference = self.root / "mock_gics.xlsx"
                workbook = Workbook()
                workbook.active.title = summary.GICS_SHEET
                workbook.save(reference)
            self.assertEqual(summary.batch(date(2024, 6, 1), date(2024, 6, 30), len(urls), execute=True,
                                           gics_reference=reference, output_root=self.root), 0)

        root, = self.root.glob("runs_summary_*")
        log = read_json(root / "screening_log.json")
        rows = {keys[row["source_url"]]: row for row in log["documents"]}
        recovered = {"recoverable"} | ({"saved_rmed"} if original.is_file() else set())
        expected = recovered | {"former_gate"}
        self.assertEqual(set(sent), expected)
        self.assertEqual(set(rows), set(urls))
        self.assertEqual(log["sha256_before"], log["sha256_after"])
        for key, row in rows.items():
            with self.subTest(source=key):
                if key in original_rows and key not in {"oversized", "empty", "hidden", "partial_http", "fetch", "binary"}:
                    for field, value in original_rows[key].items():
                        if field != "extractor_status":
                            self.assertEqual(row[field], value)
                if key in recovered:
                    self.assertEqual(row["decision"], "REVIEW")
                    self.assertIn("unreadable_source", row["flags"])
                    self.assertEqual(row["html_recovery"]["result"], "eligible")
                    self.assertEqual(row["extractor_status"], "completed")
                elif key != "former_gate":
                    self.assertEqual(row["extractor_status"], "not_sent")
                    self.assertTrue(row.get("error") or row["html_recovery"]["reason"])
        self.assertIn("above the current CLI bound", rows["oversized"]["error"])
        self.assertEqual(rows["former_gate"]["decision"], "KEEP")
        self.assertEqual(rows["former_gate"]["extractor_status"], "completed")
        self.assertEqual(rows["oversized"]["decision"], "REVIEW")
        self.assertIn("source_too_large", rows["oversized"]["flags"])
        self.assertEqual(rows["oversized"]["prescreen_decision"], original_rows["oversized"]["prescreen_decision"])
        self.assertEqual(rows["fetch"]["error"], "HTTP 504")
        self.assertEqual(rows["recoverable"]["captured_rate_text"], "99.99%")
        self.assertNotIn("99.99%", sent["recoverable"])
        self.assertIn("a royalty of [***]% of Net Sales", sent["recoverable"])
        if "saved_rmed" in expected:
            previous = next(row for row in read_json(historical / "screening_log.json")["documents"]
                            if row["source_url"] == urls["saved_rmed"])
            for field in ("decision", "prescreen_decision", "flags", "prescreen_reason", "prescreen_flags",
                          "source_issue", "captured_rate_text", "captured_excerpt", "evidence_pointer"):
                self.assertEqual(rows["saved_rmed"][field], previous[field])

        workbook = load_workbook(log["workbook"])
        self.assertEqual(workbook.sheetnames, ["Agreement Summary"])
        sheet = workbook.active
        self.assertEqual((sheet.max_row, sheet.max_column), (1 + len(expected), 16))
        self.assertEqual(tuple(cell.value for cell in sheet[1]), tuple(name for name, _, _ in summary.COLUMNS))
        for row_number in range(2, sheet.max_row + 1):
            key = sheet.cell(row_number, 1).value.removeprefix("Mock output for ")
            prompt = sent[key]
            if key == "former_gate":
                self.assertNotIn("PENDING HUMAN REVIEW", sheet.cell(row_number, 15).value)
                continue
            self.assertTrue(prompt.startswith(summary.REVIEW_INSTRUCTIONS))
            self.assertIn(summary.RECOVERY_CAVEAT, prompt)
            supplied = prompt.split("\n\nSEC EXHIBIT TEXT\n\n", 1)[1]
            supplied = [line.split("] ", 1)[1] for line in supplied.splitlines() if line]
            paragraphs, _ = summary.parse_document(test_sources[key][0], Path(urls[key]).name)
            self.assertEqual(supplied, paragraphs)
            cell = sheet.cell(row_number, 15)
            visible = " ".join(cell.value.split())
            self.assertIn("PENDING HUMAN REVIEW", visible)
            self.assertIn("HTML root has no closing tag", visible)
            self.assertIn(summary.RECOVERY_CAVEAT, visible)
            self.assertIn(conditions.strip(), cell.comment.text)
            self.assertEqual(sheet.cell(row_number, 8).value, "Undisclosed")
            self.assertEqual(sheet.cell(row_number, 16).hyperlink.target, urls[key])
        workbook.close()
        print("Verified workbook headers, REVIEW reasons and caveats, overflow notes, and source hyperlinks.")
        print("Mock reader received every extracted passage for: " + ", ".join(sorted(expected)))
