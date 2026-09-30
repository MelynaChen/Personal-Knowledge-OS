from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pathlib import Path

from app.api.import_routes import router as import_router
from app.api.knowledge_routes import router as knowledge_router
from app.api.review_routes import router as review_router
from app.api.sync_routes import router as sync_router

app = FastAPI(title="Personal Knowledge OS", version="0.3.0")
app.include_router(import_router)
app.include_router(knowledge_router)
app.include_router(review_router)
app.include_router(sync_router)


@app.get("/health")
def health():
    return {"status": "ok", "phase": 2}


@app.get("/", response_class=HTMLResponse)
def home():
    return (Path(__file__).resolve().parent / "web" / "demo.html").read_text(encoding="utf-8")
