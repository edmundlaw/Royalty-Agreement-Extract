# M3 bounded agent chunk contract

Use only when a document cannot be interpreted as a whole. Produce an M2 `make-packets --mode full` packet first. If an individual source passage exceeds the allowed packet size, STOP and flag a source segmentation exception; **never truncate that passage or pretend the missing tail was read**.

For each entry in `packet.chunks`, an agent writes a complete JSON object with these fields:

```json
{
  "schema": "m3-chunk.1",
  "document_id": "EXACT_M1_ID",
  "source_text_sha256": "EXACT_M1_TEXT_HASH",
  "packet_sha256": "SHA256_OF_THE_COMPLETE_PACKET_JSON_USING_PROJECT_CANONICAL_SERIALIZATION",
  "chunk_index": 1,
  "chunk_count": 2,
  "reviewed_passage_ids": ["EXACT_IDS_ASSIGNED_TO_THIS_CHUNK_IN_ORDER"],
  "reader": {"engine": "codex", "model": "actual model name", "run_id": "unique id"},
  "agreement": {"title": null, "field_evidence": {}},
  "royalty_terms": [],
  "other_payments": [],
  "evidence": [],
  "dispositions": [],
  "open_issues": [],
  "amendment_status": "NOT_CHECKED"
}
```

This is a structural example, not an acceptable extraction answer. The schema of inner royalties, payments, evidence, issues and dispositions is **the M2 schema**. Across all chunks, evidence/term/payment/disposition/issue IDs must be globally unique. Each evidence citation must point to a passage inside the chunk that supplied it. A single term may refer to evidence in other chunks, but its record must occur only once. A later semantic review must reconcile terms crossing chunks.

To compute the packet hash reproducibly:

```bash
PYTHONPATH=src python3 -c 'import json,sys;from royalty_research.storage import sha256,json_bytes;print(sha256(json_bytes(json.load(open(sys.argv[1])))))' full_packet.json
```

Merge:

```bash
PYTHONPATH=src python3 -m royalty_research m3-merge-chunks --map full_map.json \
  --packet full_packet.json --chunk chunk_1.json --chunk chunk_2.json \
  --out merged_extraction.json
```

M3 verifies all assigned source passages, text/section metadata, inventory, chunk counts, disjoint reviewed passages, source hashes, unique IDs, coherent agreement header and M2 schema/number/quote/coverage validation. If QC fails, the merged file and `.merge-report.json` remain for correction, with a nonzero exit status. Re-attempting a merge cannot silently overwrite the previous output without `--force`.

**Important:** Exact chunk reconciliation does not prove an AI actually read the text or interpreted the economics correctly. Independently check cross-chunk terms, schedules, conditions and amendments.
