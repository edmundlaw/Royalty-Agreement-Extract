"""Deterministic exhibit screening with verified audit records."""
from __future__ import annotations

import re
import sys

from .storage import atomic_bytes, atomic_json, read_json, sha256, utc_now

SCREEN_VERSION = "royalty-screen.4"
MIN_SOURCE_CHARS = 2000

PERCENT = r"(?:%|percent\b|per cent\b)"
CURRENCY = r"(?:U\.?S\.?\s*\$|(?:HK|CA|AU|C|A)?\$|€|£|¥|(?:USD|EUR|GBP|CAD|AUD)\b)"
NUMBER = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)"
WORDS = (r"(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
         r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|"
         r"forty|fifty|sixty|seventy|eighty|ninety|hundred)")
SPELLED = (rf"(?:{WORDS}(?:[- ]{WORDS})*|(?:{WORDS}[- ])?"
           r"(?:half|quarter|third|fourth|fifth|eighth|tenth|twentieth|hundredth)s?"
           r"(?: of one)?|half of one)")
QUALITATIVE = r"(?:(?:low|mid|high)[- ]+single|(?:low[- ]+|mid[- ]+|high[- ]+)?double)[- ]+digits?"
RATE = (rf"(?<![\w.])(?:(?:{NUMBER}(?:\s*[-–—]\s*{NUMBER})?|\d+/\d+|{SPELLED})\s*{PERCENT}"
        rf"|(?:{NUMBER}|{SPELLED})\s*(?:basis points?\b|bps\b)|{QUALITATIVE}\b)")
MONEY = rf"(?:{CURRENCY}\s*{NUMBER}(?:\s+(?:million|billion|thousand)\b)?|{NUMBER}\s+cents?\b)"
BRACKET = rf"(?:\[\s*(?:\*{{1,3}}|REDACTED)\s*(?:{PERCENT})?\s*\]|\{{\s*\*{{3}}\s*(?:{PERCENT})?\s*\}})"
MARKER = rf"(?<![\[{{*])(?:{BRACKET}|\*{{2,3}}(?![*\]}}]))"
REDACTED = rf"(?:{CURRENCY}\s*)?{MARKER}(?:\s*{PERCENT}(?:\s*{BRACKET})?)?"
ROYALTY = r"royalt(?:y|ies)"
LABEL = (r"(?:(?:running|earned|sales(?:[- ]based)?|tiered|base)\s+)?royalty\s+rates?"
         r"|(?:running|earned|sales(?:[- ]based)?)\s+royalt(?:y|ies)")
SUB = (r"(?:(?:non[- ]royalty\s+)?sub[- ]?licen[sc](?:e|ing)\s+"
       r"(?:income|consideration|fees?|revenue|proceeds|receipts|payments?))")
UNIT = (r"(?:units?|products?|devices?|buildings?|tonnes?|(?:metric )?tons?|kilograms?|kg|"
        r"barrels?|cubic met(?:re|er)s?|lit(?:re|er)s?|copies|transactions?|downloads?|"
        r"pounds?|ounces?|square (?:feet|met(?:re|er)s?)|MWh)\b")
BASE = (rf"(?:{SUB}|(?:(?:aggregate|adjusted|annual|gross|net|total|contract|licensed|"
        r"product|worldwide|actual)\s+)*(?:sales(?:\s+price)?|selling\s+price|"
        r"revenues?|income|proceeds|receipts|production(?:\s+volumes?)?|output|"
        r"volumes?|quantit(?:y|ies)\s+(?:extracted|produced|sold)|"
        r"amounts?\s+(?:received|realized)\s+(?:from|on)\s+(?:the\s+)?(?:sale|selling))\b"
        rf"|{UNIT}\s+(?:sold|manufactured|produced|extracted)\b)")
UNIT_BASIS = rf"(?:per|for each)\s+{UNIT}"
HEAD = (rf"(?:(?:percentage of )?{SUB}(?:\s+(?:share|payable to [\w -]+|received by [\w -]+))?|{LABEL}|"
        rf"(?:royalty|rate)\s+{UNIT_BASIS}|percentage of (?:net|gross) sales)")
NUMBERING = r"(?:\(?[a-z0-9]+(?:\.\d+)*[.)]\s*)?"
ASSIGN = r"""\s*["”')]*\s*(?:(?:[:=]|[–—])\s*|\s+(?:(?:shall be|will be|is|are|means|equals?|of|payable at|equal to|at)\s+){1,2})"""
OBLIGATION = (rf"\b(?:an?\s+)?(?:(?:running|earned|sales[- ]based|annual|minimum|perpetual|production|per[- ]unit)\s+)?"
              rf"{ROYALTY}\s+(?:(?:payable|payment|shall be|will be|is)\s+)?(?:of|equal to|at the rate of|at|calculated as)\s+")
RATE_ALIAS = rf"(?:\s*\(\s*{NUMBER}\s*{PERCENT}\s*\))?(?:\s*\(the [\"“]royalty rate[\"”]\))?"
RATE_END = r"(?![\w*]|\s*(?:\]|\}|million\b|billion\b|thousand\b))"
ROYALTY_BASE = rf"(?:of|on|on the basis of|in respect of|based on)\s+(?:the\s+)?(?:{BASE}|licensed products?\b|[\w’'-]+\s+(?:net|gross)\s+sales\b)"
ILLUSTRATIVE = re.compile(
    r"for (?:illustrative purposes|purposes of illustration|example only)|hypothetical|"
    r"sample (?:royalty )?(?:report|calculation)|(?:blank|form of) royalty report|"
    r"non[- ]binding (?:term sheet|proposal)|proposed (?:running )?royalty", re.I)
INLINE_EXAMPLE = re.compile(
    r"\b(?:by way of (?:an? )?example|for example[,]?\s+(?:if|assuming|suppose))\b", re.I)
MISSING = re.compile(
    r"\b(?:schedule|appendix|annex|attachment|exhibit)\b[^\n.;]{0,110}"
    r"\b(?:not (?:attached|included|provided|filed|reproduced|available)|"
    r"(?:has been |is |are )?omitted(?: pursuant to| from| herewith|[.;]|$)|missing)\b", re.I | re.M)
MISSING_ECONOMIC_ATTACHMENT = re.compile(
    rf"^\s*(?:schedule|appendix|annex|attachment|exhibit)\s+[\w-]+[^\n]*"
    rf"\n(?:[^\n]{{0,120}}\n)?[ \t·\u200b]*{BRACKET}[ \t\u200b]*$",
    re.I | re.M,
)
REFERENCE = re.compile(
    r"\b(?:royalty rates?|running royalties|earned royalties|royalty schedule)\b"
    r"[^\n.;]{0,140}?\b(?:set (?:out|forth)|specified|listed|provided|described|shown|stated)"
    r"\s+in\s+(?:the\s+)?(?P<ref>(?:schedule|appendix|annex|attachment|exhibit)\s+[\w-]+)",
    re.I)
ATTACHED_REFERENCE = re.compile(
    r"\battach(?:ed|ment)?\s+(?:hereto|herewith|to this agreement)\s+as\s+(?:the\s+)?"
    r"(?P<ref>(?:schedule|appendix|annex|attachment|exhibit)\s+[\w.-]+?)(?=[,;.:]?(?:\s|$))",
    re.I)
REJECTIONS = (
    ("CONTROL_THRESHOLD", r"voting (?:stock|securities|power|rights)|of the voting|(?:change of |common )control|equity ownership|equity securities"),
    ("LITIGATION_EXPENSE_OFFSET", r"litigation (?:costs?|expenses?)|offset (?:a total of )?|of any expenses incurred|(?:costs?|expenses?) of (?:the )?(?:litigation|suit)|(?:deduct|offset)\w*[^.;]{0,65}(?:expenses?|costs?)"),
    ("ROYALTY_ADJUSTMENT_CAP", r"(?:royalt\w+[^.;]{0,75}reduc\w+|reduc\w+[^.;]{0,75}royalt\w+)|(?:reduction|reduced) (?:by|of|to)"),
    ("PRODUCT_SPECIFICATION", r"concentration|purity|ingredient|percentage composition|(?:technical|product) specifications?|active substance|by weight"),
    ("EXISTING_STREAM_OWNERSHIP", r"(?:acquir\w+|assign\w+|purchas\w+|retain\w+|allocat\w+|sell\w*|buyer receives)[^.;]{0,100}\b(?:royalt\w+ (?:interests?|receipts?|stream|rights)|purchased (?:stream|royalt\w+))"),
    ("OTHER_NON_RATE_PERCENTAGE", r"late (?:payment|charge)|cost of the audit|audit performed|underpayment in excess of|interest (?:on|rate)|withholding tax|audit (?:cost|discrepancy)|insurance coverage|indemnification|royalty[- ]free"),
)
REJECTIONS = tuple((code, re.compile(pattern, re.I)) for code, pattern in REJECTIONS)


def pattern(expression):
    return re.compile(expression, re.I)


def rate_patterns(value):
    return (
        ("R1", pattern(rf"\b(?:{LABEL}){ASSIGN}(?P<value>{value}){RATE_END}")),
        ("R2", pattern(rf"{OBLIGATION}(?P<value>{value}){RATE_END}{RATE_ALIAS}\s+(?:{ROYALTY_BASE}|{UNIT_BASIS})")),
        ("R4", pattern(rf"\b{ROYALTY}\s+(?:is\s+|shall be\s+)?(?:payable|calculated|computed)"
                       rf"\s+(?:at|as|at the rate of)\s+(?P<value>{value}){RATE_END}\s+{ROYALTY_BASE}")),
        ("R6", pattern(rf"\b{ROYALTY}\s*(?:=|equals?\s+)(?P<value>\s*{value}){RATE_END}\s*(?:×|\*|x|times|multiplied by)\s*(?:the\s+)?{BASE}")),
        ("R6", pattern(rf"\b{BASE}\s*(?:×|\*|x|times|multiplied by)\s*(?P<value>{value}){RATE_END}\s*(?:=|equals?\s+)\s*{ROYALTY}\b")),
        ("R7", pattern(rf"\b(?:pay|remit|receive)\s+(?P<value>{value}){RATE_END}\s+{ROYALTY_BASE}"
                       rf"[^\n.;]{{0,110}}?\s+(?:as|in)\s+(?:an?\s+)?{ROYALTY}\b")),
        ("R8", pattern(rf"\b{SUB}(?:\s+(?:share|payable to (?:the )?(?:licensor|grantor)))?{ASSIGN}(?P<value>{value}){RATE_END}")),
        ("R8", pattern(rf"\b(?:pay|remit|receive|entitled to)\s+(?P<value>{value}){RATE_END}\s+of\s+(?:all\s+|the\s+)?{SUB}")),
        ("PER_UNIT", pattern(rf"(?:{OBLIGATION}|\b{LABEL}{ASSIGN})(?P<value>{value}){RATE_END}\s+{UNIT_BASIS}")),
        ("PER_UNIT", pattern(rf"\b(?:royalty|royalty rate)\s+{UNIT_BASIS}(?:\s+(?:sold|produced|extracted))?{ASSIGN}(?P<value>{value}){RATE_END}")),
    )


RED_RULES = rate_patterns(REDACTED)
KEEP_RULES = rate_patterns(rf"(?:{RATE}|{MONEY})") + (
    ("R2", pattern(rf"{OBLIGATION}(?P<value>{RATE})\s+(?:above|over|up to|in excess of)"
                   rf"\s+(?:{REDACTED}|{MONEY})\s+{ROYALTY_BASE}")),
    ("R4", pattern(rf"\b{ROYALTY}\s+(?:shall be|is|equals)\s+(?P<value>{RATE})\s+{ROYALTY_BASE}")),
    ("R6", pattern(rf"\b(?:{LABEL}|{ROYALTY})\s*(?:=|equals?\s+)(?P<value>\s*{NUMBER})"
                   rf"\s*(?:×|\*|x|times|multiplied by)\s*(?:the\s+)?{BASE}")),
    ("R6", pattern(rf"\b{BASE}\s*(?:×|\*|x|times|multiplied by)\s*(?P<value>{NUMBER})"
                   rf"\s*(?:=|equals?\s+)\s*{ROYALTY}\b")),
    ("ROYALTY_PASS_THROUGH", pattern(rf"(?P<value>{RATE})\s+of\s+(?:all\s+|the\s+)?royalties\s+received")),
    ("SUBLICENSE_SHARE", pattern(rf"(?P<value>\d{{1,3}}\s*[/–-]\s*\d{{1,3}}|equally)"
                                 rf"\s*(?:split|share|of)?\s*(?:of\s+)?{SUB}")),
    ("SUBLICENSE_SHARE", pattern(rf"{SUB}[^.;\n]{{0,45}}?\b(?:split|shared|divided)\s+"
                                 r"(?P<value>\d{1,3}\s*[/–-]\s*\d{1,3}|equally)")),
    ("MINIMUM_ROYALTY", pattern(rf"\b(?:minimum\s+(?:annual\s+|quarterly\s+)?royalt(?:y|ies)|"
                                rf"(?:annual|quarterly)\s+minimum\s+royalt(?:y|ies))(?:\s+payments?)?{ASSIGN}(?P<value>{MONEY})")),
    ("RECURRING_FEE", pattern(rf"\b(?:annual|quarterly|monthly|recurring)\s+(?:royalty|licen[sc]e fee)(?:\s+payments?)?{ASSIGN}(?P<value>{MONEY})")),
    ("RECURRING_FEE", pattern(rf"\b(?:royalty|licen[sc]e fee){ASSIGN}(?P<value>{MONEY})\s+(?:per (?:year|quarter|month)|annually|quarterly|monthly)")),
    ("MINIMUM_ROYALTY", pattern(rf"\b(?:royalty|royalties)\s+(?:payments?\s+)?(?:of\s+)?"
                                rf"(?:at least|no less than)\s+(?P<value>{MONEY})")),
    ("RECURRING_FEE", pattern(rf"\b(?:pay|remit)\s+(?P<value>{MONEY})\s+(?:per (?:year|quarter|month)|"
                               rf"annually|quarterly|monthly)\s+as\s+(?:an?\s+)?(?:royalty|licen[sc]e fee)")),
    ("ROYALTY_CREATION", pattern(rf"\b(?:hereby grants?|reserves?|creates?|establishes?)\s+(?:an?\s+)?"
                                 rf"(?:perpetual\s+)?royalty\s+(?:of|equal to)\s+(?P<value>{RATE})\s+{ROYALTY_BASE}")),
    ("ROYALTY_ADJUSTMENT", pattern(rf"\b(?:royalty\s+(?:advance|credit|buy[- ]down|substitute)|"
                                   rf"(?:advance|credit)\s+against\s+royalties){ASSIGN}(?P<value>{MONEY})")),
)
VALUE = pattern(rf"{RATE}|{MONEY}")
RED_CELL = pattern(REDACTED)
MARK = pattern(MARKER)
HEAD_CELL = pattern(rf"{NUMBERING}(?:total\s+)?(?P<head>{HEAD})"
                    rf"(?:\s+for licensed [\w -]+)?"
                    rf"(?:\s*\([^)]{{1,100}}\)|\s*[:–—-]\s*[\w -]+)?")
# These slots are only uncertainty indicators. They cannot supply SKIP evidence.
UNSUPPORTED = pattern(r"(?:\[[^\]\n]{0,40}\]|\{[^}\n]{0,40}\}|\*+|[†‡]+|#{2,}|[■█]+|…+|\.{3,}|TBD\b|to be determined\b)")
SLOT = pattern(rf"(?:\b(?:{HEAD}){ASSIGN}|{OBLIGATION})(?:{CURRENCY}\s*)?(?P<token>{UNSUPPORTED.pattern})")
CLAUSE = re.compile(r"[^\n;]+?(?:[.!?](?=\s|$)|(?=\n|;|$))")
HTML_TAIL = re.compile(rb"</(?:html|body)>\s*(?:</(?:text|document)>\s*)*$", re.I)
LOSSY_TABLE = re.compile(
    rb"<t[dh]\b[^>]*\b(?:colspan|rowspan)\s*=\s*[\"']?(?:[2-9]|[1-9]\d+)(?!\d)[^>]*>",
    re.I)
HTML_TABLE = re.compile(rb"<table\b.*?</table\s*>", re.I | re.S)
TABLE_SIGNAL = re.compile(rb"royalt|sublicens|percentage\s+of\s+(?:net|gross)\s+sales|rate\s+per", re.I)
OPERATION = pattern(r"\b(?:in witness whereof|intending to be legally bound|hereby agree|"
                    r"hereby grants?|shall pay|effective date|executed by|agreed and accepted)\b")


def evidence(text, family, start, end, value, reason, **extra):
    return dict(family=family, start=start, end=end, excerpt=text[start:end],
                value=value.strip(), reason=reason, **extra)


def classify(text, raw, parser, *, verified_identity, limitation=""):
    """Screen the full normalized exhibit and retain exact source offsets."""
    uncertainty = set()
    redactions, safeguards, rejected = [], [], []
    if len(text.strip()) < MIN_SOURCE_CHARS:
        uncertainty.add("SHORT_OR_EMPTY_SOURCE")
    if not verified_identity:
        uncertainty.add("SOURCE_IDENTITY_UNVERIFIED")
    if limitation or parser not in {"HTML_TEXT", "PLAIN_TEXT"} or "\ufffd" in text or "\x00" in text:
        uncertainty.add("UNSUPPORTED_OR_UNREADABLE_SOURCE")
    if parser == "HTML_TEXT" and not HTML_TAIL.search(raw):
        uncertainty.add("HTML_END_NOT_ESTABLISHED")
    wrapper = re.findall(rb"</?(?:DOCUMENT|TEXT)>", raw, re.I) if re.match(rb"\s*<DOCUMENT>", raw, re.I) else []
    if wrapper and [tag.upper() for tag in wrapper] != [b"<DOCUMENT>", b"<TEXT>", b"</TEXT>", b"</DOCUMENT>"]:
        uncertainty.add("INCOMPLETE_SEC_WRAPPER")
    if (re.search(r"\[(?:document |text )?truncated\]|unexpected end of (?:file|document)", text, re.I)
            or text.rstrip().endswith(("…", "..."))):
        uncertainty.add("INCOMPLETE_SOURCE")
    if MISSING.search(text) or MISSING_ECONOMIC_ATTACHMENT.search(text) or any(
        not re.search(rf"^[ \t]*{re.escape(ref.group('ref'))}(?=[\s:–—]|$)(?![^\n]*\|)", text, re.I | re.M)
        for rule in (REFERENCE, ATTACHED_REFERENCE) for ref in rule.finditer(text)
    ):
        uncertainty.add("MISSING_SCHEDULE_OR_APPENDIX")
    if parser == "HTML_TEXT" and (
        len(re.findall(rb"<table\b", raw, re.I)) != len(re.findall(rb"</table\s*>", raw, re.I))
        or any(LOSSY_TABLE.search(table.group()) and TABLE_SIGNAL.search(table.group())
               for table in HTML_TABLE.finditer(raw))
    ):
        uncertainty.add("TABLE_HEADER_MAPPING_UNCERTAIN")

    # An example can contain rate-shaped text without actually setting a rate.
    inline_examples = [clause.span() for clause in CLAUSE.finditer(text) if INLINE_EXAMPLE.search(clause.group())]
    # Each match is local, with no limit on its position in the exhibit.
    for family, rule in RED_RULES:
        for match in rule.finditer(text):
            if any(start <= match.start() < end for start, end in inline_examples):
                uncertainty.add("ILLUSTRATIVE_RATE_POSITION")
                continue
            value = match.group("value")
            if re.match(CURRENCY, value.strip(), re.I) and not re.search(UNIT_BASIS, match.group(), re.I):
                uncertainty.add("AMBIGUOUS_REDACTED_CURRENCY_RATE")
                continue
            marker = MARK.search(value)
            if not marker:
                continue
            if marker.group() in {"**", "***"} and not (
                "%" in value or re.search(r"\bpercent\b", value, re.I)
                or family in {"R1", "R6", "PER_UNIT"}
                or re.search(CURRENCY, value, re.I)
            ):
                uncertainty.add("AMBIGUOUS_BARE_MARKER")
                continue
            if re.fullmatch(rf"\s*(?:{CURRENCY}\s*)?{BRACKET}\s*", value, re.I) and family == "R1":
                code = "R9"
            else:
                code = family
            redactions.append(evidence(text, code, *match.span(), value,
                                       "Marker fills the stated royalty rate, formula or share slot",
                                       marker=marker.group(),
                                       direct_sales_rate=bool(family != "R8" and re.search(r"\b(?:sales|selling price|running royalty|earned royalty)\b", match.group(), re.I))))
    for match in SLOT.finditer(text):
        token = match.group("token")
        if not MARK.fullmatch(token) and not re.fullmatch(BRACKET, token, re.I):
            uncertainty.add("UNSUPPORTED_RATE_MARKER")

    for family, rule in KEEP_RULES:
        for match in rule.finditer(text):
            value = match.group("value")
            matched = match.group()
            if (family in {"R1", "R2", "R4", "R7", "R8"} and re.fullmatch(MONEY, value, re.I)
                    and not re.search(UNIT_BASIS, matched, re.I)):
                continue
            # R2 and the unit rule may describe the same slot.
            if family == "R2" and re.search(UNIT_BASIS, matched, re.I):
                continue
            code = "SUBLICENSE_SHARE" if family == "R8" else family
            if family in {"R1", "R2", "R4", "R7"} and re.search(SUB, matched, re.I):
                code = "SUBLICENSE_SHARE"
            elif re.search(QUALITATIVE, value, re.I):
                code = "QUALITATIVE_ROYALTY"
            safeguards.append(evidence(text, code, *match.span(), value, "Disclosed royalty economics",
                                       value_start=match.start("value")))

    scan_tables(text, redactions, safeguards, uncertainty)
    if not redactions and not safeguards:
        return uncertainty, redactions, safeguards, rejected

    for clause in CLAUSE.finditer(text):
        if not re.search(rf"\b(?:{ROYALTY}|{SUB})\b", clause.group(), re.I):
            # Control and specification percentages can be relevant audit rejections on their own.
            if not redactions:
                continue
        matched = clause.group()
        for numeric in VALUE.finditer(matched):
            if re.fullmatch(MONEY, numeric.group(), re.I):
                continue
            pos = clause.start() + numeric.start()
            if any(item["start"] <= pos and pos + len(numeric.group()) <= item["end"]
                   and (not item.get("table_family") or item["value_start"] == pos)
                   for item in safeguards):
                continue
            negative = next((code for code, rule in REJECTIONS
                             if any(max(numeric.start() - hit.end(), hit.start() - numeric.end()) <= 28
                                    for hit in rule.finditer(matched))), None)
            if negative:
                rejected.append(evidence(text, negative, *clause.span(), numeric.group(),
                                         "Numeric term measures a non-rate obligation"))
            elif re.search(rf"\b(?:{ROYALTY}|{SUB})\b", matched, re.I) and not ILLUSTRATIVE.search(matched):
                uncertainty.add("AMBIGUOUS_ROYALTY_PERCENTAGE")
    for item in safeguards[:]:
        start = text.rfind("\n", 0, item["start"]) + 1
        end = text.find("\n", item["end"])
        context = text[start:end if end != -1 else len(text)]
        if ILLUSTRATIVE.search(context):
            safeguards.remove(item)
            if not re.search(r"for example only|hypothetical|sample|blank", context, re.I):
                uncertainty.add("OPERATIVE_EFFECT_UNCERTAIN")
        elif item["family"] == "ROYALTY_PASS_THROUGH" and dict(REJECTIONS)["EXISTING_STREAM_OWNERSHIP"].search(context):
            safeguards.remove(item)
            rejected.append({**item, "family": "EXISTING_STREAM_OWNERSHIP",
                             "reason": "Allocation of a previously established royalty stream"})
    if redactions and ILLUSTRATIVE.search(text):
        uncertainty.add("OPERATIVE_EFFECT_UNCERTAIN")
    return uncertainty, redactions, safeguards, rejected


def scan_tables(text, redactions, safeguards, uncertainty):
    """Use normalized table rows and exact adjacent labels, with no layout inference."""
    headings = {}
    columns = None
    schedule = False
    continuation = None
    example = False
    operative = bool(OPERATION.search(text))
    for line in re.finditer(r"[^\n]+", text):
        if re.fullmatch(r"\s*(?:example|illustration|sample(?: royalty)? report)\s*:\s*", line.group(), re.I):
            example = True
            headings, columns, schedule, continuation = {}, None, False, None
        if example and re.match(r"\s*(?:--\s*)?(?:end of )?(?:exhibit|appendix|schedule)\s+[A-Z0-9]+\b",
                                line.group(), re.I):
            example = False
        if example:
            continue
        cells = list(re.finditer(r"[^|\t]+", line.group()))
        labels = {i: cell for i, cell in enumerate(cells) if HEAD_CELL.fullmatch(cell.group().strip())}
        if len(cells) == 1 and labels:
            headings = {0: (line.start(), line.end(), line.group())}
            columns = 1
            schedule = True
            continue
        if len(cells) == 1 and schedule:
            tier = re.match(r"\s*\((?:[ivx]+|[a-z]|\d+)\)\s+", line.group(), re.I)
            if tier:
                cells = [re.match(r".+", line.group()[tier.end():])]
                rate = pattern(rf"(?P<value>{REDACTED}|{RATE})\s+{ROYALTY_BASE}").match(cells[0].group())
                if rate:
                    start, _, heading = headings[0]
                    table_value(text, rate.group("value"), start, line.end(),
                                line.start() + tier.end() + rate.start("value"),
                                heading, "R8", operative, redactions, safeguards, uncertainty)
                elif re.search(rf"{UNSUPPORTED.pattern}|{RATE}", line.group(), re.I):
                    uncertainty.add("ROYALTY_SCHEDULE_MAPPING_UNCERTAIN")
                continue
        schedule = False
        # Numbered term sheets may put the label after a section number and
        # carry it over to an immediately following enumerated row.
        label_index = 1 if len(cells) > 2 and re.fullmatch(r"\d+(?:\.\d+)+(?:\([a-z]\))?",
                                                                          cells[0].group().strip(), re.I) else 0
        if len(cells) > 1 and label_index in labels and label_index < len(cells) - 1:
            heading = cells[label_index].group()
            found = False
            for cell in cells[label_index + 1:]:
                value = cell.group().strip()
                if table_value(text, value, line.start(), line.end(),
                               line.start() + cell.start() + len(cell.group()) - len(cell.group().lstrip()),
                               heading, "T1", operative, redactions, safeguards, uncertainty):
                    found = True
            if found:
                continuation = (heading, line.start()) if re.search(r"\|\s*\([a-z]\) ", line.group(), re.I) else None
                headings, columns = {}, None
                continue
        if continuation and len(cells) == 2 and re.match(r"\s*\([a-z]\) ", cells[0].group(), re.I):
            heading, locator = continuation
            table_value(text, cells[1].group().strip(), line.start(), line.end(),
                        line.start() + cells[1].start() + len(cells[1].group()) - len(cells[1].group().lstrip()),
                        heading, "T1", operative, redactions, safeguards, uncertainty, heading_start=locator)
            continue
        continuation = None
        if (len(cells) >= 2 and operative
                and re.fullmatch(r"sublicen[sc]e fees?", cells[-2].group().strip(), re.I)):
            rate = pattern(rf"\s*(?P<value>{RATE})\s+of\s+{SUB}").fullmatch(cells[-1].group())
            if rate:
                safeguards.append(evidence(text, "SUBLICENSE_SHARE", line.start(), line.end(), rate.group("value"),
                                           "Disclosed share in a sublicensing fee row", table_family="T1",
                                           value_start=line.start() + cells[-1].start() + rate.start("value")))
        if labels and len(cells) > 1:
            headings = {i: (line.start(), line.end(), cell.group()) for i, cell in labels.items()}
            columns = len(cells)
            continue
        if not headings:
            continue
        if len(cells) != columns:
            if len(cells) > 1:
                uncertainty.add("TABLE_HEADER_MAPPING_UNCERTAIN")
            # Retain a clearly numeric rate suffix under contiguous trailing
            # royalty headings, while leaving exclusion blocked by the mismatch.
            count = len(headings)
            if (len(cells) > count and set(headings) == set(range(columns - count, columns))
                    and all(pattern(RATE).fullmatch(cell.group().strip()) for cell in cells[-count:])):
                cells = [None] * (columns - count) + cells[-count:]
            else:
                if len(cells) > 1 and columns > 1:
                    continue
                headings, columns = {}, None
                continue
        found = False
        for i, (start, _, heading) in headings.items():
            cell = cells[i]
            value = cell.group().strip()
            if columns == 1 and re.fullmatch(NUMBER, value):
                # A lone integer after a heading may be a page number.
                uncertainty.add("TABLE_HEADER_MAPPING_UNCERTAIN")
                continue
            # The span for a column match includes intervening source rows. Keep
            # the heading locator separately and use the exact current row.
            if table_value(text, value, line.start(), line.end(),
                           line.start() + cell.start() + len(cell.group()) - len(cell.group().lstrip()),
                           heading, "T1", operative, redactions, safeguards, uncertainty,
                           heading_start=start):
                found = True
        if not found:
            headings, columns = {}, None


def table_value(text, value, start, end, value_start, heading, family, operative,
                redactions, safeguards, uncertainty, **locator):
    sublicense = bool(re.search(SUB, heading, re.I))
    unit = bool(re.search(UNIT_BASIS, heading, re.I))
    if RED_CELL.fullmatch(value):
        marker = MARK.search(value).group()
        if marker in {"**", "***"} and value == marker:
            uncertainty.add("AMBIGUOUS_BARE_MARKER")
        elif not operative or (re.match(CURRENCY, value, re.I) and not unit):
            uncertainty.add("OPERATIVE_EFFECT_UNCERTAIN")
        else:
            redactions.append(evidence(text, family, start, end, value,
                                       "Rate cell corresponds to the royalty heading",
                                       marker=marker, heading=heading.strip(),
                                       direct_sales_rate=bool(not sublicense and re.search(
                                           r"sales|running royalty|earned royalty", heading, re.I)),
                                       **locator))
    elif VALUE.fullmatch(value) or re.fullmatch(NUMBER, value):
        if not operative:
            uncertainty.add("OPERATIVE_EFFECT_UNCERTAIN")
        else:
            code = ("SUBLICENSE_SHARE" if sublicense else "PER_UNIT" if unit else
                    "QUALITATIVE_ROYALTY" if re.search(QUALITATIVE, value, re.I) else family)
            safeguards.append(evidence(text, code, start, end, value, "Disclosed rate in a royalty row",
                                       table_family=family, heading=heading.strip(), value_start=value_start,
                                       **locator))
    elif UNSUPPORTED.fullmatch(value):
        uncertainty.add("UNSUPPORTED_RATE_MARKER")
    else:
        if VALUE.search(value) or MARK.search(value):
            uncertainty.add("TABLE_HEADER_MAPPING_UNCERTAIN")
        return False
    return True


def audit_screen(run, text, raw, prepared, *, verified_identity, prompt_sha256=None):
    """Write and verify the advisory result. A failed audit cannot propose exclusion."""
    path = run / "royalty_screen.json"
    try:
        source_path = run / "screened_source.txt"
        source_bytes = text.encode("utf-8")
        atomic_bytes(source_path, source_bytes)
        if source_path.read_bytes() != source_bytes:
            raise OSError("Screened source read-back mismatch")
        embedded_name = re.search(rb"^<FILENAME>\s*([^\r\n<]+)", raw, re.I | re.M)
        if embedded_name and embedded_name.group(1).strip().decode("ascii", "replace").lower() != prepared["source_url"].rsplit("/", 1)[-1].lower():
            verified_identity = False
        uncertainty, redactions, safeguards, rejected = classify(
            text, raw, prepared["parser"], verified_identity=verified_identity,
            limitation=prepared["limitation"])
        scanned = True
    except Exception as exc:
        uncertainty, redactions, safeguards, rejected = {f"SCREEN_ERROR_{type(exc).__name__}"}, [], [], []
        scanned = False
    candidate = bool(redactions and not safeguards and not uncertainty)
    flags = set()
    if any(item["direct_sales_rate"] for item in redactions):
        flags.add("DIRECT_SALES_RATE_REDACTED")
        if safeguards and all(item["family"] == "SUBLICENSE_SHARE" for item in safeguards):
            flags.add("SUBLICENSE_SHARE_ONLY_TAXONOMY_PENDING")
    if redactions and any(item.get("table_family") for item in safeguards):
        flags.add("SOME_RATE_CELLS_OR_TIERS_DISCLOSED")
    if any(item["family"] == "EXISTING_STREAM_OWNERSHIP" for item in rejected) and not safeguards:
        flags.add("EXISTING_STREAM_ALLOCATION_WITHOUT_DISCLOSED_RATE")
    if rejected:
        flags.add("NON_RATE_PERCENTAGE_REJECTED")
    flags.update(item["family"] for item in safeguards if item["family"] in {
        "PER_UNIT", "MINIMUM_ROYALTY", "RECURRING_FEE", "SUBLICENSE_SHARE",
        "QUALITATIVE_ROYALTY", "ROYALTY_CREATION",
    })
    reasons = sorted(uncertainty)
    if safeguards:
        reasons.append("DISCLOSED_ROYALTY_ECONOMICS")
    if not redactions:
        reasons.append("NO_DIRECT_RATE_REDACTION")
    if candidate:
        reasons.append("DIRECT_RATE_REDACTION_WITHOUT_KEEP_SAFEGUARD")
    record = dict(
        screen_version=SCREEN_VERSION, screened_at=utc_now(), document_id=prepared["document_id"],
        source_url=prepared["source_url"], raw_source="source.htm", raw_sha256=prepared["source_sha256"],
        screened_source="screened_source.txt", screened_sha256=sha256(text.encode("utf-8")),
        decision="KEEP", status="WOULD_SKIP" if candidate else "KEEP",
        reasons=reasons, uncertainty=sorted(uncertainty), flags=sorted(flags),
        prompt_sha256=prompt_sha256, entire_source_scanned=scanned, redactions=redactions, safeguards=safeguards,
        rejected_percentages=rejected, source_review="PENDING" if candidate else "NOT_REQUIRED")
    try:
        atomic_json(path, record)
        if read_json(path) != record:
            raise OSError("Audit read-back mismatch")
    except Exception as exc:
        # Report the failure even if the run directory cannot be written.
        print(f"Screen KEEP (AUDIT_FAILURE) for {prepared['source_url']}: {exc}", file=sys.stderr)
        try:
            path.unlink(missing_ok=True)
        except OSError as cleanup_error:
            print(f"Could not remove unverified screening audit {path}: {cleanup_error}", file=sys.stderr)
        return None
    return record


def record_exclusion(run, proposal):
    """Verify a proposal made in this batch before recording an effective SKIP."""
    if not proposal or proposal["status"] != "WOULD_SKIP":
        return False
    receipt = run / "royalty_exclusion.json"
    try:
        if read_json(run / "royalty_screen.json") != proposal:
            raise ValueError("Screen audit changed after preparation")
        if (proposal["screen_version"] != SCREEN_VERSION or proposal["decision"] != "KEEP"
                or not proposal["entire_source_scanned"] or not proposal["redactions"]
                or proposal["uncertainty"] or proposal["safeguards"]):
            raise ValueError("Audit is not eligible for exclusion")
        prepared = read_json(run / "prepared.json")
        if any(prepared[key] != proposal[key] for key in ("document_id", "source_url")):
            raise ValueError("Prepared exhibit identity changed")
        raw = (run / "source.htm").read_bytes()
        screened = (run / "screened_source.txt").read_bytes()
        prompt = (run / "prompt.txt").read_bytes()
        if (sha256(raw) != proposal["raw_sha256"] or prepared["source_sha256"] != proposal["raw_sha256"]
                or sha256(screened) != proposal["screened_sha256"] or sha256(prompt) != proposal["prompt_sha256"]):
            raise ValueError("Prepared source or prompt changed after screening")
        text = screened.decode("utf-8")
        if len(text.strip()) < MIN_SOURCE_CHARS or any(
            not (0 <= item["start"] < item["end"] <= len(text))
            or text[item["start"]:item["end"]] != item["excerpt"]
            or item["marker"] not in item["excerpt"]
            for item in proposal["redactions"]
        ):
            raise ValueError("Redaction evidence does not match the screened source")
        effective = {**proposal, "status": "SKIPPED", "decision": "SKIP", "excluded_at": utc_now()}
        atomic_json(receipt, effective)
        if read_json(receipt) != effective:
            raise OSError("Exclusion receipt read-back mismatch")
    except Exception as exc:
        print(f"Screen KEEP (EXCLUSION_VERIFICATION_FAILED) for {run.name}: {exc}", file=sys.stderr)
        try:
            receipt.unlink(missing_ok=True)
        except OSError as cleanup_error:
            print(f"Could not remove unverified exclusion receipt {receipt}: {cleanup_error}", file=sys.stderr)
        return False
    return True
