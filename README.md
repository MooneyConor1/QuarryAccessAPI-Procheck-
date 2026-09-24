# Quarry Access Check API

A FastAPI service with a single endpoint: given a person, a site, and a
timestamp, determine whether entry should be granted.

## Running it

```bash
pip install fastapi uvicorn
uvicorn main:app --reload
```

Requires `data/site_requirements.csv` and `data/person_accreditations.csv`
alongside `main.py`. Interactive docs at `http://127.0.0.1:8000/docs`.

## Endpoint

**`POST /checks`**

```json
// Request
{
  "person_id": "P-123",
  "site_id": "S-001",
  "checked_at": "2026-09-24T09:30:00"
}
```

```json
// Response
{
  "outcome": "Amber",
  "person_id": "P-123",
  "site_id": "S-001",
  "checked_at": "2026-09-24T09:30:00",
  "missing_accreditations": [],
  "invalid_accreditations": [],
  "expiring_accreditations": [
    { "accreditation_code": "ACC-002", "accreditation_name": "Working at Heights",
      "expiry_date": "2026-10-10", "days_until_expiry": 16 }
  ]
}
```

- **Red** — a required accreditation is missing or not currently valid.
- **Amber** — all requirements met, but one expires within 30 days.
- **Green** — all requirements met, none expiring soon.

Red takes priority over Amber. Unknown `site_id` or `person_id` → `404`.

## Key decisions

- **`ACC-007` / `ACC-001` aliasing** — the CSVs use different codes for
  what appears to be the same safety requirement. Handled via an explicit
  alias map rather than a general name-matching system, since the
  relationship isn't guaranteed to hold outside the sample data.
- **Logging** - Put/check used as it keeps identifiers from being shown within the URL.  
- **Date-level expiry** — `checked_at` is compared against `issue_date`/
  `expiry_date` by date only, since those fields carry no time component.
- **Strict timestamp format** — only `YYYY-MM-DDTHH:MM:SS` is accepted, so
  malformed input provides a more informative fail (`422`).
- **404 handling** — an unknown person and a known person with zero
  accreditation rows are indistinguishable in the given data, so both
  return the same `404`.

## Designing for future use cases

- **Daily results per site** — each check is a self-contained, queryable
  record (`person_id` + `site_id` + timestamp), so this becomes a query
  over stored results rather than a change to the check logic.
- **De-duplicating scanner polls** — checks are a pure function of their
  inputs with no side effects, so repeated identical requests are
  naturally idempotent; de-dup can sit in front of the endpoint.
- **Compliance storage** — the response is already a flat, serialisable
  record of what was evaluated and why, so persisting it is a matter of
  writing it to a store, not restructuring it.

None of this is implemented — the service currently reads CSVs into
memory at startup — but the response shape was kept explicit so these
extensions wouldn't require reworking the core logic.

## With more time

- Index the CSV data instead of scanning per request.
- Create a database to handle a larger mutli-site dataset.
- Confirm the accreditation-code relationship with real data before
  relying on a hardcoded alias.
- Add tests for boundary cases (exact expiry date, 30-day threshold,
  multiple records per code).
