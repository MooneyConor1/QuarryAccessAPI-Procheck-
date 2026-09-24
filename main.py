"""Quarry access check API backed by the supplied CSV files."""

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# The supplied files use different codes for the shared safety requirement:
# ACC-007 at sites and ACC-001 are treated as equivalent based on
# the accreditation names and the fact that safety applies to all sites.
ACCREDITATION_ALIASES = {"ACC-007": "ACC-001"}
AMBER_WINDOW_DAYS = 30

#Creating the FastAPI app with a title and version.
app = FastAPI(title="Quarry Access Check API", version="1.0.0")

# Defining the request model for the /checks endpoint.
class CheckRequest(BaseModel):
    person_id: str
    site_id: str
    checked_at: datetime

    @field_validator("checked_at", mode="before")
    @classmethod
    def require_timestamp_seconds(cls, value: Any) -> datetime:
        if not isinstance(value, str):
            raise ValueError("checked_at must be an ISO timestamp string")
        try:
            
    #The API requires timestamps to include seconds, so we parse the string accordingly.
            parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
        except ValueError as exc:
            raise ValueError("checked_at must use YYYY-MM-DDTHH:MM:SS format") from exc
        return parsed

# Function to load CSV rows into a list of dictionaries.
def load_rows(filename: str) -> list[dict[str, str]]:
    with (DATA_DIR / filename).open("r", newline="", encoding="utf-8-sig") as csv_file:
        return list(csv.DictReader(csv_file))


PERSON_ROWS = load_rows("person_accreditations.csv")
SITE_ROWS = load_rows("site_requirements.csv")


def canonical_code(code: str) -> str:
    return ACCREDITATION_ALIASES.get(code, code)

# Defining the /checks endpoint to evaluate a person's accreditations against site requirements.
@app.post("/checks")
def create_check(request: CheckRequest) -> dict[str, Any]:
    site_requirements = [row for row in SITE_ROWS if row["site_id"] == request.site_id]
    if not site_requirements:
        raise HTTPException(status_code=404, detail=f"Unknown site_id: {request.site_id}")

    person_records = [row for row in PERSON_ROWS if row["person_id"] == request.person_id]
    if not person_records:
        #Can't distinguish between an unknown person_id and a known person with no accreditation records, so both are reported as 404.
        raise HTTPException(status_code=404, detail=f"Unknown person_id or no accreditation records: {request.person_id}")

    check_date = request.checked_at.date()
    held_by_code: dict[str, list[dict[str, str]]] = {}
    for record in person_records:
        held_by_code.setdefault(canonical_code(record["accreditation_code"]), []).append(record)

    missing: list[dict[str, str]] = []
    invalid: list[dict[str, str]] = []
    expiring: list[dict[str, Any]] = []

    # Group site requirements by canonical accreditation code to avoid duplicate checks for equivalent codes.
    requirements_by_code: dict[str, dict[str, str]] = {}
    for requirement in site_requirements:
        requirements_by_code.setdefault(canonical_code(requirement["required_accreditation_code"]), requirement)

    for code, requirement in requirements_by_code.items():
        candidates = held_by_code.get(code, [])
        valid_records = []
        for record in candidates:
            issued = date.fromisoformat(record["issue_date"])
            expires = date.fromisoformat(record["expiry_date"])
            if issued <= check_date <= expires:
                valid_records.append((record, expires))
        if not candidates:
            missing.append({"accreditation_code": requirement["required_accreditation_code"], "accreditation_name": requirement["required_accreditation_name"]})
        elif not valid_records:
            invalid.append({"accreditation_code": requirement["required_accreditation_code"], "accreditation_name": requirement["required_accreditation_name"]})
        else:
            nearest_expiry = min(expires for _, expires in valid_records)
            days_left = (nearest_expiry - check_date).days
            if days_left <= AMBER_WINDOW_DAYS:
                expiring.append({
                    "accreditation_code": requirement["required_accreditation_code"],
                    "accreditation_name": requirement["required_accreditation_name"],
                    "expiry_date": nearest_expiry.isoformat(),
                    "days_until_expiry": days_left,
                })
# Determining the overall outcome based on the accreditation checks.
    if missing or invalid:
        outcome = "Red"
    elif expiring:
        outcome = "Amber"
    else:
        outcome = "Green"

    return {
        "outcome": outcome,
        "person_id": request.person_id,
        "site_id": request.site_id,
        "checked_at": request.checked_at.isoformat(),
        "missing_accreditations": missing,
        "invalid_accreditations": invalid,
        "expiring_accreditations": expiring,
    }
