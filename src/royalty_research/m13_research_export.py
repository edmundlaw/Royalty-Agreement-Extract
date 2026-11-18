"""M13 research-facing five-sheet Excel from the *same* immutable M13 row sets.

No extra AI invocation and no new assessment of a contract. Legacy columns
and records remain in rows.json/CSV; the optional detailed XLSX is untouched.
A missing/legacy licensing-rights field is NOT_ASSESSED, never 'No'.
"""
from __future__ import annotations

import re
import json
from pathlib import Path
from collections import defaultdict
from .licence_grant import grant_hits

NAMES = ('01 Royalty Database', '02 Tiers & Mechanics', '03 Other Payments',
         '04 Source Evidence', '05 QC & Issues', '06 Other Terms')

HEADERS = {
    NAMES[0]: ['Observation ID','Nature of IA','Licensed intangible asset','Royalty rate (%)','Per-unit / currency rate',
        'Usable for royalty benchmark','Benchmark note','Period-limited','Linked to row','Royalty rate as reported','Royalty family','Rate structure','Rate unit','Royalty base','Product / field of use',
        'Licensor','Licensee','Related party','Industry','Territory','Exclusivity','Exclusivity scope','Sublicensing rights',
        'Signing date','Effective date','SEC filing date','Agreement status','Royalty period','Minimum guarantee','Royalty cap',
        'Advance / prepayment','Upfront fee','Other material terms',
        'Payment source IDs','Rate evidence ID','Rate quotation','SEC source link','Disclosure','Reader comparison',
        'Document QC','Analyst action','Agreement ID','Document ID','IA evidence IDs',
        'Sublicensing evidence IDs','Exclusivity evidence IDs',
        'Exclusivity scope evidence IDs','Other terms evidence IDs','IA classification detail',
        'Agreement status (full text)','Exclusivity scope (full text)'],
    NAMES[1]: ['Record type','Observation ID','Term ID','Sequence','Rate (as reported)',
        'Rate numeric','Rate unit','Per-unit / currency rate','Lower threshold','Upper threshold','Mechanics / condition',
        'Evidence IDs','SEC source link','Document ID','QC state','Notes'],
    NAMES[2]: ['Payment ID','Payment type','Amount (as reported)','Amount numeric','Currency / unit',
        'Economic basis','Trigger / period','Evidence IDs','First source quotation',
        'SEC source link','QC state','Licensor','Licensee','Disclosure','Document ID'],
    NAMES[3]: ['Evidence ID','Role','Passage ID','Section','Exact quotation',
        'Linked extracted records','SEC source link','Extraction SHA-256','Document ID'],
    NAMES[4]: ['Record type','Document ID','Priority / level','Value or issue ID','Description',
        'First reader / state','Second reader','Passage / issue ID','Section','Source quotation',
        'SEC source link','Analyst action'],
    NAMES[5]: ['Agreement ID','Document ID','Licensor','Licensee','Category','Valuation relevance','Text','Evidence IDs',
        'Quotation of first evidence','SEC source link'],
}

# --- Python-only helpers (no AI) -------------------------------------------
SHORT_LIMIT = 150      # cap for long agreement-level text in sheet 01
# Royalty families whose rate applies to money received from a sublicensee (a
# pass-through / recovery share), not to product sales. The schema has no
# separate 'recovery' family, so SUBLICENSING_RECEIPTS is the whole list.
PASS_THROUGH_FAMILIES = {'SUBLICENSING_RECEIPTS'}
# Term sheet / conditional agreements: simple wording match on contractual_status.
# "conditional" must not match inside "unconditional" (an "Unconditional and binding" licence is not a
# term sheet); "non-binding" matches, a bare "binding" does not.
_CONDITIONAL = re.compile(r'term sheet|letter of intent|heads of terms|memorandum of understanding|\bnon-?\s?binding\b|'
                          r'(?<![A-Za-z])conditional|conditions? precedent|subject to[^.;]{0,60}conditions?', re.I)
# Keyword scan for readings that did not list the IP types (label shown in the workbook, regex).
# Several types can match; every matched type is listed (v0.13.9).
_IA_KEYWORDS = (('PATENT','patent',re.compile(r'\bpatents?\b',re.I)),
                ('KNOW_HOW','know-how/trade secret',re.compile(r'\bknow-?how\b|\btrade secrets?\b',re.I)),
                ('TECHNOLOGY','technology/technical information',
                 re.compile(r'\btechnical (?:information|data)\b|\b(?:licensed|proprietary|unpatented|patented) technolog(?:y|ies)\b|\btechnology licen[cs]es?\b',re.I)),
                ('SOFTWARE','software/source code',re.compile(r'\bsoftware\b|\bsource code\b',re.I)),
                ('COPYRIGHT','copyright',re.compile(r'\bcopyrights?\b',re.I)),
                ('TRADEMARK_BRAND','trademark/brand/trade name/logo',
                 re.compile(r'\btrade ?marks?\b|\bbrand marks?\b|\btrade names?\b|\blogos?\b|\bservice marks?\b',re.I)),
                ('FRANCHISE','franchise',re.compile(r'\bfranchis(?:e|es|ed|ing)\b',re.I)))
# Short label per enum value for a reader's own components list.
_IA_LABELS = {'PATENT':'patent','KNOW_HOW':'know-how','TECHNOLOGY':'technology','SOFTWARE':'software','COPYRIGHT':'copyright',
              'TRADEMARK_BRAND':'trademark/brand','TRADE_SECRET':'trade secret','FRANCHISE':'franchise'}
_RELATED = re.compile(r'related[- ]part(?:y|ies)|affiliated (?:entit(?:y|ies)|parties|companies)', re.I)


PERCENT_UNITS = ('PERCENT','PCT')
RATE_COLUMNS = ('Royalty rate (%)','Rate numeric')   # sheet 01 and sheet 02 rate cells
RATE_NUMBER_FORMAT = '0.00%'


def percent_points_to_fraction(value):
    """5 (percent-points) -> 0.05, rounded so 0.1 + float noise never reaches the cell."""
    return round(float(value)/100.0,10)


def _short(text, limit=SHORT_LIMIT):
    text='' if text is None else str(text)
    return text if len(text)<=limit else text[:limit-1].rstrip()+'\u2026'


def _ia_keyword_hint(texts):
    """Labelled fallback only: keyword scan of cited evidence text.

    Returns (nature, labels, detail) or None. nature is the single matched type, or 'MIXED' when
    several types match; labels lists ALL matched types (v0.13.9).
    """
    found={}
    for key,label,rx in _IA_KEYWORDS:
        for t in texts:
            m=rx.search(t or '')
            if m:found.setdefault(key,(label,m.group(0).lower()));break
    if not found:return None
    nature=next(iter(found)) if len(found)==1 else 'MIXED'
    labels=[v[0] for v in found.values()]
    return nature,labels,'Keyword hint (Python, not the reader): matched '+', '.join(f"'{w}' -> {k}" for k,(_l,w) in found.items())+' in cited evidence'


def _ia_components(agreement):
    """The reader's own components list as labels (deduplicated, reader order); unknown values are ignored."""
    raw=agreement.get('licensed_ip_components')
    if not isinstance(raw,list):return []
    out=[]
    for c in raw:
        label=_IA_LABELS.get(c)
        if label and label not in out:out.append(label)
    return out


# --- Other material terms: valuation relevance (Python only, v0.13.9) -------
KEY,SUPPLEMENTARY,ADMIN='KEY','SUPPLEMENTARY','ADMIN'
TIER_ORDER={KEY:0,SUPPLEMENTARY:1,ADMIN:2}
_CF=re.S|re.I
# Rules, applied in this order; the first that matches decides. Unsure -> SUPPLEMENTARY (never dropped).
#  1. KEY keywords (label shown in the sheet-01 summary): asset/scope/field, exclusivity, royalty base,
#     step-downs/offsets/stacking, minimums/diligence, term/termination rights such as "no sales within 5
#     years", costs borne by the licensee (prosecution/maintenance), sublicensing economics,
#     most-favoured terms, change of control with an economic effect.
#  2. STRONG ADMIN keywords (publicity, use of the licensor's name, counterparts, entire agreement, headings,
#     severability): ADMIN.
#  3. WEAK ADMIN keywords (notices, confidentiality, waiver, force majeure, ...): ADMIN only for the reader's
#     category OTHER and when the text does not talk about termination or expiry.
#  4. The reader's category: SCOPE, EXCLUSIVITY, SUBLICENSING, TERMINATION, RENEWAL -> KEY (an insolvency /
#     bankruptcy clause -> SUPPLEMENTARY); everything else (ASSIGNMENT, AUDIT_REPORTING, OTHER; i.e. payment
#     mechanics, currency/FX, reporting, audit, insolvency, assignment/transfer restrictions, governing law,
#     warranties/indemnities and anything unsure) -> SUPPLEMENTARY.
#  In AUDIT_REPORTING and ASSIGNMENT clauses the royalty-base/scope/exclusivity/sublicensing keywords are
#  ignored (an audit clause mentioning 'net sales' is not a royalty-base term).
_ECON=r'(?:royalt|payment|fee|milestone|rate|consideration|accelerat)'
_KEY_RULES=(
    ('TERM/TERMINATION',re.compile(r'terminat\w*[^.;]{0,120}\b(?:no|without|failure|fail\w*|not)\b[^.;]{0,60}(?:sales?|launch|commerciali[sz]\w*)'
                                   r'|\b(?:no|without|absence of)\s+(?:commercial\s+)?sales\b[^.;]{0,80}(?:terminat|within)',_CF)),
    ('COSTS',re.compile(r'\b(?:prosecution|maintenance|enforcement)\b[^.;]{0,80}\b(?:costs?|expenses?|fees?)\b'
                        r'|\b(?:costs?|expenses?)\b[^.;]{0,60}\b(?:borne|paid|reimburs\w+)\b[^.;]{0,40}\b(?:licensee|licensor)\b'
                        r'|\b(?:licensee|licensor)\b[^.;]{0,40}\b(?:bear|pay|reimburse)\w*\b[^.;]{0,60}\b(?:costs?|expenses?)\b',_CF)),
    ('DILIGENCE',re.compile(r'\bdiligence\b|\bminimum (?:annual |royalt|payment|sales|purchase)|\bcommercially reasonable efforts\b|\bmilestone\b',_CF)),
    ('STEP-DOWN/OFFSET',re.compile(r'\bstep[- ]?downs?\b|\breduc\w+\b[^.;]{0,60}\b(?:royalt|rate)|\b(?:royalt\w*|rate)\b[^.;]{0,60}\breduc\w+|\boffsets?\b|\bcredits? against\b|\bstacking\b|\bdeduct\w*\b[^.;]{0,60}\broyalt',_CF)),
    ('ROYALTY BASE',re.compile(r'\bnet sales\b|\broyalty (?:base|rate|computation|calculation|term)\b|\bcalculat\w+ (?:of )?(?:the )?royalt',_CF)),
    ('SUBLICENSING',re.compile(r'\bsub-?licens\w+\b[^.;]{0,100}\b(?:income|revenue|receipts?|consideration|royalt\w*|share|percent|%)|\b(?:income|revenue|receipts?|consideration|royalt\w*|share)\b[^.;]{0,100}\bsub-?licens',_CF)),
    ('MOST-FAVOURED',re.compile(r'\bmost[- ]favou?red\b',_CF)),
    ('CHANGE OF CONTROL',re.compile(r'change (?:of|in) control[^.;]{0,200}'+_ECON+r'|'+_ECON+r'[^.;]{0,200}change (?:of|in) control',_CF)),
    ('EXCLUSIVITY',re.compile(r'\bexclusiv\w*\b|\bsole licen[cs]e\b',_CF)),
    ('SCOPE',re.compile(r'\bfield of use\b|\blicensed (?:products?|patents?|technolog\w+|ip|intellectual property|marks?|rights)\b|\bterritory\b|\bscope of (?:the )?licen[cs]e\b',_CF)),
)
_STRONG_ADMIN=re.compile(r'\b(?:publicity|press releases?|public announcements?|counterparts?|entire agreement|headings?|severab\w+|further assurances)\b'
                         r'|\buse of (?:the )?(?:licensor|licensee|either party|a party|its|their|\w+.s)\b[^.;]{0,30}\b(?:name|names|logos?|marks?)\b[^.;]{0,80}\b(?:publicity|advertis\w+|promot\w+|marketing|press)',_CF)
_WEAK_ADMIN=re.compile(r'\bnotices?\b|\bconfidential\w*\b|\bwaivers?\b|\bforce majeure\b|\bindependent contractors?\b|\bamend\w* in writing\b|\bsurviv\w+\b',_CF)
_KEY_CATEGORIES={'SCOPE':'SCOPE','EXCLUSIVITY':'EXCLUSIVITY','SUBLICENSING':'SUBLICENSING','TERMINATION':'TERM/TERMINATION','RENEWAL':'TERM/TERMINATION'}
_CATEGORY_SENSITIVE=('ROYALTY BASE','SCOPE','EXCLUSIVITY','SUBLICENSING')
_TERM_TALK=re.compile(r'terminat|expir|renew',re.I)


def classify_other_term(category, text):
    """Python-only valuation relevance of one other_material_term: returns (tier, label).

    tier is KEY, SUPPLEMENTARY or ADMIN; label is a short heading used in the sheet-01 summary.
    Rules and their order are documented above. When unsure -> SUPPLEMENTARY.
    """
    cat=str(category or 'OTHER').upper(); body=str(text or '')
    for label,rx in _KEY_RULES:
        if label in _CATEGORY_SENSITIVE and cat in ('AUDIT_REPORTING','ASSIGNMENT'):continue   # e.g. 'net sales' inside an audit clause
        if rx.search(body):return KEY,_KEY_CATEGORIES.get(cat,label)   # the reader's own key category names it
    if _STRONG_ADMIN.search(body):return ADMIN,'ADMIN'
    if cat=='OTHER' and _WEAK_ADMIN.search(body) and not _TERM_TALK.search(body):return ADMIN,'ADMIN'
    if cat in _KEY_CATEGORIES:
        # A termination clause that is only about insolvency stays supplementary; one that also gives a right
        # to terminate for breach, convenience or similar is an early-termination right (KEY).
        if re.search(r'insolven|bankrupt',body,re.I) and not re.search(r'breach|convenience|without cause|for cause|change (?:of|in) control',body,re.I):
            return SUPPLEMENTARY,cat
        return KEY,_KEY_CATEGORIES[cat]
    return SUPPLEMENTARY,cat


def key_terms_summary(material, limit=120):
    """Sheet-01 text: only KEY terms, as category labels plus a count; at most `limit` characters."""
    if not material:return 'none recorded'
    labels=[];n=0;other=0
    for m in material:
        tier,label=classify_other_term(m.get('category'),m.get('text'))
        if tier==KEY:
            n+=1
            if label not in labels:labels.append(label)
        else:other+=1
    if not n:return _short(f'no key terms ({other} other term{"" if other==1 else "s"}) \u2013 see sheet 06',limit)
    tail=f' ({n} key term{"" if n==1 else "s"}) \u2013 see sheet 06'
    head=', '.join(labels)
    if len(head)+len(tail)>limit:
        keep=[]
        for lab in labels:
            if len(', '.join(keep+[lab]))+len(', ...')+len(tail)<=limit:keep.append(lab)
            else:break
        head=', '.join(keep)+', ...'
    return head+tail


def _related_hint(texts):
    for t in texts:
        for m in _RELATED.finditer(t or ''):
            if re.search(r'\b(?:not|no|nor|neither)\b[^.]{0,25}$',t[max(0,m.start()-30):m.start()],re.I):continue
            return m.group(0)
    return None


# Document QC states that make a reading unfit for use as a benchmark until a person has looked at it.
NEEDS_REVIEW_STATES = ('SOURCE_CHECK_FAILED','SECOND_READER_FAILED_SOURCE_CHECK','TWO_READERS_DIFFER')


def _record_error_codes(term_id, source_errors):
    """Codes of source-check errors tied to one royalty term (ref is the term, one of its tiers, or its evidence)."""
    tid=str(term_id or '')
    if not tid:return []
    out=[]
    for e in source_errors or []:
        ref=str((e or {}).get('ref') or '')
        if ref==tid or ref.startswith(tid+':'):out.append(str(e.get('code') or 'ERROR'))
    return out


def benchmark_usable(term, related, status, *, nature=None, grant_found=None, qc_state=None, record_errors=None,
                     tier_summary=None, unresolved=False, period_limited=None):
    """Python rule, zero AI. Returns ('YES'|'NO', note). Any one reason makes it NO.

    nature is the reader's own licensed_ip_nature; grant_found is True/False when the source text was
    scanned for licence-grant wording, None when no text is available (then that reason is skipped).
    qc_state is the document's QC state: SOURCE_CHECK_FAILED, SECOND_READER_FAILED_SOURCE_CHECK and
    TWO_READERS_DIFFER force NO ("needs review: <state>" is the first reason). record_errors lists the
    source-check error codes tied to this very row; any of them forces NO. tier_summary (e.g. '4%-7%') is given when
    the term has disclosed tiers: the blank scalar rate is then not "undisclosed" but "tiered, assess at point of use"
    (still NO: a tiered rate is not one number). unresolved marks an unrated cross-chunk duplicate that Python could
    not attach to one real term (sheet 05 has the HIGH open issue). TWO_READERS_AGREE_ON_NUMBERS
    stays allowed (same numbers in the same clauses) with a note to read the STRUCTURE differences.
    SINGLE_READER_NOT_CHECKED is the normal mode and stays allowed.
    period_limited (v0.13.12) is (wording, base_observation_id_or_None) when the term's own wording says it applies only
    to a sell-off / post-termination disposal period: it is a restatement for that period, never a benchmark of its own.
    """
    reasons=[]
    if period_limited:
        kind,base=period_limited
        reasons.append(f'period-limited ({kind}) restatement of {base} \u2013 use base row' if base
                       else f'period-limited ({kind}) royalty; base row not identified \u2013 see sheet 05')
    if qc_state in NEEDS_REVIEW_STATES:reasons.append(f'needs review: {qc_state}')
    if record_errors:reasons.append('needs review: source-check error on this row ('+', '.join(sorted(set(record_errors)))+')')
    if nature=='UNDETERMINED' and grant_found is False:
        reasons.append('no IP licence grant found (e.g. services / profit share)')
    family=term.get('Family')
    if family in PASS_THROUGH_FAMILIES:reasons.append('pass-through of sublicensee receipts, not a sales royalty')
    rate=term.get('Rate_Numeric')
    unit=str(term.get('Rate_Unit') or '').upper()
    if unresolved:
        reasons.append('unresolved cross-chunk duplicate \u2013 see sheet 05')
    elif rate in (None,'') and tier_summary and term.get('Disclosure_Status') not in ('REDACTED','AMBIGUOUS','NOT_VERIFIED'):
        reasons.append('tiered rate \u2013 assess at point of use')
    elif rate in (None,'') or term.get('Disclosure_Status') in ('REDACTED','AMBIGUOUS','NOT_VERIFIED') or unit in ('UNKNOWN','REDACTED'):
        reasons.append('rate not disclosed or unclear')
    else:
        try:
            if float(rate)>=50:reasons.append(f'rate {rate:g}% is 50% or more')
        except (TypeError,ValueError):reasons.append('rate not numeric')
        if unit not in ('PERCENT','PCT'):reasons.append('rate is not a percentage')
    if related.startswith('YES'):reasons.append('related-party agreement'+(' (keyword hint)' if 'hint' in related else ''))
    if _CONDITIONAL.search(status or ''):reasons.append('term sheet or conditional agreement')
    if reasons:return 'NO','; '.join(reasons)
    note='No exclusion rule triggered; still confirm at point of use'
    if qc_state=='TWO_READERS_AGREE_ON_NUMBERS':note+='; both readers agree on the numbers, check sheet 05 STRUCTURE differences'
    return 'YES',note


def _amount_value(text):
    from .m13_two_reader import reader_value
    try:return reader_value(text)
    except Exception:return None


def _figures_in(*texts):
    """Percent and money figures written in reader text (e.g. "1% per month"); used to pick the quotation that shows them."""
    from .m13_two_reader import numbers_in_text
    out=[]
    for text in texts:
        for t in numbers_in_text(str(text or '')):
            if t['unit'] in ('PCT','USD') and t['value'] not in out:out.append(t['value'])
    return out


def _best_evidence(ids, did, evid_by_doc, amount_text=None, figures=None):
    """Evidence to display for a figure: a quotation that contains the reported amount (digits compared after
    normalising "$20,000" / "20000" / "9%" / "nine percent"), else (v0.13.12) one that contains a figure the record
    itself states (figures: e.g. the "1%" of an interest charge that has no amount), else RATE-role evidence, else the first."""
    from .m13_two_reader import numbers_in_text
    items=[evid_by_doc.get((did,i)) for i in ids]
    items=[e for e in items if e]
    if not items:return None
    want=_amount_value(amount_text) if amount_text not in (None,'') else None
    if want is not None:
        for e in items:
            if any(t['value']==want for t in numbers_in_text(e.get('Exact_Quotation') or '')):return e
    elif figures:
        for e in items:
            if any(t['value'] in figures for t in numbers_in_text(e.get('Exact_Quotation') or '')):return e
    for e in items:
        if e.get('Role')=='RATE':return e
    return items[0]


# --- Display quotation: a wrapped source line completed to its sentence (v0.13.12) ----------------
# The reader's evidence quote is often one wrapped source line ("percent (4%) of all Net Sales during that Contract
# Year (" Royalty ") minus (ii)"). For DISPLAY ONLY the chosen quote is extended to the enclosing sentence, using the
# text of the cited passage and of the passages next to it (a wrapped clause continues in the next passage). The
# stored evidence and the source check are never touched. The result is the source text itself with whitespace
# normalised, at most DISPLAY_QUOTE_CAP characters, cut at clause boundaries with an ellipsis when the sentence is longer.
DISPLAY_QUOTE_CAP=300
_PASSAGE_SEP='\x1f'
_SENTENCE_END=re.compile(r'[.;?!]')
_NOT_AN_END=re.compile(r'(?:\b(?:Inc|Ltd|Corp|Co|No|Nos|Sec|Art|St|Mr|Mrs|Ms|Dr|vs|etc|Jr|Sr|Bros|LLC|LP|U\.S|e\.g|i\.e)|\b[A-Z]|\bSection\s+\d+|\bArticle\s+\d+|\([a-z0-9]{1,4}\))$')
_WALL=re.compile(r'\W*(?:page\s+)?[\dIVXLCivxlc]{1,6}\W*')   # a page number / roman numeral on its own line


def _squash(text):
    return re.sub(r'\s+',' ',str(text or '')).strip()


def _boundary_after(ctx, i):
    """True when ctx[i] ends a sentence: . ; ? ! (or the end of a passage that ends in ':') and is not an abbreviation."""
    c=ctx[i]
    nxt=ctx[i+1:i+3]
    if c==':':return nxt[:1]==_PASSAGE_SEP
    if not _SENTENCE_END.match(c):return False
    k=i+1
    while k<len(ctx) and ctx[k] in '\u201d")\'':k+=1
    if k<len(ctx) and ctx[k] not in (' ',_PASSAGE_SEP):return False
    if c=='.' and _NOT_AN_END.search(ctx[max(0,i-14):i]):return False
    return True


def display_quote(quote, passage_id, texts, cap=DISPLAY_QUOTE_CAP):
    """The quote completed to its enclosing sentence (see above), or the quote itself when it cannot be located.

    texts is the ordered list of passage texts of the document (index = passage number - 1); passage_id ends in P<number>.
    """
    q=_squash(quote)
    m=re.search(r'P0*(\d+)$',str(passage_id or ''))
    if not q or not m or not texts:return quote
    n=int(m.group(1))-1
    if not 0<=n<len(texts):return quote
    lo,hi=max(0,n-4),min(len(texts),n+5)
    parts=[_squash(texts[k]) for k in range(lo,hi)]
    starts=[];ctx=''
    for part in parts:
        starts.append(len(ctx)); ctx+=part+_PASSAGE_SEP
    own=starts[n-lo]
    qs=ctx.replace(_PASSAGE_SEP,' ').find(q,own)
    if qs<0 or qs+len(q)>own+len(parts[n-lo]):return quote   # not inside the cited passage: leave it alone
    qe=qs+len(q)
    # A page number or an ALL-CAPS heading on its own line is a wall: the sentence never reaches across it.
    is_wall=lambda i:i!=n-lo and (bool(_WALL.fullmatch(parts[i])) or (len(parts[i])<40 and not re.search(r'[a-z]',parts[i])))   # page number / ALL-CAPS heading
    wall_start={starts[i+1] for i in range(len(parts)-1) if is_wall(i)}
    wall_end={starts[i] for i in range(len(parts)) if is_wall(i)}
    left=qs
    while left>0 and left not in wall_start:
        k=left-1
        if ctx[k] in (' ',_PASSAGE_SEP):
            j=k
            while j>=0 and ctx[j] in (' ',_PASSAGE_SEP):j-=1
            if j<0 or _boundary_after(ctx,j):break
        left=k
    right=qe
    if not _boundary_after(ctx,qe-1):
        k=qe
        while k<len(ctx) and k not in wall_end:
            if _boundary_after(ctx,k):k+=1;break
            k+=1
        right=k
    sentence=_squash(ctx[left:right].replace(_PASSAGE_SEP,' '))
    if sentence==q:return quote
    if len(sentence)<=cap:return sentence
    budget=cap-len(q)
    if budget<=0:return quote
    lead=ctx[left:qs].replace(_PASSAGE_SEP,' '); tail=ctx[qe:right].replace(_PASSAGE_SEP,' ')
    left_allow=max(budget//2,budget-len(tail))
    lead_out=lead
    if len(lead)>left_allow:
        lead_out=''
        for mm in re.finditer(r'[,;:]\s+',lead):
            if len(lead)-mm.end()<=left_allow:lead_out=lead[mm.end():];break
    room=budget-len(lead_out)
    tail_out=tail
    if len(tail)>room:
        tail_out=''
        for mm in re.finditer(r'[,;]\s+',tail):
            if mm.start()+1<=room:tail_out=tail[:mm.start()+1]
    out=_squash(('\u2026 ' if lead_out!=lead else '')+lead_out+q+tail_out+(' \u2026' if tail_out!=tail else ''))
    return quote if out==q else out


def _tier_summary(tiers):
    """'4%-7%' (min-max of the disclosed tier rates) for sheet 01; None when no tier carries a numeric rate."""
    vals=[];unit=None
    for z in tiers:
        try:vals.append(float(z.get('Rate_Numeric')))
        except (TypeError,ValueError):continue
        unit=unit or str(z.get('Rate_Unit') or '').upper()
    if not vals:return None
    lo,hi=min(vals),max(vals)
    suffix='%' if unit in ('PERCENT','PCT') else (' '+unit.lower().replace('_',' ') if unit else '')
    return f'{lo:g}{suffix}' if lo==hi else f'{lo:g}{suffix}\u2013{hi:g}{suffix}'


_CURRENCY_NUMBER=re.compile(r'(US\s*\$|C\$|A\$|\$|USD|EUR|CAD|AUD|GBP|JPY|CHF|\u20ac|\u00a3|\u00a5)\s*(\d[\d,]*(?:\.\d+)?)',re.I)
_CURRENCY_CODE={'$':'USD','US$':'USD','USD':'USD','C$':'CAD','CAD':'CAD','A$':'AUD','AUD':'AUD','EUR':'EUR','\u20ac':'EUR',
                'GBP':'GBP','\u00a3':'GBP','JPY':'JPY','\u00a5':'JPY','CHF':'CHF'}


def _currency_of(value_text, quotes):
    """Currency code written next to the figure ("$0.05", "USD 0.05") in the reported value, else in the quoted text.
    A bare "$" is read as USD. None when no currency is written next to that figure."""
    want=_amount_value(value_text)
    for text in [value_text]+list(quotes):
        for m in _CURRENCY_NUMBER.finditer(str(text or '')):
            if want is None or _amount_value(m.group(2))==want:
                return _CURRENCY_CODE.get(re.sub(r'\s+','',m.group(1)).upper())
    return None


def per_unit_rate(record, quotes=()):
    """Sheet text for a rate that is NOT a percentage: "0.05 USD per unit" (CURRENCY_PER_UNIT) or "<n> (unit X)".

    None for percent units and for records with no numeric rate. The percent column never holds these (v0.13.12)."""
    unit=str(record.get('Rate_Unit') or '').upper()
    if unit in PERCENT_UNITS:return None
    num=record.get('Rate_Numeric')
    if num in (None,''):return None
    try:shown=f'{float(num):g}'
    except (TypeError,ValueError):shown=str(num)
    if unit=='CURRENCY_PER_UNIT':
        cur=_currency_of(record.get('Rate_Value_Text'),quotes)
        return f'{shown} {cur} per unit' if cur else f'{shown} per unit (currency not stated)'
    return f'{shown} (rate unit {unit or "not stated"})'


def _percent_cell(record):
    """Numeric rate for the percent column: only PERCENT / PCT units (v0.13.12)."""
    return record.get('Rate_Numeric') if str(record.get('Rate_Unit') or '').upper() in PERCENT_UNITS else None


# --- Period-limited (sell-off) restatements (v0.13.12) ---------------------------------------------
# A royalty term whose OWN wording (period, scope, territory, base, its rate quotation or its conditions) says it applies
# only to a sell-off / post-termination inventory-disposal period is a restatement for that period, not a second benchmark.
# Wording that is NOT enough: "royalties continue after expiry of the patent", "during the Term", "sales after expiration".
_SELL_OFF=re.compile(r'\bsell[- ]?off\b',re.I)
_DISPOSAL=re.compile(r'\b(?:dispos\w+|sell(?:ing)?|sold|sales?|liquidat\w+)\b[^.;]{0,60}\b(?:inventor(?:y|ies)|(?:remaining|existing|unsold|on[- ]hand) stock|goods on hand)\b'
                     r'|\b(?:inventor(?:y|ies)|(?:remaining|existing|unsold|on[- ]hand) stock|goods on hand)\b[^.;]{0,60}\b(?:dispos\w+|sell(?:ing)?|sold|sales?|liquidat\w+)',re.I)
_AFTER_END=re.compile(r'\b(?:after|following|upon|post)[- ]?(?:the )?(?:termination|expir\w+)\b',re.I)


def period_limited_wording(*texts):
    """'sell-off' or 'post-termination inventory disposal' when one of the texts says so; else None."""
    for text in texts:
        text=str(text or '')
        if _SELL_OFF.search(text):return 'sell-off'
        if _DISPOSAL.search(text) and _AFTER_END.search(text):return 'post-termination inventory disposal'
    return None


def link_period_limited(items):
    """items: list of dicts {key, doc, family, base, scope, wording}. Returns {key: ('base', base_key) | ('none', [candidate keys])}
    for every item whose wording is set: linked to its base row only when exactly one plausible base term exists
    (same document and family, not itself period-limited; narrowed by royalty base and product scope when several)."""
    from .m13_consolidate import _words
    out={}
    for it in items:
        if not it['wording']:continue
        cands=[o for o in items if o['doc']==it['doc'] and not o['wording'] and o['family']==it['family']]
        if len(cands)>1:
            narrowed=[o for o in cands if _words(o['base'])==_words(it['base'])
                      and (lambda x,y:not x or not y or x<=y or y<=x)(_words(o['scope']),_words(it['scope']))]
            cands=narrowed or cands
        out[it['key']]=('base',cands[0]['key']) if len(cands)==1 else ('none',[c['key'] for c in cands])
    return out


def _records(rows, name):
    if name not in rows or not rows[name]: return []
    headers=rows[name][0]
    return [dict(zip(headers, r)) for r in rows[name][1:]]


def _join(value, delim='; '):
    if isinstance(value, list):return delim.join(str(v) for v in value if v is not None)
    return '' if value is None else str(value)


def _ids(value):
    """Read IDs from M3's JSON cells or from already separated row sets."""
    if isinstance(value, str) and value.startswith('['):
        try:
            decoded=json.loads(value)
            if isinstance(decoded, list):return [str(x) for x in decoded if x is not None]
        except ValueError:pass
    if isinstance(value, list):return [str(x) for x in value if x is not None]
    return [x.strip() for x in str(value or '').split(';') if x.strip()]


def _safe(value):
    if value is None:return None
    if isinstance(value, (float,int,bool)):return value
    text=str(value)
    if len(text)>32767:
        raise ValueError('Research cell exceeds Excel 32767-character limit; source must be split, not silently truncated')
    return text


def _observation_reference(term_id, document_id):
    return f'{document_id}:{term_id}'


_ROYALTY_WORD=re.compile(r'royalt',re.I)


_MINIMUM_LABEL=re.compile(r'\s*(?:a\s+|an\s+|the\s+)?(?:minimum\s+(?:annual\s+)?royalt(?:y|ies)|royalt(?:y|ies)\s+minimum|guaranteed\s+minimum\s+royalt(?:y|ies))\b',re.I)


def _is_minimum_royalty(p):
    """MINIMUM_ROYALTY, or a GUARANTEE that is explicitly labelled as a minimum royalty (e.g. not a share-price guarantee).

    v0.13.11 (B4): the label may open the Basis OR the Condition field."""
    kind=p.get('Kind')
    if kind=='MINIMUM_ROYALTY':return True
    return kind=='GUARANTEE' and any(_MINIMUM_LABEL.match(str(p.get(k) or '')) for k in ('Basis','Condition'))


def _amount_label(p):
    raw=p.get('Amount_Text')
    if raw is None or str(raw).strip()=='':
        amount='AMOUNT_AMBIGUOUS' if p.get('Disclosure_Status')=='AMBIGUOUS' else 'AMOUNT_NOT_DISCLOSED'
    else:
        amount=str(raw).strip()
        if re.fullmatch(r'\d+',amount):amount=f'{int(amount):,}'
    currency=p.get('Currency')
    if currency and currency not in amount:amount=f'{currency} {amount}'
    elif not currency and re.search(r'\bshares?\b',str(p.get('Basis') or ''),re.I):amount+=' shares'
    return amount


# What a minimum is "per" (v0.13.12): "per licensed Product", "for each Contract Year" -> "per ...". Only the payment
# record's own Basis wording is used, cut at the first filler word; nothing is inferred.
_QUALIFIER=re.compile(r'\b(per|for each|for every)\s+((?:[A-Za-z][\w-]*)(?:\s+[A-Za-z][\w-]*){0,3})',re.I)
_QUALIFIER_STOP={'and','or','if','that','which','in','on','during','until','from','unless','but','where','when','provided','commencing',
                 'beginning','payable','shall','to','of','after','before','with','as','is','are','be','by','at','the','a','an'}


def _minimum_qualifier(p):
    # Basis only: a "per ..." in the Condition usually belongs to something else ("may be increased once per five-year period").
    for m in _QUALIFIER.finditer(str(p.get('Basis') or '')):
        words=[]
        for w in m.group(2).split():
            if w.lower() in _QUALIFIER_STOP:break
            words.append(w)
        if words:return 'per '+' '.join(words)
    return ''


def _payment_summary(payments: list[dict], kinds: set[str], *, minimum=False, royalty_only=False):
    """Faithful non-additive list of classified agreement-level payment records.

    Never reinterpret a signing advance as a separate upfront fee, never sum
    payments, and never treat missing rows as proof of the absence of a clause.
    """
    matches=[]
    for p in payments:
        kind=p.get('Kind')
        if kind not in kinds:continue
        if royalty_only and not _ROYALTY_WORD.search(' '.join(str(p.get(k) or '') for k in ('Basis','Condition'))):
            continue   # e.g. a cap on deferred service consideration: stays in sheet 03 only
        if minimum and kind=='GUARANTEE' and not _is_minimum_royalty(p):
            # 'GUARANTEE' may be e.g. share-price or performance guarantees: only royalty-minimum-labelled ones go here.
            continue
        amount=_amount_label(p)
        if minimum:
            qualifier=_minimum_qualifier(p)   # v0.13.12: "USD 25,000 per licensed Product [1-PAY02]"
            if qualifier:amount+=' '+qualifier
        matches.append(f"{amount} [{p.get('Payment_ID') or 'UNKNOWN_ID'}]")
    return '; '.join(matches) if matches else 'NOT_ASSESSED'


# Explicit advance wording only (v0.13.12). "on the Effective Date" is NOT enough (that is a due date, not a statement
# that the payment is made in advance); a notice given "in advance" is not a payment made in advance.
_ADVANCE_WORDING=re.compile(r'\bin advance\b|\badvance(?:d)? (?:payment|royalt\w+|minimum)\b|\bpre-?paid\b|\bprepay\w*|'
                            r'\b(?:payable|paid|due) (?:up)?on (?:the )?(?:signing|execution)\b|\bupon (?:signing|execution) of this agreement\b',re.I)
_NOT_PAYMENT_ADVANCE=re.compile(r'\bnotice\b|\bnotif\w+|\bregistered mail\b|\bwritten\b',re.I)


def _advance_wording(texts):
    """The first clause that says a payment is made in advance, shortened; None when no text says so."""
    for text in texts:
        for clause in re.split(r'(?<=[.;])\s+',str(text or '')):
            m=_ADVANCE_WORDING.search(clause)
            if m and not _NOT_PAYMENT_ADVANCE.search(clause):
                a,b=max(0,m.start()-30),min(len(clause),m.end()+40)
                snippet=clause[a:b]
                if a>0:snippet=re.sub(r'^\S*\s+','',snippet)       # no half word at either edge
                if b<len(clause):snippet=re.sub(r'\s+\S*$','',snippet)
                return snippet.strip()
    return None


def _advance_from_minimum(payments, quotes_of):
    """Minimum-royalty records whose own Basis / Condition / evidence quotation says the minimum is paid in advance.

    Returns 'USD 130,000 [C1-P1] (record says: "prepaid by January 30 each Contract Year")' items, or []."""
    out=[]
    for p in payments:
        if not _is_minimum_royalty(p):continue
        hit=_advance_wording([p.get('Basis'),p.get('Condition')]+list(quotes_of(p)))
        if hit:out.append(f"{_amount_label(p)} [{p.get('Payment_ID') or 'UNKNOWN_ID'}] (minimum royalty record says: \"{hit.rstrip('.;,')}\")")
    return out


def _payment_references(payments: list[dict]):
    def evidence(value):
        if isinstance(value, str) and value.startswith('['):
            try:
                parsed=json.loads(value)
                if isinstance(parsed,list):return _join(parsed)
            except (ValueError,TypeError):pass
        return _join(value)
    return '; '.join(f"{p.get('Kind') or 'UNKNOWN'}:{p.get('Payment_ID') or 'UNKNOWN'}:{evidence(p.get('Evidence_IDs'))}"
                    for p in payments if p.get('Payment_ID'))


def research_rows(rows: dict, first_readings: dict | None = None, source_texts: dict | None = None,
                  source_errors: dict | None = None) -> dict:
    """Derive a presentational database. All primary evidence remains in rows.

    first_readings maps Document_ID to its *first reader* extraction. This does
    not resolve reader disagreements or infer novel rights on old recordings.
    """
    first_readings=first_readings or {}
    source_texts=source_texts or {}
    python_issues=[]    # open issues raised by the export rules themselves (sheet 05)
    docs={d['Document_ID']:d for d in _records(rows,'Documents')}
    terms=_records(rows,'Royalty Terms')
    payments=_records(rows,'Other Payments')
    evid=_records(rows,'Evidence')
    evid_by_doc={(e['Document_ID'],e['Evidence_ID']):e for e in evid}
    links=defaultdict(list)
    for table, key, id_field in (('Royalty Terms','Rate_Evidence_IDs','Term_ID'),
                                 ('Royalty Terms','Evidence_IDs','Term_ID'),
                                 ('Tiers','Evidence_IDs','Term_ID'),
                                 ('Other Payments','Evidence_IDs','Payment_ID')):
        for item in _records(rows,table):
            for evidence_id in _ids(item.get(key)):
                if evidence_id:
                    ref=f'{table}:{item[id_field]}'
                    if ref not in links[(item['Document_ID'],evidence_id)]:links[(item['Document_ID'],evidence_id)].append(ref)
    tiers_by_term=defaultdict(list)
    for z in _records(rows,'Tiers'):tiers_by_term[(z['Document_ID'],z['Term_ID'])].append(z)
    unresolved_terms=set()
    for issue in _records(rows,'Open Issues'):
        if issue.get('Kind')=='UNRESOLVED_DUPLICATE':
            m_=re.search(r'\bterm (\S+?) has no rate',str(issue.get('Description') or ''))
            if m_:unresolved_terms.add((issue.get('Document_ID'),m_.group(1)))
    result={n:[HEADERS[n][:]] for n in NAMES}
    payments_by_doc=defaultdict(list)
    for p in payments:payments_by_doc[p['Document_ID']].append(p)
    conditions=defaultdict(list)
    for c in _records(rows,'Conditions'):conditions[(c['Document_ID'],c['Term_ID'])].append(c)
    adjustments=defaultdict(list)
    for a in _records(rows,'Adjustments'):adjustments[(a['Document_ID'],a['Term_ID'])].append(a)

    def shown_quote(e):
        """Display text of an evidence row: its quote completed to the enclosing sentence (stored evidence is unchanged)."""
        if not e:return ''
        quote=e.get('Exact_Quotation') or ''
        return display_quote(quote,e.get('Passage_ID'),source_texts.get(e.get('Document_ID')) or [])

    # Period-limited (sell-off) restatements: decided once per document from each term's own wording.
    quotes_of_term=lambda t:[(evid_by_doc.get((t['Document_ID'],i)) or {}).get('Exact_Quotation') for i in _ids(t.get('Rate_Evidence_IDs'))]
    pl_items=[{'key':(t['Document_ID'],t.get('Term_ID')),'doc':t['Document_ID'],'family':t.get('Family'),'base':t.get('Royalty_Base'),
               'scope':t.get('Product_Scope'),
               'wording':period_limited_wording(t.get('Effective_Period'),t.get('Product_Scope'),t.get('Territory'),t.get('Royalty_Base'),
                                                t.get('Base_Definition'),*quotes_of_term(t),
                                                *[c.get('Condition_Text') for c in conditions.get((t['Document_ID'],t.get('Term_ID')),[])])}
              for t in terms]
    obs_of={(t['Document_ID'],t.get('Term_ID')):t.get('Observation_ID') or _observation_reference(t.get('Term_ID'),t['Document_ID']) for t in terms}
    pl_link=link_period_limited(pl_items); pl_wording={i['key']:i['wording'] for i in pl_items}
    restated_by=defaultdict(list)
    for key,(state,target) in pl_link.items():
        if state=='base':restated_by[target].append(obs_of[key])
        else:
            cand=', '.join(obs_of[c] for c in target)
            python_issues.append((key[0],f'PY-PL-{key[1]}',
                f'{obs_of[key]} is worded as a {pl_wording[key]} (period-limited) royalty. '
                +(f'More than one possible base row ({cand}), so it is NOT linked; check which row it restates.' if target
                  else 'No base row of the same royalty family was found, so it is NOT linked.')
                +' Python rule: it is marked not usable as a benchmark until a person has looked.'))

    for t in terms:
        did=t['Document_ID']; doc=docs.get(did,{})
        ex=first_readings.get(did) or {}; agreement=ex.get('agreement') or {}
        field_refs=agreement.get('field_evidence') or {}
        field_ev=lambda *keys:[(evid_by_doc.get((did,i)) or {}).get('Exact_Quotation') or ''
                               for k in keys for i in _ids(field_refs.get(k))]
        nature=agreement.get('licensed_ip_nature')
        nature='NOT_ASSESSED' if nature is None else nature
        ia_detail=agreement.get('licensed_ip_nature_details')
        inferred_basis=agreement.get('licensed_ip_nature_basis')=='INFERRED'
        components=_ia_components(agreement)
        ia_texts=lambda:field_ev('licensed_ip','licensed_ip_nature','licensed_ip_components','licensed_ip_nature_details','duration')
        if nature=='MIXED':
            if components:   # the reader's own list
                nature='MIXED: '+', '.join(components)+(' (inferred)' if inferred_basis else '')
            else:            # reader said MIXED without listing; add the components as a labelled keyword hint
                hint=_ia_keyword_hint(ia_texts())
                if hint:
                    nature='MIXED: '+', '.join(hint[1])+' (keyword hint)'
                    ia_detail=(str(ia_detail)+' | ' if ia_detail else '')+hint[2]
                elif inferred_basis:nature='MIXED (inferred)'
        elif nature=='UNDETERMINED' or (nature=='NOT_ASSESSED' and agreement):
            hint=_ia_keyword_hint(ia_texts())
            if hint:  # never overrides a reader's own non-UNDETERMINED value
                nature=(f'MIXED: {", ".join(hint[1])}' if hint[0]=='MIXED' else hint[0])+' (keyword hint)'
                ia_detail=(str(ia_detail)+' | ' if ia_detail else '')+hint[2]
        elif nature!='NOT_ASSESSED' and inferred_basis:
            nature=f'{nature} (inferred)'
        related=agreement.get('related_party')
        if related is None:
            related='NOT_ASSESSED'
            if agreement:
                word=_related_hint(field_ev('licensed_ip','contractual_status') + [e.get('Exact_Quotation') or '' for (d_,_i),e in evid_by_doc.items() if d_==did]
                                   + list(source_texts.get(did) or []))
                if word:related=f'YES (keyword hint: "{word}")'
        tier_text=_tier_summary(tiers_by_term.get((did,t.get('Term_ID')),[])) if t.get('Disclosure_Status') not in ('REDACTED','AMBIGUOUS','NOT_VERIFIED') else None
        grant_text=' '.join(list(source_texts.get(did) or [])+[e.get('Exact_Quotation') or '' for (d_,_i),e in evid_by_doc.items() if d_==did])
        usable,usable_note=benchmark_usable(t,related,doc.get('Contract_Status'),nature=agreement.get('licensed_ip_nature'),
                                            grant_found=(grant_hits(grant_text)>0 if grant_text.strip() else None),
                                            qc_state=t.get('QC_State') or doc.get('Extraction_Status'),
                                            record_errors=_record_error_codes(t.get('Term_ID'),(source_errors or {}).get(did)),
                                            tier_summary=tier_text,unresolved=(did,t.get('Term_ID')) in unresolved_terms,
                                            period_limited=((pl_wording[(did,t.get('Term_ID'))],
                                                             obs_of[pl_link[(did,t.get('Term_ID'))][1]] if pl_link[(did,t.get('Term_ID'))][0]=='base' else None)
                                                            if pl_wording.get((did,t.get('Term_ID'))) else None))
        key=(did,t.get('Term_ID'))
        if pl_wording.get(key):
            pl_cell=f'YES ({pl_wording[key]})'
            link_cell=obs_of[pl_link[key][1]] if pl_link[key][0]=='base' else 'not linked \u2013 see sheet 05'
        elif restated_by.get(key):
            pl_cell=''; link_cell='has period-limited restatement: '+', '.join(restated_by[key])
        else:pl_cell=link_cell=''
        license_text=doc.get('Licensed_IP') or agreement.get('licensed_ip')
        rights=agreement.get('sublicensing_rights') or 'NOT_ASSESSED'
        material=agreement.get('other_material_terms') or []
        n_cond=len(conditions.get((did,t['Term_ID']),[])); n_adj=len(adjustments.get((did,t['Term_ID']),[]))
        summary=key_terms_summary(material)   # KEY terms only (short); everything stays in sheet 06
        if n_cond or n_adj:summary+=f'; {n_cond} condition(s), {n_adj} adjustment(s) \u2013 see sheet 02'
        summary=_short(summary,120)
        payments_present=payments_by_doc.get(did,[])
        min_hint=_payment_summary(payments_present,{'MINIMUM_ROYALTY','GUARANTEE'},minimum=True)
        cap_hint=_payment_summary(payments_present,{'CAP'},royalty_only=True)
        advance_hint=_payment_summary(payments_present,{'ADVANCE'})
        # v0.13.12: a minimum whose own record says it is paid in advance fills the advance field (with its payment ID);
        # a plain "on the Effective Date" does not. A signing fee is never reinterpreted: UPFRONT stays UPFRONT.
        pay_quotes=lambda p:[(evid_by_doc.get((did,i)) or {}).get('Exact_Quotation') for i in _ids(p.get('Evidence_IDs'))]
        from_minimum=_advance_from_minimum(payments_present,pay_quotes)
        if from_minimum:
            advance_hint='; '.join(([] if advance_hint=='NOT_ASSESSED' else [advance_hint])+from_minimum)
        upfront_hint=_payment_summary(payments_present,{'UPFRONT'})
        n_pay=len(payments_present)
        checked=lambda what:f'NOT_ASSESSED (checked {n_pay} payment record{"" if n_pay==1 else "s"}: none is {what}; absence is not proven by one reading)'
        if advance_hint=='NOT_ASSESSED' and n_pay:advance_hint=checked('an advance or prepayment')
        if upfront_hint=='NOT_ASSESSED' and n_pay:upfront_hint=checked('an upfront or signing fee')
        payment_ids=_payment_references(payments_present)
        exclusivity_scope=agreement.get('exclusivity_scope') or 'NOT_ASSESSED'
        rate_ids=_join(t.get('Rate_Evidence_IDs'))
        quote=shown_quote(_best_evidence(_ids(t.get('Rate_Evidence_IDs')),did,evid_by_doc,t.get('Rate_Value_Text')))
        rate_reported=t.get('Rate_Value_Text')
        if rate_reported in (None,'') and tier_text:
            # Tiered / hybrid / formula term with disclosed tiers: the numeric cell stays blank (never one collapsed
            # number, sorting unaffected); the reported-rate cell says what the tiers span.
            rate_reported=f"{str(t.get('Structure') or 'TIERED').upper()} {tier_text} \u2013 see sheet 02"
        action='Review CORE differences' if doc.get('Extraction_Status')=='TWO_READERS_DIFFER' else 'Point-of-use source review'
        result[NAMES[0]].append([
            t.get('Observation_ID'),nature,license_text,_percent_cell(t),per_unit_rate(t,quotes_of_term(t)),usable,usable_note,pl_cell,link_cell,rate_reported,t.get('Family'),t.get('Structure'),
            t.get('Rate_Unit'),t.get('Royalty_Base'),t.get('Product_Scope'),t.get('Licensor') or doc.get('Licensor'),
            t.get('Licensee') or doc.get('Licensee'),related,doc.get('Industry'),t.get('Territory') or doc.get('Territory'),
            doc.get('Exclusivity') if doc.get('Exclusivity') is not None else 'NOT_ASSESSED',
            _short(exclusivity_scope),rights,doc.get('Executed') or agreement.get('execution_date'),doc.get('Effective'),
            doc.get('Filing_Date'),_short(doc.get('Contract_Status')),t.get('Effective_Period'),min_hint,cap_hint,advance_hint,
            upfront_hint,summary,payment_ids,rate_ids,quote,
            t.get('Source_URL'),t.get('Disclosure_Status'),doc.get('Second_AI_Review_Status'),
            t.get('QC_State'),action,t.get('Agreement_ID'),did,
            _join(list(dict.fromkeys(_ids(field_refs.get('licensed_ip_nature'))+_ids(field_refs.get('licensed_ip_components'))))),_join(field_refs.get('sublicensing_rights')),
            _join(field_refs.get('exclusivity')),
            _join(field_refs.get('exclusivity_scope')),
            _join([x for m in material for x in (m.get('evidence_ids') or [])]),
            ia_detail,doc.get('Contract_Status'),exclusivity_scope])

    other_terms=[]
    for did,ex in first_readings.items():
        agreement=(ex or {}).get('agreement') or {}
        doc=docs.get(did,{})
        if not any(t['Document_ID']==did for t in terms):continue   # same agreements as sheet 01
        first_term=next(t for t in terms if t['Document_ID']==did)
        for m in agreement.get('other_material_terms') or []:
            ids=[str(x) for x in (m.get('evidence_ids') or [])]
            quote=(evid_by_doc.get((did,ids[0])) or {}).get('Exact_Quotation') if ids else ''
            tier,_label=classify_other_term(m.get('category'),m.get('text'))
            other_terms.append((TIER_ORDER[tier],[first_term.get('Agreement_ID'),did,agreement.get('licensor') or doc.get('Licensor'),
                agreement.get('licensee') or doc.get('Licensee'),m.get('category','OTHER'),tier,m.get('text'),
                _join(ids),quote,doc.get('Source_URL') or first_term.get('Source_URL')]))
    # KEY first, then SUPPLEMENTARY, then ADMIN; stable inside a tier (sorted() keeps reading order).
    result[NAMES[5]].extend(row for _rank,row in sorted(other_terms,key=lambda x:x[0]))

    for row in _records(rows,'Tiers'):
        result[NAMES[1]].append(['TIER',row.get('Observation_ID'),row.get('Term_ID'),row.get('Sequence'),
             row.get('Rate_Value_Text'),_percent_cell(row),row.get('Rate_Unit'),per_unit_rate(row),
             row.get('Lower_Threshold_Text'),row.get('Upper_Threshold_Text'),
             'Calculation: '+_join(row.get('Calculation'))+'; Period: '+_join(row.get('Measurement_Period'))+
             '; Threshold basis: '+_join(row.get('Threshold_Basis')),
             row.get('Evidence_IDs'),row.get('Source_URL'),row.get('Document_ID'),row.get('QC_State'),
             'Tier bounds are quoted, not inferred'])
    for table,record_type,body in (('Conditions','CONDITION','Condition_Text'),('Adjustments','ADJUSTMENT','Adjustment_Description')):
        for row in _records(rows,table):
            result[NAMES[1]].append([record_type,_observation_reference(row['Term_ID'],row['Document_ID']),
                row.get('Term_ID'),None,None,None,None,None,None,None,row.get(body),row.get('Evidence_IDs'),
                row.get('Source_URL'),row.get('Document_ID'),(docs.get(row['Document_ID']) or {}).get('Extraction_Status'),
                'As extracted; no inferred economics'])

    for p in payments:
        doc=docs.get(p['Document_ID'],{})
        q=shown_quote(_best_evidence(_ids(p.get('Evidence_IDs')),p['Document_ID'],evid_by_doc,p.get('Amount_Text'),
                                     figures=_figures_in(p.get('Basis'),p.get('Condition')) if p.get('Amount_Text') in (None,'') else None)) or None
        result[NAMES[2]].append([p.get('Payment_ID'),p.get('Kind'),p.get('Amount_Text'),
            p.get('Amount_Numeric'),p.get('Currency'),p.get('Basis'),p.get('Condition'),
            p.get('Evidence_IDs'),q,p.get('Source_URL'),p.get('QC_State'),p.get('Licensor') or doc.get('Licensor'),
            p.get('Licensee') or doc.get('Licensee'),p.get('Disclosure_Status'),p.get('Document_ID')])

    for e in evid:
        result[NAMES[3]].append([e.get('Evidence_ID'),e.get('Role'),e.get('Passage_ID'),e.get('Passage_Section'),
            e.get('Exact_Quotation'),_join(links.get((e['Document_ID'],e['Evidence_ID']),[])),
            e.get('Source_URL'),e.get('Extraction_SHA256'),e.get('Document_ID')])

    for r in _records(rows,'Reader Check'):
        result[NAMES[4]].append(['READER_CHECK',r.get('Document_ID'),r.get('State'),
            r.get('Facts_Both_Readers_Recorded'),r.get('Meaning'),r.get('First_Reader'),r.get('Second_Reader'),
            None,None,None,r.get('Source_URL'),r.get('What_To_Do')])
    for r in _records(rows,'Reader Differences'):
        result[NAMES[4]].append(['READER_DIFFERENCE',r.get('Document_ID'),r.get('Level'),r.get('Value'),
            r.get('What_Differs'),r.get('First_Reader'),r.get('Second_Reader'),r.get('Passage_ID'),
            r.get('Section'),r.get('Source_Excerpt'),r.get('Source_URL'), 'Source review required' if r.get('Level')=='CORE' else 'Review if material'])
    for r in _records(rows,'Open Issues'):
        result[NAMES[4]].append(['OPEN_ISSUE',r.get('Document_ID'),r.get('Severity'),r.get('Issue_ID'),
            r.get('Description'),r.get('Kind'),r.get('Status'),r.get('Source_Passage_IDs'),
            None,None,r.get('Source_URL'),'Review open issue'])
    for did_,issue_id,text in python_issues:     # raised by the export rules above (not read from the reading)
        result[NAMES[4]].append(['OPEN_ISSUE',did_,'MEDIUM',issue_id,text,'PERIOD_LIMITED_LINK_UNRESOLVED','OPEN',None,
                                 None,None,(docs.get(did_) or {}).get('Source_URL'),'Review open issue'])
    for r in _records(rows,'QC'):
        result[NAMES[4]].append(['DETERMINISTIC_QC',r.get('Document_ID'),r.get('State'),r.get('Errors'),
            'Warnings: '+_join(r.get('Warnings'))+'; read scope: '+_join(r.get('Read_Scope')),
            r.get('Deterministic_Result'),r.get('Second_AI_Review_Status'),None,None,None,
            r.get('Source_URL'),'Machine checks are not full-contract recall'])
    for r in _records(rows,'Amendments'):
        result[NAMES[4]].append(['AMENDMENT',r.get('From_Document_ID'),r.get('Evidence_Status'),r.get('To_Document_ID'),
            r.get('Relation'),r.get('Supersession_Scope'),r.get('Basis'),None,None,None,None,
            'No automatic effective-rate inference'])
    for r in _records(rows,'Pending Jobs'):
        result[NAMES[4]].append(['PROCESSING',r.get('Document_ID'),r.get('State'),r.get('Attempt_Count'),
            r.get('What_Next'),None,None,None,None,None,r.get('Source_URL'), 'Follow M13 run status'])

    return {name:[[_safe(x) for x in row] for row in result[name]] for name in NAMES}


SUMMARY_NAME = '00 Run Summary'
SUMMARY_HEADERS = ['Document ID','Company / licensor \u2013 licensee','SEC source link','Status','QC state','Royalty rows','Note']


ROW_HEIGHT_MAX=150     # points (about 11 lines of Arial 10)
_LINE_POINTS=12.75     # one wrapped line of Arial 10
_CHARS_PER_WIDTH=1.1   # Arial 10 characters that fit in one Excel column-width unit (conservative: leaves room for word wrap)
_NO_HEIGHT_HEADER=re.compile(r'\bIDs?\b|\bSHA\b|\blink\b',re.I)   # ID lists / URLs would make every row tall


def estimate_row_height(values, widths, minimum=30, maximum=ROW_HEIGHT_MAX, skip=()):
    """Row height in points for wrapped text: the tallest cell decides (lines = text length / column width, per paragraph).

    values and widths are parallel lists (column widths in Excel units); columns whose index is in skip (ID lists, URLs)
    are ignored. Clamped to minimum..maximum; text longer than the maximum is still wrapped, and the full text stays in the cell."""
    lines=1
    for i,(value,width) in enumerate(zip(values,widths)):
        if i in skip or value is None or isinstance(value,(int,float)):continue
        per_line=max(1,int(width*_CHARS_PER_WIDTH))
        n=sum(max(1,-(-len(part)//per_line)) for part in str(value).split('\n'))
        lines=max(lines,n)
    return float(min(maximum,max(minimum,lines*_LINE_POINTS+6)))


def _write_run_summary(wb, summary):
    """Sheet 00: one row per run folder of the batch, so an unfinished or failed agreement is never silent.

    summary = {'counts': str, 'rows': [[...SUMMARY_HEADERS...]], 'candidates': [(status, count, meaning)], 'candidate_line': str}
    """
    from .m3_export import official_sec_url
    from .m3_workbook import _clean
    from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
    from openpyxl.utils import get_column_letter
    orange='FD5108'; black='000000'; light='F5F7F8'
    ws=wb.create_sheet(SUMMARY_NAME,0)
    ws.sheet_view.showGridLines=False
    ws.sheet_properties.tabColor=orange
    n=len(SUMMARY_HEADERS); last_col=get_column_letter(n)
    ws.cell(1,1,'RUN SUMMARY  |  Every agreement of this batch').font=Font(name='Georgia',size=15,bold=True,color=black)
    ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=min(n,7)); ws.row_dimensions[1].height=29
    for c in range(1,n+1):ws.cell(2,c).border=Border(bottom=Side(style='medium',color=orange))
    ws.row_dimensions[2].height=8
    lines=['One row per run folder; agreements that are not finished or failed are listed here and are NOT in sheets 01-06',
           summary.get('counts') or '',
           summary.get('candidate_line') or 'Candidates the batch did not read: not recorded for this workbook']
    for i,text in enumerate(lines,3):
        cell=ws.cell(i,1,text);cell.font=Font(name='Arial',size=10,bold=(i==4),color=black)
        cell.alignment=Alignment(vertical='center',wrap_text=True)
        ws.merge_cells(start_row=i,start_column=1,end_row=i,end_column=n);ws.row_dimensions[i].height=20 if i!=5 else 34
    ws.row_dimensions[6].height=8
    for c,title in enumerate(SUMMARY_HEADERS,1):
        cell=ws.cell(7,c,title);cell.font=Font(name='Arial',size=10,bold=True,color=black)
        cell.fill=PatternFill('solid',fgColor='FFFFFF');cell.alignment=Alignment(vertical='center',wrap_text=True)
        cell.border=Border(top=Side(style='medium',color=orange),bottom=Side(style='medium',color=orange))
        ws.column_dimensions[get_column_letter(c)].width=[26,44,38,40,30,14,50][c-1]
    ws.row_dimensions[7].height=37
    rows=summary.get('rows') or []
    summary_widths=[26,44,38,40,30,14,50]
    for ridx,row in enumerate(rows,8):
        ws.row_dimensions[ridx].height=estimate_row_height(row,summary_widths,minimum=33,skip={2})
        for c,val in enumerate(row,1):
            cell=ws.cell(ridx,c,_clean(val))
            if isinstance(cell.value,str):cell.data_type='s'
            cell.font=Font(name='Arial',size=10,bold=(c==4 and not str(val).startswith('EXPORTED')),color=black)
            cell.alignment=Alignment(vertical='top',wrap_text=True)
            if ridx%2==1:cell.fill=PatternFill('solid',fgColor=light)
            if isinstance(cell.value,str) and 'sec.gov/' in cell.value and official_sec_url(cell.value):cell.hyperlink=cell.value
    end=7+len(rows)
    if rows:ws.auto_filter.ref=f'A7:{last_col}{end}'
    cands=summary.get('candidates') or []
    if cands:
        r=end+2
        ws.cell(r,1,'Candidates not read, by register status').font=Font(name='Arial',size=10,bold=True,color=black)
        for i,(status,count,meaning) in enumerate(cands,r+1):
            ws.cell(i,1,status).font=Font(name='Arial',size=10,color=black)
            ws.cell(i,2,count).font=Font(name='Arial',size=10,color=black)
            ws.cell(i,2).alignment=Alignment(horizontal='left')
            m=ws.cell(i,3,meaning);m.font=Font(name='Arial',size=10,color=black);m.alignment=Alignment(wrap_text=True,vertical='top')
            ws.merge_cells(start_row=i,start_column=3,end_row=i,end_column=n);ws.row_dimensions[i].height=20
    ws.freeze_panes='B8'
    ws.sheet_view.zoomScale=85
    ws.page_setup.orientation='landscape'


def write_research_xlsx(legacy_rows: dict, destination, first_readings: dict | None = None, source_texts: dict | None = None,
                        source_errors: dict | None = None, run_summary: dict | None = None):
    """Optional dependency matches existing M13 writer; no network or model calls."""
    from .m3_export import official_sec_url
    from .m3_workbook import _clean
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
        from openpyxl.utils import get_column_letter
    except ImportError as exc:
        raise RuntimeError('M13 research XLSX needs the existing optional openpyxl dependency') from exc
    sheets=research_rows(legacy_rows,first_readings,source_texts,source_errors)
    wb=Workbook();wb.remove(wb.active)
    orange='FD5108'; gray='DFE3E6'; light='F5F7F8'; black='000000'; grey='808080'
    for idx,(name,matrix) in enumerate(sheets.items()):
        ws=wb.create_sheet(name)
        ws.sheet_view.showGridLines=False
        ws.sheet_properties.tabColor=(orange if idx==0 else 'FFE8D4' if idx<3 else 'FFCDA8')
        n=len(matrix[0]); last_col=get_column_letter(n)
        title=['ROYALTY DATABASE  |  Valuation research','TIERS & ECONOMIC MECHANICS',
               'OTHER PAYMENTS & GUARANTEES','SOURCE EVIDENCE REGISTER',
               'READER & SOURCE QC  |  ACTION REGISTER','OTHER MATERIAL TERMS  |  One row per term'][idx]
        ws.cell(1,1,title).font=Font(name='Georgia',size=15,bold=True,color=black)
        ws.merge_cells(start_row=1,start_column=1,end_row=1,end_column=min(n,7))
        ws.row_dimensions[1].height=29
        for c in range(1,n+1):
            ws.cell(2,c).border=Border(bottom=Side(style='medium',color=orange))
        ws.row_dimensions[2].height=8
        intro=['One row per source-document royalty term; NOT a unique transaction benchmark',
               'Separate tiers, conditions and rate adjustments linked to original observations',
               'One record per extracted fee or guarantee; totals may duplicate component amounts',
               'Original quotations and passage identifiers; do not replace with paraphrases',
               'Machine source checks and reader differences when a second reading was used',
               'Other material terms by valuation relevance (KEY, SUPPLEMENTARY, ADMIN; Python rules, not the reader); sheet 01 summarises only the KEY terms'][idx]
        ws.cell(3,1,intro).font=Font(name='Arial',size=10,color=black)
        ws.merge_cells(start_row=3,start_column=1,end_row=3,end_column=min(n,9))
        ws.cell(4,1,f'{len(matrix)-1} records | source-document-specific | no unverified assumptions auto-filled').font=Font(name='Arial',size=10,bold=True,color=black)
        ws.merge_cells(start_row=4,start_column=1,end_row=4,end_column=min(n,9))
        ws.cell(5,1,('Missing fee categories = NOT_ASSESSED (not zero); agreement-level fees repeat on rate rows, NEVER SUM. Rates are real percentages (30% is stored as 0.30); per-unit / currency rates are in their own column. '
                     'Reader agreement is not proof of recall.' if idx==0 else
                     'Full unmodified M13 technical evidence remains in rows.json and optional Detailed XLSX.')).font=Font(name='Arial',size=10,color=black)
        ws.merge_cells(start_row=5,start_column=1,end_row=5,end_column=min(n,9))
        ws.row_dimensions[5].height=20
        for c,title in enumerate(matrix[0],1):
            cell=ws.cell(7,c,_clean(title)); cell.font=Font(name='Arial',size=10,bold=True,color=black)
            cell.fill=PatternFill('solid',fgColor='FFFFFF')
            cell.alignment=Alignment(vertical='center',wrap_text=True)
            cell.border=Border(top=Side(style='medium',color=orange),bottom=Side(style='medium',color=orange))
            width=24
            if any(tok in title.lower() for tok in ['quotation','quote','description','mechanics','material terms','text','note','rights','base','source','licensed intangible','product','payment','guarantee','cap','fee']):width=38
            elif any(tok in title.lower() for tok in ['id','document','licensee','licensor','territory','evidence']):width=26
            if title in ('Royalty rate (%)','Rate numeric','Amount numeric'):width=16
            if title=='Per-unit / currency rate':width=22
            ws.column_dimensions[get_column_letter(c)].width=min(width,45)
        col_widths=[ws.column_dimensions[get_column_letter(c)].width for c in range(1,n+1)]
        no_height={c for c,h in enumerate(matrix[0]) if _NO_HEIGHT_HEADER.search(str(h))}
        ws.row_dimensions[7].height=37
        rate_cols={c for c,h in enumerate(matrix[0],1) if h in RATE_COLUMNS}
        unit_col=matrix[0].index('Rate unit') if 'Rate unit' in matrix[0] else 0
        for ridx,row in enumerate(matrix[1:],8):
            # v0.13.12: wrapped text and a height estimated from the text (was a fixed 33 / 30 points that cut long cells)
            ws.row_dimensions[ridx].height=estimate_row_height(row,col_widths,minimum=33 if idx in (0,4) else 30,skip=no_height)
            admin_row=idx==5 and row[5]==ADMIN
            for c,val in enumerate(row,1):
                cell=ws.cell(ridx,c,_clean(val))
                if isinstance(cell.value,str):cell.data_type='s'
                cell.font=Font(name='Arial',size=10,color=(grey if admin_row else black))
                cell.alignment=Alignment(vertical='top',wrap_text=True)    # top: a clipped cell shows its beginning, not its middle
                if c in rate_cols and isinstance(cell.value,(int,float)) and not isinstance(cell.value,bool) \
                        and str(row[unit_col] or '').upper() in PERCENT_UNITS:
                    # Excel cell holds the real fraction (5 percent-points -> 0.05, shown 5.00%).
                    # Rows.json / CSV keep percent-points; per-unit amounts, FORMULA, UNKNOWN stay as they are.
                    cell.value=percent_points_to_fraction(cell.value)
                    cell.number_format=RATE_NUMBER_FORMAT
                if ridx%2==1:cell.fill=PatternFill('solid',fgColor=light)
                # A subtle separator every fifth row rather than an orange grid.
                if (ridx-7)%5==0:
                    cell.border=Border(bottom=Side(style='hair',color=gray))
                if isinstance(cell.value,str) and title and ('sec.gov/' in cell.value):
                    if official_sec_url(cell.value):cell.hyperlink=cell.value
        if len(matrix)>1:
            ws.auto_filter.ref=f'A7:{last_col}{len(matrix)+6}'
        ws.freeze_panes='D8' if idx==0 else 'C8'
        ws.sheet_view.zoomScale=85
        ws.print_options.horizontalCentered=False
        ws.page_setup.orientation='landscape'
    if run_summary is not None:_write_run_summary(wb,run_summary)
    out=Path(destination);out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_name('.'+out.name+'.tmp.xlsx')
    try:
        wb.save(tmp)
        if tmp.stat().st_size<1000:raise RuntimeError('Empty research workbook')
        tmp.replace(out)
    finally:
        if tmp.exists():tmp.unlink()
    return str(out)
