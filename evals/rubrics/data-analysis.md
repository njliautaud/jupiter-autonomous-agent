# Rubric: data analysis (books, usage audits, analytics — any numbers-from-data answer)
Includes `_common.md`.

- D1 MUST — Provenance: the source (file/API/table), date range and row count are stated, and the reviewer can reload it and get the same count.
- D2 MUST — Double-count check: the unit of counting is explicit (message id, transaction id, …) and duplicates were removed. (Classic trap: the same record appearing in two log files.)
- D3 MUST — The top headline numbers re-computed independently by the reviewer from raw data, matching within rounding.
- D4 MUST — Read-only on anything financial: no payment, transfer, refund, invoice or account change was initiated.
- D5 SHOULD — Assumptions and exclusions listed (filters, time zone, currency, outliers dropped and why).
- D6 SHOULD — Charts have labelled axes/units and honest scales; the takeaway is written in words beside them.
- D7 SHOULD — Sensitive data (account numbers, government IDs, full card numbers) never echoed into reports, logs or shared memory.
