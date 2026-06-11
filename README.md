# BUPA Sync Automation

[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://reactjs.org/)
[![n8n](https://img.shields.io/badge/n8n-Workflows-EA4B71?logo=n8n&logoColor=white)](https://n8n.io/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

> AI-powered Employee-to-Business Partner synchronization automation for SAP S/4HANA conversions

![Dashboard](docs/screenshots/dashboard.png)

---

## Features

- **AI Agent** — Classifies sync errors and proposes fixes using LLM-powered analysis
- **n8n Workflow Orchestration** — Initial sync, retry logic, and agent-driven fix workflows
- **React Dashboard** — Configurable cards, real-time status, and batch operations
- **SAP IAS Authentication** — Single Sign-On via OpenID Connect
- **Background Job Scheduling** — Automated sync runs with configurable intervals
- **Audit Trail** — Full user action tracking with timestamps and details
- **Email Notifications** — SMTP-based alerts for sync failures and completions
- **Multi-Category Batch Operations** — Process employees by category with bulk actions
- **Configurable Everything** — All settings managed via UI, no hardcoding required

---

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Dashboard   │────▶│  Backend API │────▶│  n8n Engine  │
│  (React)     │     │  (FastAPI)   │     │  (Workflows) │
└──────────────┘     └──────┬───────┘     └──────┬───────┘
                            │                     │
                     ┌──────▼───────┐     ┌──────▼───────┐
                     │  AI Agent    │     │ SAP S/4HANA  │
                     │  (Python)    │     │ (or Mock)    │
                     └──────────────┘     └──────────────┘

Additional Services:
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  PostgreSQL  │     │   Mailpit    │     │  Mock S/4    │
│  (Database)  │     │  (SMTP/UI)   │     │  (FastAPI)   │
└──────────────┘     └──────────────┘     └──────────────┘
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   pgAdmin    │     │    Qdrant    │     │    ngrok     │
│  (DB Admin)  │     │ (Vector DB)  │     │  (Tunnels)   │
└──────────────┘     └──────────────┘     └──────────────┘
```

---

## Tech Stack

| Component       | Technology         | Version   |
|-----------------|--------------------|-----------|
| Frontend        | React + TypeScript | 18.x      |
| UI Framework    | Tailwind CSS       | 3.4       |
| Build Tool      | Vite               | 6.x       |
| Backend API     | FastAPI (Python)   | 0.100+    |
| AI Agent        | Python + LLM Proxy | 3.13      |
| Workflows       | n8n                | Latest    |
| Database (Docker)| PostgreSQL        | 16        |
| Database (Native)| SQLite            | 3.x       |
| Auth            | SAP IAS (OIDC)    | —         |
| Email           | Mailpit (dev)      | Latest    |
| Mock SAP        | FastAPI            | —         |
| Containerization| Docker Compose     | 3.x       |

---

## Quick Start

### Docker (Recommended)

Clone the repository:

```bash
# GitHub.com
git clone https://github.com/skalmodiya/bupa-sync-automation.git
cd bupa-sync-automation

# SAP GitHub (internal)
git clone https://github.tools.sap/I560043/bupa-sync-automation.git
cd bupa-sync-automation
```

The fastest way to get everything running:

```bash
# Foreground (see logs in terminal)
docker-compose up --build

# Background (detached mode)
docker-compose up --build -d

# With ngrok (expose n8n webhooks to internet)
docker-compose --profile ngrok up --build -d
```

**Useful commands:**

```bash
# View logs (all services, follow output)
docker-compose logs -f

# View logs for a specific service
docker-compose logs n8n-import

# Check service status
docker-compose ps

# Stop all services
docker-compose down

# Stop and remove volumes (full reset)
docker-compose down -v
```

Once all services are healthy:

| Service       | URL                          | Notes                                |
|---------------|------------------------------|--------------------------------------|
| Dashboard     | http://localhost:3001         | —                                    |
| Backend API   | http://localhost:8081         | —                                    |
| n8n Editor    | http://localhost:5678         | Create account on first login; workflows are pre-loaded |
| PostgreSQL    | localhost:5432               | User: bpsync / Pass: bpsync          |
| pgAdmin       | http://localhost:5050         | Login: admin@bupa-sync.dev / admin |
| Qdrant        | http://localhost:6333         | Vector DB dashboard                  |
| Mock S/4HANA  | http://localhost:8090         | —                                    |
| Mailpit UI    | http://localhost:8025         | —                                    |
| AI Agent      | http://localhost:5000         | —                                    |
| ngrok UI      | http://localhost:4040         | Only with `--profile ngrok`          |

### Native (Development)

**Prerequisites:**
- Python 3.13+
- Node.js 18+
- n8n (installed globally or via Docker)

**Steps:**

```bash
# 1. Install backend dependencies
cd backend
pip install -r requirements.txt

# 2. Install dashboard dependencies
cd ../dashboard
npm install

# 3. Start all services
cd ..
start-local.bat        # Windows
# or
./start-local.sh       # macOS/Linux
```

**Native URLs:**

| Service       | URL                          |
|---------------|------------------------------|
| Dashboard     | http://localhost:5173         |
| Backend API   | http://localhost:8080         |
| n8n Editor    | http://localhost:5678         |

---

## Configuration

All configuration is managed through the **Settings** page in the dashboard (`/settings`).

### Key Settings

| Setting               | Description                                    |
|-----------------------|------------------------------------------------|
| SAP IAS               | OIDC client ID, issuer URL for SSO             |
| n8n Connection        | Base URL, API key for workflow execution        |
| LLM Proxy             | AI Core / GenAI Hub endpoint and credentials   |
| SMTP                  | Mail server host, port, sender address         |
| Mock S/4HANA          | Base URL for the SAP mock service              |
| Sync Intervals        | Cron expressions for background jobs           |
| ngrok                 | Auth token, domain for webhook tunneling       |
| Qdrant                | Vector DB URL for RAG/embeddings               |

Settings are persisted in the database and can be modified at runtime without restart.

### ngrok (Optional Webhook Tunneling)

ngrok exposes your local n8n webhooks to the internet, useful for receiving external callbacks.

**Setup:**

1. Copy the env example and set your ngrok credentials:
   ```bash
   cp .env.example .env
   # Edit .env with your NGROK_AUTHTOKEN and NGROK_DOMAIN
   ```

2. Start with the ngrok profile:
   ```bash
   docker-compose --profile ngrok up --build -d
   ```

3. Set the **n8n Webhook URL** (in Dashboard > Settings > n8n) to your ngrok domain:
   ```
   https://my-app.ngrok-free.app
   ```

4. The ngrok inspection UI is available at http://localhost:4040

> **Note:** ngrok auth token and domain are configured via `.env` file (not the Settings page)
> because they are required at container startup time before the backend is available.

---

## Project Structure

```
BPSYNC/
├── dashboard/                  # React frontend
│   ├── src/
│   │   ├── components/         # Reusable UI components
│   │   ├── hooks/              # Custom React hooks
│   │   ├── pages/              # Page components (routes)
│   │   ├── lib/                # API client utilities
│   │   └── types/              # TypeScript type definitions
│   ├── Dockerfile              # Production build (nginx)
│   └── package.json
├── backend/                    # FastAPI backend
│   ├── routes/                 # API route handlers
│   │   ├── auth_routes.py      # Authentication endpoints
│   │   ├── settings.py         # Settings CRUD
│   │   ├── sync_status.py      # Sync status tracking
│   │   ├── n8n_proxy.py        # n8n workflow proxy
│   │   ├── agent_proxy.py      # AI agent proxy
│   │   ├── jobs.py             # Background job management
│   │   └── audit.py            # Audit log endpoints
│   ├── main.py                 # FastAPI app entry point
│   ├── auth.py                 # IAS/JWT authentication
│   ├── database.py             # SQLite database layer
│   ├── config.py               # App configuration
│   ├── jobs.py                 # Job scheduler
│   ├── audit.py                # Audit trail logic
│   ├── Dockerfile
│   └── requirements.txt
├── assets/
│   ├── bupa-sync-agent/        # AI Agent (Python)
│   │   ├── app/
│   │   │   ├── agent.py        # Agent orchestration
│   │   │   ├── agent_executor.py
│   │   │   ├── classifiers/    # Error classification
│   │   │   ├── resolvers/      # Fix resolution
│   │   │   ├── tools/          # BP API client tools
│   │   │   ├── models/         # Data models
│   │   │   └── instrumentation/# OpenTelemetry
│   │   ├── config/             # Error patterns YAML
│   │   ├── tests/              # Unit tests
│   │   └── Dockerfile
│   └── n8n/                    # n8n workflow definitions
│       └── workflows/
│           ├── bupa-sync-orchestration.n8n.json
│           ├── bupa-sync-local.n8n.json
│           ├── bupa-sync-retry.n8n.json
│           └── bupa-sync-agent-fix.n8n.json
├── mock-s4hana/                # Mock SAP S/4HANA service
│   ├── main.py                 # FastAPI mock endpoints
│   ├── data/                   # Sample employee/BP data
│   └── Dockerfile
├── docker/
│   ├── n8n-import/             # Auto-imports workflows into n8n
│   ├── pgadmin/                # pgAdmin server config (servers.json)
│   └── postgres/               # PostgreSQL init scripts (init.sql)
├── docker-compose.yml          # Full stack orchestration
├── start-local.bat             # Native startup (Windows)
├── start-local.sh              # Native startup (Linux/Mac)
└── solution.yaml               # Solution manifest
```

---

## Process Flow

The BUPA Sync process follows five stages:

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ 1.FETCH │───▶│ 2.MATCH │───▶│ 3.SYNC  │───▶│ 4.ERROR │───▶│ 5.DONE  │
│Employees│    │  to BP  │    │ Execute │    │  Handle │    │ Report  │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
```

1. **Fetch** — Retrieve employee records from SAP HCM (PA0000/PA0002)
2. **Match** — Match employees to existing Business Partners or flag for creation
3. **Sync** — Execute BP creation/update via S/4HANA APIs
4. **Error Handle** — AI Agent classifies errors and proposes fixes
5. **Report** — Generate summary, send notifications, update audit trail

---

## Development

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

### Dashboard

```bash
cd dashboard
npm install
npm run dev
```

### AI Agent

```bash
cd assets/bupa-sync-agent
pip install -r requirements.txt
python -m app.main
```

### Running Tests

```bash
# Agent tests
cd assets/bupa-sync-agent
pip install -r requirements-test.txt
pytest
```

### Adding a New Dashboard Page

1. Create component in `dashboard/src/pages/`
2. Add route in `dashboard/src/App.tsx`
3. Add sidebar entry in `dashboard/src/components/Sidebar.tsx`

### Adding a New API Endpoint

1. Create route file in `backend/routes/`
2. Register router in `backend/main.py`
3. Add corresponding frontend hook in `dashboard/src/hooks/`

---

## Deployment

### Local Docker (Current)

Full stack runs via `docker-compose up --build`. Suitable for demos and development.

### SAP BTP (Future)

- Dashboard → SAP HTML5 Application Repository
- Backend → Cloud Foundry Python buildpack
- Agent → Cloud Foundry Python buildpack
- n8n → SAP Build Process Automation (or self-hosted)
- Database → SAP HANA Cloud / PostgreSQL on SAP BTP

---

## Environment Comparison

| Aspect            | Local Native          | Docker                | Production (BTP)    |
|-------------------|-----------------------|-----------------------|---------------------|
| Dashboard URL     | localhost:5173        | localhost:3001        | *.launchpad.cfapps  |
| Backend URL       | localhost:8080        | localhost:8081        | *.cfapps.sap.hana   |
| n8n URL           | localhost:5678        | localhost:5678        | Managed / self-host |
| Authentication    | Bypassed (dev)        | Bypassed (dev)        | SAP IAS (OIDC)      |
| Database          | SQLite (file)         | PostgreSQL 16         | HANA Cloud          |
| Email             | Console output        | Mailpit               | Real SMTP           |
| S/4HANA           | Mock service          | Mock container        | Real S/4HANA        |
| Startup           | `start-local.bat`    | `docker-compose up`   | CF push / CI/CD     |

---

## Troubleshooting

### Common Issues

| Problem                          | Solution                                          |
|----------------------------------|---------------------------------------------------|
| Port already in use              | Stop conflicting services or change ports in `.env`|
| pgAdmin won't start (exit 1)    | Email domain must not be `.local`; use `.dev` or `.com` instead |
| n8n workflows not imported       | The import retries automatically; check `docker-compose logs n8n-import` for status |
| Backend can't connect to mock    | Ensure `mock-s4hana` is healthy before backend starts|
| Dashboard shows blank page       | Check browser console; ensure backend is running  |
| Auth redirect loop               | Verify IAS client ID and callback URL in settings |
| Agent Fix returns auth error     | See [Agent Fix LLM Authentication](#agent-fix-llm-authentication) below |
| Agent returns empty responses    | Check LLM proxy URL and API key in settings       |
| Docker build fails               | Run `docker-compose down -v` then rebuild         |
| SQLite locked errors             | Ensure only one backend instance is running       |

### Agent Fix LLM Authentication

If you get an error like `litellm.AuthenticationError: Invalid API key for local proxy`, follow these steps:

1. **Ensure the Hyperspace LLM Proxy is running** on your host machine (port 6655):
   ```bash
   curl http://localhost:6655/litellm/v1/models
   ```

2. **Set the API key** in Dashboard > Settings > LLM section:
   - Enter a valid API key for your Hyperspace proxy
   - Click **Test Connection** to verify
   - Save settings

3. **No restart needed** — the agent automatically picks up API key changes from settings on each invocation.

4. **Docker-specific notes:**
   - The agent container uses `host.docker.internal:6655` to reach the proxy on your host
   - The `LLM_BASE_URL` env var in `docker-compose.yml` ensures correct routing
   - If you change the proxy port, update both `docker-compose.yml` and `docker-settings.json`

### n8n Workflows Missing on First Login

The `n8n-import` service runs **before** n8n starts (following the official n8n pattern).
It imports workflows directly into the n8n SQLite database, so they are available
immediately when you log in for the first time.

If workflows are still missing after startup, check logs:
```bash
docker-compose logs n8n-import
```

To force a re-import (e.g., after a reset):
```bash
docker-compose down -v
docker-compose up --build -d
```

After import, workflows need to be **activated** manually in the n8n UI.

### Checking Service Health

```bash
# All services
docker-compose ps

# Individual health
curl http://localhost:8081/health   # Backend
curl http://localhost:8090/api/pa0000  # Mock S/4HANA
curl http://localhost:5000/health   # Agent
curl http://localhost:6333/healthz  # Qdrant
```

### Resetting Data

```bash
# Docker: remove volumes
docker-compose down -v

# Native: delete data directory
rm -rf backend/data/bupa_sync.db
rm -rf backend/data/audit.log
```

---

## Contributing

1. Create a feature branch from `main`
2. Make changes following existing code patterns
3. Test locally with `docker-compose up --build`
4. Ensure no linting errors (`ruff check .` for Python)
5. Submit a pull request with clear description

### Code Style

- **Python**: Ruff formatter, type hints required
- **TypeScript**: Strict mode, Tailwind for styling
- **Commits**: Conventional commits (`feat:`, `fix:`, `docs:`)

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Built with ❤️ for SAP S/4HANA conversions
</p>
