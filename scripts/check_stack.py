"""Opt-in test of a local development stack; briefly stops its database.

This creates the synthetic marker but never deletes data or volumes. Do not run
against a deployment being used by others. Designed for disposable CI or a local test.
"""
import argparse
import json
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from wait_ready import wait_ready

ROOT = Path(__file__).resolve().parents[1]


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", "--project-directory", str(ROOT), "-f", str(ROOT / "compose.yaml"), *args], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-synthetic-seed", action="store_true", required=True)
    parser.parse_args()
    values = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    if values.get("CL_ENVIRONMENT") != "development":
        raise SystemExit("Refusing stack mutation outside development.")
    port = int(values.get("CL_WEB_PORT", "5173"))
    origin = f"http://127.0.0.1:{port}"
    status_url = origin + "/api/v1/system/status"
    wait_ready(status_url)
    compose("exec", "-T", "api", "python", "-m", "app.cli", "seed")
    first = wait_ready(status_url)["persistence"]["marker_id"]
    assert first is not None, "Seeding did not create a marker."
    compose("restart", "db", "api", "web")
    assert wait_ready(status_url)["persistence"]["marker_id"] == first, "Marker changed after service restart."
    try:
        compose("stop", "db")
        with urlopen(origin + "/health/live", timeout=10) as response:
            assert response.status == 200
        try:
            with urlopen(status_url, timeout=15):
                raise AssertionError("Readiness must fail when PostgreSQL is stopped.")
        except HTTPError as error:
            assert error.code == 503
            assert json.load(error)["database"]["status"] == "unavailable"
    finally:
        compose("up", "-d", "--wait", "--wait-timeout", "120", "db")
    assert wait_ready(status_url)["persistence"]["marker_id"] == first
    print("Stack check passed: migration, seed, restart persistence, liveness/readiness outage, recovery.")


if __name__ == "__main__":
    main()
