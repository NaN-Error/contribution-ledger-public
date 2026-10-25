"""Wait for the existing local stack. No mutation, dependencies, or credentials."""
import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def wait_ready(url: str, seconds: float = 60) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=5) as response:
                payload = json.load(response)
                if response.status == 200 and payload.get("status") == "ready":
                    return payload
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            pass
        time.sleep(1)
    raise RuntimeError("Local readiness did not succeed. Inspect the local services; do not delete volumes.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5173/api/v1/system/status")
    args = parser.parse_args()
    wait_ready(args.url)
    print("Local API, database and migration checks are ready.")
