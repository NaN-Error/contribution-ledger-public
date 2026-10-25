"""Check roadmap routing and declared statuses without certifying acceptance."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify_backlog(data: dict) -> None:
    statuses = data["status_values"]
    assert len(statuses) == len(set(statuses)), "Duplicate status declarations."
    assert data["implementation_status"] in statuses, "Undeclared implementation status."
    phases = data["phases"]
    phase_ids = [phase["id"] for phase in phases]
    assert len(phase_ids) == len(set(phase_ids)) == data["phase_count"], "Invalid phase inventory."
    batches = [batch for phase in phases for batch in phase["batches"]]
    batch_ids = [batch["id"] for batch in batches]
    assert len(batch_ids) == len(set(batch_ids)) == data["batch_count"], "Invalid batch inventory."
    for phase in phases:
        assert phase["status"] in statuses, f"Undeclared status: {phase['id']}"
        assert all(dep in phase_ids and phase_ids.index(dep) < phase_ids.index(phase["id"])
                   for dep in phase["depends_on"]), f"Invalid dependency: {phase['id']}"
        for batch in phase["batches"]:
            assert batch["id"].startswith(phase["id"]), "Batch belongs to the wrong phase."
            assert batch["status"] in statuses, f"Undeclared status: {batch['id']}"
    assert data["current_phase"] in phase_ids, "Unknown current phase."
    assert data["next_batch"] in batch_ids, "Unknown next batch."
    current = next(phase for phase in phases if phase["id"] == data["current_phase"])
    assert data["next_batch"] in {batch["id"] for batch in current["batches"]}, "Next batch must belong to the active phase."
    assert data["next_action"].strip(), "Missing next action."


def main() -> None:
    data = json.loads((ROOT / "docs/backlog.json").read_text(encoding="utf-8"))
    verify_backlog(data)
    assert data["source_version"] == (ROOT / "VERSION").read_text(encoding="utf-8").strip(), "Backlog source version is stale."
    print(f"Backlog consistency passed: {data['phase_count']} phases, {data['batch_count']} batches; {data['current_phase']}/{data['next_batch']}.")


if __name__ == "__main__":
    main()
