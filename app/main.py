from fastapi import FastAPI
from pathlib import Path
from fastapi.staticfiles import StaticFiles

from app.api.import_routes import router as import_router
from app.api.knowledge_routes import router as knowledge_router
from app.api.review_routes import router as review_router
from app.api.sync_routes import router as sync_router
from app.api.task_routes import router as task_router
from app.web.routes import router as web_router, prompt_api

app = FastAPI(title="Personal Knowledge OS", version="0.4.0")
app.include_router(import_router)
app.include_router(knowledge_router)
app.include_router(review_router)
app.include_router(sync_router)
app.include_router(task_router)
app.include_router(prompt_api)
app.include_router(web_router)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "web" / "static")), name="static")


@app.get("/health")
def health():
    return {"status": "ok", "phase": 2}
