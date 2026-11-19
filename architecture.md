# Architecture

## Overview

Homelab Takeout is a single-container Python service that backs up self-hosted
applications on a schedule. It exposes a web GUI for configuration and monitoring.

```
┌─────────────────────────────────────────────────────────────┐
│  Docker Container (python:3.12-alpine, port 8080)           │
│                                                             │
│   ┌─────────────────┐     asyncio.gather()                  │
│   │ BackupScheduler │ ─────────────────────────────────┐    │
│   │  (cron loop)    │                                  │    │
│   └────────┬────────┘                         ┌────────▼──┐ │
│            │ run_in_executor                   │  FastAPI  │ │
│   ┌────────▼────────┐                         │  uvicorn  │ │
│   │  BackupWorker   │                         │  :8080    │ │
│   │  (thread pool)  │                         └────────┬──┘ │
│   └────────┬────────┘                                  │    │
│            │ BackupResult                               │    │
│   ┌────────▼────────┐    ┌──────────────────┐    ┌─────▼──┐ │
│   │   Destinations  │    │  state/*.json    │    │ static │ │
│   │ (Drive, SFTP…)  │    │  (last result)   │    │  GUI   │ │
│   └─────────────────┘    └──────────────────┘    └────────┘ │
└─────────────────────────────────────────────────────────────┘

Volumes:   ./config   ./backups   ./logs   ./state   ./.env
```

## Startup Sequence

1. `main.py` reads `$CONFIG_FILE`, `$ENV_FILE`, `$WEB_PORT` from environment.
2. Builds `WorkerRegistry` (maps type strings → worker classes).
3. Creates `EnvManager` (wraps `.env` file for live read/write).
4. Creates `BackupScheduler` and calls `load_config()`.
5. Calls `create_app()` to produce the FastAPI application.
6. `asyncio.gather(scheduler.run_forever(), uvicorn.serve())` — both run concurrently
   in the same event loop. Neither blocks the other.

## Scheduling

`BackupScheduler.run_forever()` sleeps until the next trigger, then calls
`_run_all_services()`.

Two scheduling modes (set in `config/services.json` → `schedule`):

| Mode           | Config key        | Behaviour                            |
|----------------|-------------------|--------------------------------------|
| Daily at time  | `daily_at: "HH:MM"` | Wakes at the given wall-clock time |
| Fixed interval | `interval_hours: N` | Wakes every N hours                |

`run_on_start: true` triggers an immediate run on container start (useful for dev).
Saving the schedule in the GUI wakes the loop, so a new time applies right away.

## Worker Execution

Each enabled service runs as a `BackupWorker` subclass. Workers are blocking
(they call subprocesses and HTTP) so the scheduler wraps each in
`loop.run_in_executor(None, worker.run, context)` — this offloads to the default
`ThreadPoolExecutor` without blocking the event loop.

Workers receive a `BackupContext` (paths + env dict) and return a `BackupResult`
(success flag, message, list of output `Path` objects, timing).

The per-service `_running` flag prevents concurrent runs of the same service.

## Data Flow

```
config/services.json
       │
       ▼
BackupScheduler.load_config()
       │
       ▼ for each enabled service
WorkerRegistry.create(service_config) → BackupWorker
       │
       ▼  (in thread)
worker.run(BackupContext)
       │
       ▼
BackupResult { success, message, output_files, timing }
       │
       ├─► _persist_state()  →  state/{service}/last_result.json
       │
       └─► _upload_to_destinations()  →  every enabled destination
```

## State Persistence

After each run (success or failure), the scheduler writes
`state/{service_name}/last_result.json`. This file is the source of truth for
the GUI's "Last Run" display. It contains:

```json
{
  "success": true,
  "message": "Backup completed: vaultwarden_encrypted_json_20260607.json",
  "started_at": "2026-06-07T03:30:00.000000",
  "finished_at": "2026-06-07T03:30:14.123456",
  "output_files": ["/backups/vaultwarden/vaultwarden_encrypted_json_20260607.json"]
}
```

## Configuration Hierarchy

```
docker-compose.yml  →  environment block  (paths, port, TZ)
         +
.env file  (service credentials, API keys)
         +
config/services.json  (schedule, retention, which services/destinations are enabled)
```

The GUI can edit all three layers at runtime via the REST API. The `.env` file is
hot-reloaded before each backup run, so credential changes take effect immediately
without a restart.

## API Surface

Everything under `/api/` needs a signed-in session (or a trusted proxy header in
proxy mode), except the four public paths marked *public*.

| Method | Path | Purpose |
|--------|------|---------|
| GET    | `/api/auth/status` | *public* — mode, setup needed, signed in? |
| POST   | `/api/auth/setup` | *public* — first admin password (needs the setup code) |
| POST   | `/api/auth/login` | *public* — sign in (5 tries, then 15 min lockout) |
| POST   | `/api/auth/logout` | End this session |
| POST   | `/api/auth/password` | Change the admin password |
| PUT    | `/api/auth/settings` | Switch password / proxy / off mode |
| GET    | `/api/services` | Dashboard services + last state (secrets masked) |
| POST   | `/api/services` | Add an app (or another instance of one) |
| DELETE | `/api/services/{name}` | Remove an app (settings and backups stay) |
| PUT    | `/api/services/{name}/env-vars` | Save one service's settings to `.env` |
| PUT    | `/api/services/{name}/label` | Rename on the dashboard |
| PUT    | `/api/services/{name}/enabled` | Toggle enabled flag |
| POST   | `/api/services/{name}/trigger` | Manual run |
| POST   | `/api/services/trigger-all` | Run every enabled, idle service |
| GET    | `/api/catalog` | Every app this build can back up |
| GET    | `/api/env-vars/{type}` | Env var specs per worker type (older API; secrets masked) |
| PUT    | `/api/env-vars/{type}` | Write a worker type's values to `.env` (older API) |
| GET    | `/api/destinations` | Destinations, settings (secrets masked), login status |
| PUT    | `/api/destinations/{type}/env-vars` | Save a destination's settings |
| POST   | `/api/destinations/{type}/test` | Test the connection (returns an SFTP host key to trust) |
| POST   | `/api/destinations/{type}/login` | Start a device-code login (Google, Microsoft) |
| GET    | `/api/destinations/logins/{id}` | Poll a device-code login |
| DELETE | `/api/destinations/{type}/login` | Revoke and forget stored tokens |
| POST   | `/api/destinations/sftp/key` | Store a pasted SSH private key (0600) |
| POST   | `/api/destinations/google_drive/credentials` | Upload your own OAuth client JSON |
| POST   | `/api/destinations/google_drive/oauth/start` | Start your-own-client OAuth (PKCE) |
| GET    | `/api/destinations/google_drive/oauth/callback` | *public* — OAuth redirect; the one-time state authenticates it |
| GET    | `/api/settings` | Schedule + retention settings |
| PUT    | `/api/settings` | Update settings |
| GET    | `/`, `/static/*` | Web GUI (no data in it; public so the login form loads) |

## Worker Catalogue

| Worker type                   | Service              | Method                      |
|-------------------------------|----------------------|------------------------------|
| `vaultwarden_encrypted_json`  | Vaultwarden          | `bw` CLI, encrypted JSON     |
| `wikijs`                      | Wiki.js              | GraphQL API export           |
| `snipeit`                     | Snipe-IT             | REST API + tar archive       |
| `bar_assistant`               | Bar Assistant        | REST API + tar archive       |
| `kitchenowl`                  | KitchenOwl           | REST API + tar archive       |
| `linkwarden`                  | Linkwarden           | REST API JSON export         |
| `n8n`                         | n8n                  | REST API JSON export         |
| `karakeep`                    | Karakeep             | REST API + tar archive       |
| `spoolman`                    | Spoolman             | REST API (no auth) + tar archive |
| `immich`                      | Immich (metadata)    | REST API + tar archive       |
| `nginx_proxy_manager`         | Nginx Proxy Manager  | REST API (token login) + tar archive |
| `adguardhome`                 | AdGuard Home         | REST API (basic auth) + tar archive |
| `plex`                        | Plex                 | REST API (X-Plex-Token) + tar archive |
| `jellyfin`                    | Jellyfin             | REST API (API key) + tar archive |
| `uptimekuma`                  | Uptime Kuma          | Socket.IO API (login) + tar archive |
| `homeassistant`               | Home Assistant       | WebSocket API: native backup, downloaded `.tar` |
| `openproject`                 | OpenProject          | REST API (API key) + tar archive |
| `openwebui`                   | Open WebUI           | REST API (API key) + tar archive |
| `qbittorrent`                 | qBittorrent          | Web API (login) + tar archive with `.torrent` files |
| `sparkyfitness`               | SparkyFitness        | REST API (API key) + tar archive |
| `manyfold`                    | Manyfold             | REST API (OAuth client) + tar archive |

See [`docs/services/`](docs/services/) for what each worker backs up and how
to configure its credentials.

## Destination Catalogue

Every enabled destination gets each successful run's files, then keeps the newest
`remote_keep_count` per service (only files named `<service>_...` are ever pruned).

| Destination    | Auth method                                         |
|----------------|-----------------------------------------------------|
| Google Drive   | Device-code login, or your own OAuth client (PKCE)  |
| OneDrive       | Device-code login (Microsoft public client)         |
| SFTP           | Password or SSH key; host key pinned on first test  |
| SMB            | Username and password                               |
| Local folder   | None (a path inside the container, e.g. a NAS mount) |

## Key Design Decisions

**Single container, no message queue.** A scheduled run starts every enabled
service at once (`asyncio.gather`), each worker in its own executor thread; one
service never runs twice at the same time. Simple, auditable, no moving parts. Suitable for personal/homelab scale.

**Blocking workers in thread pool.** Workers use `subprocess` and `requests` —
both blocking. Rather than converting everything to async (complex, error-prone),
they run in `run_in_executor`. The event loop stays responsive for the web API.

**Hot-reload of `.env`.** The env dict is rebuilt from disk before every backup
run. This means you can update a password in the GUI and the next scheduled run
picks it up without a restart.

**No Docker socket.** Workers do not mount or use the Docker socket. They
communicate with services over HTTP (REST/GraphQL) or via network-accessible
CLIs. This limits the container's blast radius if compromised.
