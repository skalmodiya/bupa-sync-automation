"""BUPA Sync Backend — Configuration management and orchestration layer."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.settings import router as settings_router
from routes.n8n_proxy import router as n8n_router
from routes.agent_proxy import router as agent_router
from routes.sync_status import router as sync_router
from routes.audit import router as audit_router
from routes.auth_routes import router as auth_router

app = FastAPI(
    title="BUPA Sync Backend",
    description="Configuration management and orchestration layer for BUPA Sync local development environment",
    version="1.0.0",
)

# CORS — allow Vite dev server and alternative dev port
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount route groups
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(n8n_router, prefix="/api/n8n", tags=["n8n"])
app.include_router(agent_router, prefix="/api/agent", tags=["agent"])
app.include_router(sync_router, prefix="/api/sync", tags=["sync"])
app.include_router(audit_router, prefix="/api/audit", tags=["audit"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])


@app.get("/health")
async def health():
    """Health check for this backend."""
    return {"status": "ok", "service": "bupa-sync-backend"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
