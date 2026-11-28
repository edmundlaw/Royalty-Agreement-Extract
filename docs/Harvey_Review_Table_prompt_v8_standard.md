# Harvey Review Table – SEC Royalty Exhibits (v8, standard prompt for all batches 2001–2026)

## Before uploading
- Upload only the .htm/.html exhibits. Do not upload the 00_SEC_SOURCE_MAP.csv files or the _admin folder (if they are uploaded by mistake, their rows are removed when combining).
- After the run, check that the number of rows equals the number of uploaded exhibits.
- Do not add a Source URL column. Rows are matched to SEC URLs afterwards from the filename.
- Use the same 28 columns, in the same order and with the same names, for every batch so results can be combined.

## Rules for every column
- Use only this document. Do not use outside knowledge or other filings, and never guess a rate or amount.
- Plain text only: no citation markers, footnote numbers or links.
- One row per document. If the document contains several agreements, report the main royalty-bearing one and mention the others in column 28.
- Write only "—" when the document does not state the item. Do not write "None stated", "Not specified" or "Total: —".
- Classification columns: choose exactly one option, never several.
- Keep to the word limits. Put any extra detail in column 28.
- Treat blanked-out terms such as [***], [*], ***, [Redacted] or "Confidential treatment requested" as redacted; write "redacted" (lower case).
- Percentages: write as a number with a % sign, e.g. "6.5%". Convert written rates: "five percent" = 5%; "one-half of one percent" = 0.5%; 250 basis points = 2.5%.
- Money: write the currency code, not a symbol: "USD 40,000" for amounts under 1 million, "USD 4.5m" for 1 million or more, "up to USD 30m". Keep shares as a share count, e.g. "3,458,033 shares".
- Older or scanned filings may contain OCR spacing errors (e.g. "3 .5 %", "royal ty"). Read through them; quote clauses as they appear.

## Columns (one column per item; format in brackets)

### Identification

**1. Usable rate** `[Classification: Yes / Redacted / Per-unit only / Sublicence only / No]`  
Yes only if this document states a numerical percentage royalty on sales, revenue or production AND what it is a percentage of (e.g. net sales). Redacted = a rate exists but is blanked out. Per-unit only = a fixed amount per unit. Sublicence only = the only stated percentage is a share of sublicensing income. No = anything else, including CREFC licence fees, interest, milestones, profit or revenue splits, earn-outs, contingent value rights, and documents that only mention royalties. If column 12 is "—" or "redacted", column 1 cannot be Yes.

**2. Source type** `[Classification: Agreement / Amendment / Description in filing]`  
Agreement = the agreement itself, including an amended and restated agreement that sets out the full terms. Amendment = an amendment or side letter that changes only some terms. Description in filing = a prospectus, annual report, technical report or other document that describes an agreement.

**3. Agreement title** `[Free text]`  
Max 15 words. The title of the royalty-bearing agreement exactly as stated, including amendment number if any. If there is no royalty-bearing agreement, give the document's own title.

**4. Transaction type** `[Free text]`  
Classify the royalty arrangement itself, not the document it appears in. Answer with exactly one of: IP licence / Collaboration / Assignment / Franchise / Royalty purchase or financing / Production royalty (NSR/ORRI). If none fits, write "Other: " plus at most 5 words.

**5. Agreement date** `[Date]`  
Date of the royalty-bearing agreement (for an amendment, the amendment date).

**6. Licensor** `[Free text]`  
Company or institution name only; the party receiving the royalty. For a two-way licence, give the party receiving the main royalty and note the reverse royalty in column 28.

**7. Licensee** `[Free text]`  
Company name only; the party paying the royalty.

### Licensed IP

**8. IP type** `[Free text]`  
Answer with one or more of: Patent / Know-how / Technology / Trademark or brand name / Software / Copyright, joined with " + " and the main one first (e.g. "Patent + Know-how"). For production royalties write "Mineral or resource rights". If none fits, write "Other: " plus at most 3 words.

**9. Licensed IP description** `[Free text]`  
Max 30 words. What is licensed and for what product, field of use or application.

**10. Industry (S&P Capital IQ)** `[Free text]`  
Classify the licensed product or field of use (not the contracting companies) using the S&P Capital IQ industry classification (GICS-based). Answer as "Sector > Industry" at the industry level, e.g. "Health Care > Pharmaceuticals", "Health Care > Biotechnology" or "Consumer Discretionary > Hotels, Restaurants & Leisure". Sector must be one of: Energy / Materials / Industrials / Consumer Discretionary / Consumer Staples / Health Care / Financials / Information Technology / Communication Services / Utilities / Real Estate. If the field of use is unclear, give the closest fit and add "(inferred)".

**11. Development stage at signing** `[Classification: Early stage / Development / Commercial / Not stated / Not applicable]`  
Stage of the licensed product when the agreement was signed. Early stage = research, discovery or pre-clinical. Development = clinical trials, regulatory review or otherwise not yet sold. Commercial = already approved or sold. Not applicable = e.g. production royalties.

### Royalty

**12. Royalty rate (%)** `[Free text]`  
The royalty rate on sales, revenue or production, e.g. "6.5%". If tiered or stepped, give the first-tier (base) rate only. If several products have different rates, give the rate for the main licensed product. Write one percentage only, with no words, conditions or second rate (e.g. "6.5%", not "6.5%; 5% after expiry"); put other rates in column 15 or 16. Write "redacted" or "—" as applicable; if an amendment does not restate the rate, write "—". Do not include sublicensing shares, milestones or revenue splits here.

**13. Royalty basis** `[Free text]`  
What the rate in column 12 is a percentage of. Answer with exactly one of: Net Sales / Gross Sales / Net Revenue / Gross Revenue / Net Smelter Returns / Not stated. Use Net Sales for equivalent defined terms such as "Net Selling Price" or "Net Invoice Price". If none fits, write "Other: " plus at most 6 words (e.g. "Other: gross overriding revenue").

**14. Royalty structure** `[Classification: Flat / Tiered / Stepped / Not stated]`  
Tiered = rate depends on sales volume. Stepped = rate changes over time or on an event (e.g. patent expiry, payment cap). If both apply, choose Tiered and describe the step in column 16.

**15. Tier detail** `[Free text]`  
Only if tiered or stepped: list every tier briefly, max 25 words (e.g. "5% to USD 100m; 7% USD 100m-250m; 9% above USD 250m"). Write "—" if flat.

**16. Royalty reductions** `[Free text]`  
Max 20 words. Events that reduce the rate, with the reduced rate if stated (e.g. "Reduced to 3% after patent expiry; up to 50% offset for third-party royalties").

**17. Royalty term** `[Free text]`  
Max 15 words. How long royalties are payable (e.g. "10 years from first commercial sale", "until last patent expires, country by country").

**18. Minimum royalty** `[Free text]`  
Annual or other minimum royalty amount, e.g. "USD 0.1m per year from year 3". Write "redacted" or "—" as applicable.

**19. Sublicensing royalty rate (%)** `[Free text]`  
The licensor's share of sublicensing royalties or sublicensing income, e.g. "20%". If tiered (e.g. by development stage), give the first-tier rate. If there are several sublicence-type shares, use the share of sublicensing royalties or income, and put shares of sale, change-of-control or other non-royalty proceeds in column 27. Write "redacted" or "—" as applicable.

**20. Sublicensing basis** `[Free text]`  
What the rate in column 19 is a percentage of, max 6 words (e.g. "Sublicense income", "Sublicensee royalties"). Write "—" if none.

### Other payments

**21. Upfront payment** `[Free text]`  
Cash or fee payable on signing or shortly after, e.g. "USD 4.5m". Write "redacted" or "—" as applicable.

**22. Milestone payments** `[Free text]`  
Max 20 words. Total and type, e.g. "Up to USD 30m: development USD 10m, regulatory USD 15m, sales USD 5m". Write "redacted" or "—" as applicable.

**23. Equity consideration** `[Free text]`  
Shares, warrants or equity stake given to the licensor, e.g. "3,458,033 shares", "10% equity stake". Write "—" if none.

### Scope

**24. Exclusivity** `[Classification: Exclusive / Non-exclusive / Sole / Co-exclusive / Not stated]`  
If different fields or territories differ, choose the one for the main licensed product.

**25. Territory** `[Free text]`  
Max 8 words, e.g. "Worldwide", "United States", "China, Hong Kong, Macau".

### Evidence and detail

**26. Rate clause** `[Free text]`  
Quote the exact sentence that states the column 12 rate, max 40 words. Write "—" if none.

**27. Other terms affecting the rate** `[Free text]`  
Max 25 words. Anything else that changes the economics, e.g. cost sharing, who pays patent costs, buy-out option, royalty cap, non-royalty proceeds share, grant-back of improvements.

**28. Detailed summary** `[Free text]`  
Max 150 words, as short bullet points. Summarise the commercial terms relevant to the royalty: parties and their roles, licensed IP and field, all royalty rates and tiers with their basis, royalty term and reductions, upfront, milestone and equity payments, minimum royalties, sublicensing share, exclusivity, territory, and termination. For an amendment, state what it changes. Mention any other agreements or reverse royalties in the document. Use only what the document states. Do not repeat the Rate clause quote.

## After export
Filter column 1 to "Yes" for the rows to read. Use column 26 to check each rate against the agreement text.
Compact view: hide columns 3, 9, 15, 16, 17, 20, 27 and 28; unhide them when you need the detail.
The same deal may appear in several rows (agreement, amendments and descriptions in later filings); duplicates are removed and % values converted to numbers when the batches are combined.
