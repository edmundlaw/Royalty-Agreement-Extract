"""Synthetic screen regressions and isolated summary-route integration."""
import contextlib
from datetime import date
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from royalty_research import agreement_summary as summary
from royalty_research import royalty_screen as screen
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
                    patch.object(summary, "discover", return_value=[{"source_url": URL}]),
                    patch.object(summary, "licence_gate", return_value={"passed": True}),
                    patch.object(summary, "triage_document", return_value={"priority": "HIGH"}),
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
        with (
            patch.object(summary, "sec_user_agent", return_value="test"),
            patch.object(summary, "SECClient"),
            patch.object(summary.frozen, "load_screen",
                         return_value=stub_frozen_source(b"<html><body></body></html>")),
            patch.object(summary, "discover", return_value=[{"source_url": URL}]),
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
            patch.object(summary, "discover", return_value=[{"source_url": URL}, {"source_url": other}]),
            patch.object(summary, "candidate_rank", return_value=0),
            patch.object(summary.tempfile, "mkdtemp", return_value=str(self.root)),
            patch.object(summary, "prepare"),
            patch.object(summary, "read", side_effect=[None, RuntimeError("reader unavailable")]),
            patch.object(summary, "write_workbook") as workbook,
        ):
            self.assertEqual(summary.batch(date(2026, 11, 16), date(2026, 11, 16), 2, execute=True), 1)
            workbook.assert_called_once_with([self.root / "exhibit-001"],
                                             self.root / "Royalty_Agreement_Summary_partial.xlsx")
