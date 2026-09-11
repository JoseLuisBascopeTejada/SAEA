import json
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import router as v1_router


def _cors_origins() -> list[str]:
    """Parse the CORS_ORIGINS env var (JSON list, see .env.example)."""
    try:
        origins = json.loads(os.environ.get("CORS_ORIGINS", "[]"))
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(o) for o in origins] if isinstance(origins, list) else []


app = FastAPI(title="SAEA Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(v1_router)


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "ok"})
