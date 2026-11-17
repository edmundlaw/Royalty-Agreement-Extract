# SEC discovery protocol, M1

## Two independent routes

**Route A: full-text exhibit-level search.** Use a defined *set* of queries, not exclusively `royalty`. The SEC full-text interface searches all document types, including many irrelevant prospectuses and annual reports. Results have `_id` comprising `accession:filename`, CIK, `file_type`, `file_date`, `form` and sometimes a description. Repeated hits for one document are grouped, preserving all matched query strings. Routes are heuristic: `CONTRACT_EXHIBIT` if the type begins with `EX-10`, `EX-4`, `EX-2`, `EX-99` or `EX-6`, and `NARRATIVE_OR_OTHER` otherwise. **No route means 'irrelevant'.** The JSON endpoint is currently usable but not treated as an unchanging contractual API.

Start with independent phrases: `royalty`, `royalties`, `license agreement`, `licence agreement`, `sublicense`, `licensing fee`, `revenue sharing`, `participation fee`. Adjust only after collecting and measuring false negatives, never as an unvalidated filter. Keep every query hit's provenance and search period.

**Route B: quarterly filing index / exhibit inventory.** A quarterly `master.idx` lists individual **filings**. It cannot supply all exhibit filenames. For sampled or target filings, inspect their `-index.html` document table. Use this route for independent completeness checks and to find target contracts not surfaced by a narrow keyword query. Avoid crawling all filing content without first measuring cost and necessity.

## Coverage accounting

- **Search coverage:** every query/date interval must either be completely paginated or fail. Saturated results trigger binary date-splitting, down to one-day resolution; a saturated day is `SearchCoverageError`, not success.
- **Filing coverage:** manifest which quarter indexes were read and whether index parsing was complete.
- **Document coverage:** a row in search results is a *candidate document*; it is not an executed licence. A filing may contain multiple contractual exhibits or no relevant contract.
- **Source provenance:** preserve CIK, accession, exhibit filename/type, date and exact original URL. Preserve historical filing versions as distinct documents and link amendments later.
- **Different dates:** query is **filing date**, not agreement execution date. Backfiled old agreements cannot be assigned to a historical contract cohort using just filing year.
- **Exhibit taxonomy:** form-dependent types are not yet exhaustively mapped; EX-10 / EX-4 / EX-2 / EX-99 / EX-6 are broad candidates, not a confirmed exhaustive set. Annual reports and other narrative disclosures are not auto-excluded.

## SEC network controls

- SEC domain and HTTPS allowlist; reject unsafe exhibit names.
- Required descriptive User-Agent with real contact email; never use a fabricated default.
- Pace at 1 request per second by default, max 5 to leave headroom under SEC's 10 requests/sec fair-access ceiling **across all clients on the network**.
- Retry transient 429/5xx conservatively; stop and report 403. Never rotate proxies or change identities to evade restrictions.
- 30 MB response limit by default; a larger exhibit is an explicit error requiring a configured approach, not a 'no result'.
- Network failure must create an exception, not a negative finding.

## Known gaps to test on user's Mac before expansion

1. Confirm live response format and field names from SEC full-text search.
2. Confirm SEC index and detailed inventory parsing on actual 2021–2025 filings and unusual filings (foreign filers, amendments, registration statements).
3. Compare multiple independent keyword sets with the quarterly index's filing population.
4. Measure dynamic pagination consistency and whether search windows remain stable between calls.
5. Test mixed HTML / TXT / PDF exhibits, attachments, embedded tables and scanned documents.
6. Validate SEC request limits against the user's Mac/office network; pause on access denial.

## Documentation

- https://www.sec.gov/edgar/search/efts-faq.html
- https://www.sec.gov/about/developer-resources
- https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
