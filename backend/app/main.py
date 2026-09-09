from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="SAEA Backend")


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "ok"})
