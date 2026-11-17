"""Loss-aware HTML/TXT/PDF text extraction for contract mapping.

Text output is not an assertion of completeness. Unreadable/unsupported files
must be rejected explicitly and never classified as royalty-free.
"""
from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser


class ParseError(ValueError):
    pass


class UnsupportedDocument(ParseError):
    pass


class _HTMLToParagraphs(HTMLParser):
    """HTML to passages.

    Review fixes RF-02 (v0.5.1-review), found on real SEC exhibits:
    * Line breaks inside an HTML text node are insignificant whitespace. v0.5.0 kept
      them as passage boundaries, so one clause was cut into arbitrary line fragments
      (Market Finders s.4.2: the 4% rate and its $500,000-$2,500,000 band landed in
      different passages). They are now collapsed to a single space, except in <pre>.
    * A table data row is emitted as ONE passage ("cell | cell | cell") even when its
      cells contain <p>/<div>/<br>. v0.5.0 emitted every cell as its own passage, which
      separated a tier rate from its threshold (NeurogesX 25% / < $250,000) and produced
      passages too short to quote. Rows that look like page layout (one text cell, or
      long multi-paragraph cells) keep their paragraph breaks.
    """
    BLOCK = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6",
             "table", "tr", "ul", "ol", "li", "blockquote", "br", "hr", "center",
             "dl", "dt", "dd", "pre", "title", "caption", "thead", "tbody", "tfoot"}
    EXCLUDE = {"script", "style", "svg", "noscript", "head"}
    PREFIX_ONLY = frozenset({"$", "US$", "U.S.$", "HK$", "C$", "A$", "S$", "€", "£", "¥", "(", "($", "(US$"})
    SUFFIX_ONLY = frozenset({"%", ")", "%)", "%;", "%,", "%."})
    ROW_MAX_CHARS = 2000      # a merged data row longer than this is treated as layout
    CELL_MAX_LINES = 4        # a cell with more block lines than this is treated as layout

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []          # top-level output
        self.ignore_depth = 0
        self.pre_depth = 0
        self.rows = []            # stack of open <tr>: {"cells": [[line,...],...], "cur": [str,...]}

    # -- output routing -------------------------------------------------
    def _emit(self, text):
        if self.rows:
            self.rows[-1]["cur"].append(text)
        else:
            self.chunks.append(text)

    def _newline(self):
        if not self.ignore_depth:
            self._emit("\n")

    def _close_cell(self, row):
        text = "".join(row["cur"])
        row["cur"] = []
        lines = [re.sub(r"[\t \u00a0]+", " ", ln).strip() for ln in text.split("\n")]
        row["cells"].append([ln for ln in lines if ln])

    def _close_row(self):
        row = self.rows.pop()
        if row["cur"]:
            self._close_cell(row)
        cells = [c for c in row["cells"] if c]
        # SEC tables routinely put the currency sign or the percent sign in its own cell
        # ("$" | "50,000.00", "25" | "%"). Glue such symbol-only cells to their value so that
        # "$50,000.00" and "25%" stay recognisable amounts instead of "$ | 50,000.00".
        glued = []
        pending_prefix = ""
        for c in cells:
            text = " ".join(c)
            if text in self.PREFIX_ONLY:
                pending_prefix += text
                continue
            if text in self.SUFFIX_ONLY and pending_prefix:
                glued.append([pending_prefix]); pending_prefix = ""     # blank form cells: keep order
            if text in self.SUFFIX_ONLY and glued:
                glued[-1] = [glued[-1][0] + text] if len(glued[-1]) == 1 else glued[-1][:-1] + [glued[-1][-1] + text]
                continue
            if pending_prefix:
                c = [pending_prefix + c[0]] + c[1:]
                pending_prefix = ""
            glued.append(c)
        if pending_prefix:
            glued.append([pending_prefix])
        cells = glued
        merged = " | ".join(" ".join(c) for c in cells)
        is_data_row = (len(cells) >= 2 and len(merged) <= self.ROW_MAX_CHARS
                       and all(len(c) <= self.CELL_MAX_LINES for c in cells))
        out = merged if is_data_row else "\n".join(ln for c in cells for ln in c)
        self._emit("\n" + out + "\n")

    # -- parser callbacks -----------------------------------------------
    def handle_starttag(self, tag, attrs):
        if tag in self.EXCLUDE:
            self.ignore_depth += 1
            return
        if self.ignore_depth:
            return
        if tag == "pre":
            self.pre_depth += 1
        if tag == "tr":
            self._newline()
            self.rows.append({"cells": [], "cur": []})
        elif tag in {"td", "th"}:
            if self.rows and (self.rows[-1]["cur"]):
                self._close_cell(self.rows[-1])
        elif tag in self.BLOCK:
            self._newline()

    def handle_startendtag(self, tag, attrs):
        if not self.ignore_depth and tag in self.BLOCK:
            self._newline()

    def handle_endtag(self, tag):
        if tag in self.EXCLUDE:
            if self.ignore_depth:
                self.ignore_depth -= 1
            return
        if self.ignore_depth:
            return
        if tag == "pre" and self.pre_depth:
            self.pre_depth -= 1
        if tag == "tr":
            if self.rows:
                self._close_row()
        elif tag in {"td", "th"}:
            if self.rows:
                self._close_cell(self.rows[-1])
        elif tag == "table":
            self._newline()
        elif tag in self.BLOCK:
            self._newline()

    def handle_data(self, data):
        if self.ignore_depth:
            return
        if not self.pre_depth:
            data = re.sub(r"[\r\n\t\f\v ]+", " ", data)
        self._emit(data)

    def close(self):
        super().close()
        while self.rows:          # unclosed <tr> at end of document: never drop its text
            self._close_row()


def decode_bytes(raw: bytes) -> str:
    # SEC contracts often contain legacy encodings; do not silently replace bytes.
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ParseError("Unable to decode document without data loss")


def extract_sgml_text(text: str) -> str:
    """For a single SEC exhibit wrapped in <DOCUMENT>; complete submissions are refused."""
    matches = list(re.finditer(r"<DOCUMENT>\s*(.*?)\s*</DOCUMENT>", text, re.I | re.S))
    if not matches:
        return text
    if len(matches) != 1:
        raise UnsupportedDocument("Multi-document SEC submissions require inventory-level separation")
    doc = matches[0].group(1)
    m = re.search(r"<TEXT>\s*(.*?)\s*</TEXT>", doc, re.I | re.S)
    if not m:
        raise ParseError("SEC SGML document lacks <TEXT> payload")
    return m.group(1)


def text_to_paragraphs(text: str, is_html: bool) -> list[str]:
    if is_html:
        parser = _HTMLToParagraphs()
        parser.feed(text)
        parser.close()
        # A truncated HTML <script>/<style>/<head> block can otherwise hide
        # all following contract clauses while appearing like a valid parse.
        if parser.ignore_depth:
            raise ParseError("Unclosed ignored HTML section; source completeness not established")
        text = "".join(parser.chunks)
    else:
        text = unescape(text)
    # Preserve line breaks and table rows, normalize within lines only.
    lines = [re.sub(r"[\t \u00a0]+", " ", line).strip() for line in text.splitlines()]
    # Some original formatting is line-wrapped; keep it instead of silently joining clauses.
    chunks = [line for line in lines if line]
    if not chunks:
        raise ParseError("No readable text found")
    return chunks


def parse_document(raw: bytes, filename: str) -> tuple[list[str], str]:
    ext = filename.lower().rsplit(".", 1)[-1]
    if raw.startswith(b"%PDF-") or ext == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise UnsupportedDocument("PDF requires optional dependency: pip install '.[pdf]'") from exc
        import io
        try:
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                raise UnsupportedDocument("Encrypted PDF requires explicit review")
            pages = []
            for page_no, page in enumerate(reader.pages, 1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    pages.extend([f"[PDF PAGE {page_no}]"] + text_to_paragraphs(page_text, False))
                else:
                    pages.append(f"[PDF PAGE {page_no}: NO EXTRACTABLE TEXT — REVIEW REQUIRED]")
        except UnsupportedDocument:
            raise
        except Exception as exc:
            raise UnsupportedDocument(f"PDF could not be fully parsed: {type(exc).__name__}: {exc}") from exc
        if not pages or not any("NO EXTRACTABLE" not in s and not s.startswith("[PDF PAGE") for s in pages):
            raise UnsupportedDocument("Image-only or empty PDF; manual/OCR review required")
        if any("NO EXTRACTABLE" in s for s in pages):
            raise UnsupportedDocument("One or more PDF pages unreadable; no partial silent approval")
        return pages, "PDF_TEXT"
    if ext not in {"htm", "html", "txt", "xml"}:
        raise UnsupportedDocument(f"Unsupported file extension: {ext}")
    decoded = extract_sgml_text(decode_bytes(raw))
    looks_html = ext in {"htm", "html", "xml"} or bool(re.search(r"<(?:html|body|p|div|table|font)\b", decoded[:10000], re.I))
    return text_to_paragraphs(decoded, looks_html), "HTML_TEXT" if looks_html else "PLAIN_TEXT"
