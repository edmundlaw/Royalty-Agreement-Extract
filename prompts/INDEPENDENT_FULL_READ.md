# Blind full-document omission search (independent second reader)

You have a numbered FULL-document source packet (possibly multiple chunks), not the first reader's answers. You must independently identify every distinct licensing payment obligation, royalty rate, tier, sublicense share, minimum guarantee, reduction, threshold, exception, and redacted term in the entire document.

Read **all** packet chunks. Make a numbered list of each relevant section and quote its supporting phrase exactly. Distinguish running royalties from ownership percentages, late-payment interest and audit thresholds. Track referenced sections/definitions/schedules. State if any passage was not read or if original PDF rendering was defective.

Also independently note the type of licensed IP, territorial/field rights, exclusivity, sublicensing, termination/renewal and other material limitations when stated. Use quoted evidence for the optional `agreement` licensing fields; leave unsupported values unknown rather than guessing. These fields are not yet included in M13's numerical reader-comparison outcome.

Produce a fresh `m2_extraction.schema.json` JSON result with your own term IDs/evidence and candidate dispositions; do not look at the first reader's output. Mark `FULL_DOCUMENT` only if every mapped passage was actually read, otherwise mark `SELECTED_PASSAGES`, list actual reviewed passage IDs, and open an issue for the gap.

This checks omission risks independently. Agreement of two AI readers is **not** proof of accuracy. If you cannot finish under the subscription limit, save a partial draft labelled incomplete and resume before attempting validation.
