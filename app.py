"""AWDAX API entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import asyncio

from api.routes.dashboard import router as dashboard_router
from api.routes.instances import router as instances_router
from api.routes.live import router as live_router
from config.settings import settings
from live import bus
from live.manager import live_manager
from warehouse.database import init_db

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    bus.set_event_loop(asyncio.get_running_loop())
    live_manager.resume_all()
    yield
    live_manager.stop_all()


app = FastAPI(
    title="AWDAX",
    description="Autonomous Web Data Acquisition & eXtraction",
    lifespan=lifespan,
)

app.include_router(instances_router, prefix="/api")
app.include_router(live_router, prefix="/api")
app.include_router(dashboard_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


def main() -> None:
    url = f"http://127.0.0.1:{settings.port}" if settings.host in ("0.0.0.0", "::") else f"http://{settings.host}:{settings.port}"
    print(f"AWDAX running at {url}")
    uvicorn.run(
        "app:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
