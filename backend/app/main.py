from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.v1.router import router as v1_router

app = FastAPI(title="SAEA Backend")
app.include_router(v1_router)


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "ok"})
