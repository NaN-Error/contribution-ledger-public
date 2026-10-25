# Phase-2 API contract

OpenAPI is generated from the source at `/openapi.json`; `/docs` is read-only developer reference unless the caller deliberately supplies the browser-security protocol. Browser calls should go through the same-origin web proxy.

Start with GET `/api/v1/auth/session` to establish/read an opaque cookie and obtain a memory-only `csrf_token`. For POST/PATCH/DELETE send JSON, an allowed `Origin`, and `X-CSRF-Token`; retain the server's HttpOnly cookie. The browser supplies Origin automatically. No CORS/wildcard allowance is enabled. Request bodies are limited to 64 KiB. Unsafe calls are never automatically retried by the UI.

| Method | Path | Access and effect |
|---|---|---|
| GET | `/api/v1/auth/session` | Anonymous or current session; no personal data beyond the signed-in user. |
| POST | `/api/v1/auth/bootstrap` | Anonymous browser + valid operator setup token; first owner only. |
| POST | `/api/v1/auth/login` | Anonymous browser; rate-limited password verification. |
| POST | `/api/v1/auth/logout` | Current browser session; revoke and rotate to anonymous. |
| POST | `/api/v1/auth/password` | Signed in; current password + new password; revoke old sessions. |
| GET / DELETE | `/api/v1/auth/sessions` / `/api/v1/auth/sessions/{id}` | List/revoke only own sessions. |
| POST | `/api/v1/auth/invitations/inspect` | Browser + invitation token in JSON, never URL query. |
| POST | `/api/v1/auth/invitations/accept` | Token + new-account details, or matching signed-in account. |
| POST | `/api/v1/auth/recover` | Browser + operator recovery token + new password. |
| GET / POST | `/api/v1/workspaces` | Signed in; own active list / create own workspace. |
| GET | `/api/v1/workspaces/{w}` | Active member of this workspace. |
| GET / PATCH | `/api/v1/workspaces/{w}/members` / `.../members/{u}` | Workspace administration, reason and expected version for changes. |
| GET / POST | `/api/v1/workspaces/{w}/projects` | Scope-filtered reads; workspace administrator creates. |
| GET / PATCH | `/api/v1/workspaces/{w}/projects/{p}` | Project access / project administration for edits. |
| GET / POST / PATCH | `/api/v1/workspaces/{w}/projects/{p}/members[/{u}]` | Project administration; target must belong to the same workspace. |
| GET / POST / DELETE | `/api/v1/workspaces/{w}/invitations[/{i}]` | Workspace administration, one-time token exposed only on creation. |
| GET | `/api/v1/workspaces/{w}/audit` | Workspace administration; immutable history, paginated. |

Authenticated responses and errors use `Cache-Control: no-store` and request IDs. Validation responses do not echo input passwords. 401 means missing/expired authentication; 403 means a failed browser-security or scope-permission rule; 404 conceals out-of-scope records; 409 requests a fresh decision for version/state conflicts; 422 rejects bounded/schema data; 429 includes Retry-After. Invalid/wrong/disabled login uses the same message. Exact schemas are in `app/auth/schemas.py` and `app/projects/schemas.py`.

Public `/health/live`, `/health/ready` and `/api/v1/system/status` remain loopback diagnostics, not team-data routes. No API can set a contribution percentage, issue units, connect AI, or distribute money in phase 2.
