# Seven-agreement royalty rate and IA review

The November 18, 2026 test used one reader per agreement at commit `af59061`. The seven original workbooks contain 17 main-sheet rows. The disclosed headline rates checked below match their source clauses. The main sheet misses a disclosed tier and gives incomplete asset classifications in two cases. The sample does not establish 100% extraction accuracy.

| Agreement | Rate check | Licensed asset check |
| --- | --- | --- |
| [NaturalNano](https://www.sec.gov/Archives/edgar/data/863895/000114420407041119/v083396_ex10-1.htm) | §3.1 gives 5% of net sales and 25% of sublicense consideration. The workbook keeps the two- and three-royalty proration examples as adjustments. | The patent and technical information grants support the mixed patent, know-how, technology and trade secret label. |
| [Laser Lock / Copag](https://www.sec.gov/Archives/edgar/data/1104038/000095011604001037/ex10-6.txt) | §1.01 gives $0.05 per excess unit above 200,000 per royalty period. §9.01 gives a separate royalty-free, non-exclusive improvements licence. That row inherited the wrong exclusivity, minimum and advance. | §§1.03 and 1.07 expressly include design rights. The reader captured them in prose, but the structured label included only patent and technology. |
| [Michigan / Glyconix](https://www.sec.gov/Archives/edgar/data/1303041/000119312506100423/dex108.htm) | §3.1 gives 2% of net sales and 10% of non-sales sublicense revenue. Article 8 divides residual litigation recoveries equally. Those rows had a misleading undisclosed-rate note. | Patent rights. The conditional $100,000 annual fee is recorded on sheets 03 and 06. |
| [Therapeutic Solutions / Emvolio](https://www.sec.gov/Archives/edgar/data/1419051/000107878217000613/f8k051017_ex10z1.htm) | Article III gives 5% of gross sales and 50% of sublicensing receipts. Sheet 06 records the reverse royalty-free grant following licensee termination or conversion. Sheet 01 has only the two paying rows. | Patent rights for the primary grant. The contingent reverse grant includes improvements and related know-how. |
| [UNeMed / Telomolecular](https://www.sec.gov/Archives/edgar/data/1353532/000135353207000003/unemed.htm) | §§4.1–4.2 give 5% of cosmeceutical net sales, 4% on other licensed products and 30% of sublicense income. | Patent rights. |
| [Novo Nordisk / Amicus](https://www.sec.gov/Archives/edgar/data/1178879/000095012306006534/y20474exv10w6.txt) | Table 1 withholds all 18 percentages. The workbook preserves the tiers but also exports an unrated placeholder for the same annual-net-sales economics. Exclude it from counts pending review. | §2.1.9 supports patents, know-how and technical information. The numerical rates cannot be scored from this filing. |
| [Cyclerion / Akebia amendment](https://www.sec.gov/Archives/edgar/data/1755237/000119312524280125/d856941dex101.htm) | Amended Table 7.5 discloses 20% in its fourth tier. The original workbook has it on sheet 02. Sheet 01 leaves the reported rate blank. The applicable threshold is redacted. | The amendment supports a patent inference. §§1.28 and 8.1 of the original licence expressly include know-how in the grant. [Original licence](https://www.sec.gov/Archives/edgar/data/1755237/000156459021039205/cycn-ex102_241.htm) |

## What changed in v0.13.13

The main sheet distinguishes fully redacted schedules from partly disclosed tiers. It preserves the separate per-unit and percentage columns. Potential territorial duplicates now generate an open, high-priority issue. The exporter uses rate evidence to identify the non-exclusive royalty-free row and separates litigation recovery splits from missing royalty rates.

The reader can classify design rights and is asked to identify incomplete amendment-only evidence and conditional grantbacks. Two-reader comparisons now flag disagreements about the IA category or components as core differences. The filing-date fallback uses supplied filing metadata. When an effective date is missing and the source points to the last signature, the workbook flags the recorded signing date for review.

## Verification and limits

The review compared the original workbooks with public filings. The revised exporter was exercised using values reconstructed from all seven workbooks. Regression tests cover the production export and capture the source conditions above. The original raw reader responses were unavailable. A replay can verify how an extracted fact is displayed. It cannot measure whether a fresh reader will find that fact or every component of the grant.

For valuation use, count a row as verified once a reviewer has checked the operative grant and definitions, the rate, its base, unit, tiers, conditions and payment direction. Track source-redacted rates and missing original agreements separately. Other-term accuracy was not measured in this review.
