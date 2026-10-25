"""Operator-only commands. Never run seed/reset/recovery implicitly during normal startup."""
import argparse
import json
import sys
from uuid import UUID
from app.ledger.operator import inspect_credit
from alembic import command
from app.core.config import get_settings
from app.core.errors import ApiError
from app.db.development import reset_marker, seed_marker
from app.db.migration import migration_config
from app.db.session import Database
from app.system.service import system_status
from app.auth.operator import setup_token, recovery_token, set_account_active, seed_team, prune_auth


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("provision-runtime", help="Provision the separate API role using CL_RUNTIME_DB_PASSWORD.")
    sub.add_parser("init-security", help="Initialize a separate MFA master only if no existing factors require recovery.")
    sub.add_parser("init-repository-credentials", help="Initialize the separate local GitHub credential master without overwriting existing ciphertext.")
    mfa_reset = sub.add_parser("reset-mfa", help="After identity verification, revoke sessions and require fresh enrollment.")
    mfa_reset.add_argument("--email",required=True)
    mfa_reset.add_argument("--reason",required=True)
    mfa_reset.add_argument("--confirm",required=True)
    sub.add_parser("migrate", help="Apply forward migrations; never resets data.")
    sub.add_parser("seed", help="Create the optional synthetic persistence marker.")
    sub.add_parser("status", help="Print diagnostics without credentials.")
    sub.add_parser("setup-token", help="Print a one-hour single-use first-owner setup token.")
    sub.add_parser("desktop-ticket", help="Explicit personal desktop setup/reopen; print a two-minute one-use launch ticket.")
    sub.add_parser("prune-auth", help="Prune authentication records expired over seven days ago; retain audits.")
    reset = sub.add_parser("reset-development", help="Delete only the synthetic persistence marker.")
    reset.add_argument("--confirm", required=True)
    seed = sub.add_parser("seed-team", help="Create an optional synthetic team and print random passwords once.")
    seed.add_argument("--confirm", required=True)
    for name in ("recover-account", "disable-account", "enable-account"):
        tool = sub.add_parser(name)
        tool.add_argument("--email", required=True)
        tool.add_argument("--reason", required=True, help="Reason for this authorized operator action, 8–500 characters.")
    credit = sub.add_parser("check-credit", help="Verify contribution projections against immutable events.")
    credit.add_argument("--workspace-id", required=True, type=UUID)
    credit.add_argument("--project-id", required=True, type=UUID)
    credit.add_argument("--repair", action="store_true", help="Rebuild derived projections only; never edits credit events.")
    credit.add_argument("--confirm", default="")
    credit.add_argument("--reason", default="")
    args = parser.parse_args()
    database = None
    try:
        settings = get_settings()
        settings.require_local_foundation()
        database = Database(settings)
        if args.command == "provision-runtime":
            import os
            from app.operations.privileges import provision_runtime
            print(json.dumps(provision_runtime(database,os.environ.get("CL_RUNTIME_DB_PASSWORD",""),"PROVISION-RESTRICTED-API")))
        elif args.command == "init-security":
            from app.operations.security import initialize_auth_key
            print(json.dumps(initialize_auth_key(database)))
        elif args.command == "init-repository-credentials":
            from app.analysis.connections import enabled
            from app.security.secrets.encrypted import initialize
            enabled(settings)
            initialize(settings.repository_master_key_file,settings.repository_credential_root)
            print('Protected local GitHub credential storage is ready; no credential was displayed.')
        elif args.command == "reset-mfa":
            from app.operations.security import reset_factor
            print(json.dumps(reset_factor(database,args.email,args.reason,args.confirm)))
        elif args.command == "check-credit":
            result = inspect_credit(database, args.workspace_id, args.project_id,
                repair=args.repair, confirm=args.confirm, reason=args.reason)
            print(json.dumps(result, indent=2))
            return 0 if result.get("after", result)["consistent"] else 1
        elif args.command == "migrate":
            command.upgrade(migration_config(), "head")
            print("Forward migrations applied.")
        elif args.command == "status":
            result = system_status(database)
            print(result.model_dump_json(indent=2))
            return 0 if result.status == "ready" else 1
        elif args.command == "seed":
            print(json.dumps({"marker_id": str(seed_marker(database))}))
        elif args.command == "reset-development":
            reset_marker(database, args.confirm)
            print("Synthetic marker removed. Accounts, memberships and audit history are unchanged.")
        elif args.command == "desktop-ticket":
            from app.auth.desktop import desktop_ticket
            print(json.dumps({"desktop_ticket": desktop_ticket(database)}))
        elif args.command == "setup-token":
            print("Single-use setup token (expires in one hour; replaces any earlier setup token):")
            print(setup_token(database))
            print("Paste this into the first-owner setup screen. Treat it as a secret; do not send it in chat.")
        elif args.command == "recover-account":
            print("One-time recovery token (expires in 30 minutes; all existing sessions revoked):")
            print(recovery_token(database, args.email, args.reason))
            print("Give it privately to the verified account owner. Use the recovery screen; then sign in normally.")
        elif args.command in {"disable-account", "enable-account"}:
            set_account_active(database, args.email, args.command == "enable-account", args.reason)
            print("Account state changed and sessions revoked. Historical identity is preserved.")
        elif args.command == "seed-team":
            print(json.dumps(seed_team(database, args.confirm), indent=2))
        elif args.command == "prune-auth":
            print(json.dumps(prune_auth(database)))
        return 0
    except ApiError as exc:
        print(f"Operation refused: {exc.message}", file=sys.stderr)
        return 1
    except (PermissionError, ValueError):
        print("Operation refused. Check the documented configuration, confirmation, and bounded input requirements.", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Operation failed ({type(exc).__name__}). Check local services and configuration; secrets are not printed.", file=sys.stderr)
        return 1
    finally:
        if database:
            database.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
