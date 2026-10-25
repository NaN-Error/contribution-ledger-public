"""Dependency-free structural checks; not a substitute for installation or runtime tests."""
import ast
import json
import re
import tomllib
from pathlib import Path
from verify_backlog import main as verify_backlog

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {".git", ".venv", "node_modules", "dist", "__pycache__", ".test-build", ".pytest_cache", ".local"}


def main() -> None:
    verify_backlog()
    sources = [p for p in ROOT.rglob("*") if p.is_file() and not any(x in IGNORED for x in p.relative_to(ROOT).parts) and p.relative_to(ROOT).parts[0] not in {"uploads", "secrets"}]
    for name in ["__init__.py", "store.py", "provision.py"]:
        assert ROOT / "apps/api/app/security/secrets" / name in sources, "SecretStore source was excluded with credential data."
    python_files = [p for p in sources if p.suffix == ".py"]
    for path in python_files:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for path in sources:
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
    package = json.loads((ROOT / "apps/web/package.json").read_text())
    lock = json.loads((ROOT / "apps/web/package-lock.json").read_text())
    assert lock["lockfileVersion"] == 3
    for group in ["dependencies", "devDependencies"]:
        assert lock["packages"][""][group] == package[group]
        for name, version in package[group].items():
            assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"Direct dependency not exact: {name}"
            assert lock["packages"]["node_modules/" + name]["version"] == version
    for path, item in lock["packages"].items():
        if not path:
            continue
        assert item.get('integrity', '').startswith('sha512-'), f"Missing registry integrity: {path}"
        for group in ["dependencies", "optionalDependencies"]:
            for name in item.get(group, {}):
                assert "node_modules/" + name in lock["packages"], f"Missing transitive node: {name}"
    for name in ["requirements.lock", "requirements-dev.lock", "requirements-jobs.lock"]:
        for line in (ROOT / "apps/api" / name).read_text().splitlines():
            if line and not line.startswith("#"):
                assert re.match(r"[a-z0-9-]+==[^\s]+", line), f"Unpinned Python requirement: {line}"
    compose = (ROOT / "compose.yaml").read_text()
    assert '127.0.0.1:${CL_API_PORT' in compose and '127.0.0.1:${CL_WEB_PORT' in compose
    assert "postgres_data:/var/lib/postgresql/data" in compose
    assert "evidence_data:/var/lib/contribution-ledger/evidence" in compose
    assert "CL_OBJECT_STORAGE_ROOT" in compose
    assert '"--no-proxy-headers"' in (ROOT / "infra/api.Dockerfile").read_text()
    assert "--no-proxy-headers" in (ROOT / ".github/workflows/ci.yml").read_text()
    version = (ROOT / "VERSION").read_text().strip()
    assert re.fullmatch(r'\d+\.\d+\.\d+-phase\d+', version)
    package_version = version.split('-')[0]
    assert package["version"] == lock["version"] == lock["packages"][""]["version"] == package_version
    assert tomllib.loads((ROOT / 'apps/api/pyproject.toml').read_text())['project']['version'] == package_version
    assert f'BUILD_VERSION = "{version}"' in (ROOT / 'apps/api/app/core/config.py').read_text()
    assert (ROOT / "VERSION").read_text().strip() in (ROOT / "apps/web/src/lib/release.ts").read_text()
    print(f"Source structure passed: {len(python_files)} Python files, JSON parsing, exact dependency pins, graph presence, local bindings.")
    print("This does not verify downloaded packages, PowerShell, PostgreSQL, Docker, or the React build.")


if __name__ == "__main__":
    main()
