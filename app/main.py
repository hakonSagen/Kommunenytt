from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import ensure_directories, settings
from app.jobs import run_afjord_once, run_indre_fosen_once, run_orland_once, run_osen_once
from app.sample_protocol import run_sample_protocol_test
from app.scraper import find_afjord_documents, find_indre_fosen_documents, find_orland_documents, find_osen_documents
from db.database import get_db, init_db


app = FastAPI(title=settings.app_name)


@app.on_event("startup")
def startup() -> None:
    ensure_directories()
    init_db()


@app.get("/")
def index() -> dict:
    return {
        "name": settings.app_name,
        "endpoints": [
            "/run/indre-fosen",
            "/run/osen",
            "/run/afjord",
            "/run/orland",
            "/documents/indre-fosen",
            "/documents/osen",
            "/documents/afjord",
            "/documents/orland",
            "/articles/{filename}",
        ],
    }


async def _run_indre_fosen_job(force: bool, protocol_index: int, db: Session) -> dict:
    return await run_indre_fosen_once(db=db, force=force, protocol_index=protocol_index)


async def _run_osen_job(force: bool, protocol_index: int, db: Session) -> dict:
    return await run_osen_once(db=db, force=force, protocol_index=protocol_index)


async def _run_afjord_job(force: bool, protocol_index: int, db: Session) -> dict:
    return await run_afjord_once(db=db, force=force, protocol_index=protocol_index)


async def _run_orland_job(force: bool, protocol_index: int, db: Session) -> dict:
    return await run_orland_once(db=db, force=force, protocol_index=protocol_index)


@app.post("/run/indre-fosen")
async def run_indre_fosen_post(
    force: bool = Query(default=False, description="Prosesser dokumentet selv om det er sett før."),
    protocol_index: int = Query(default=0, ge=0, description="0 er beste/siste treff. 1 er neste protokoll i lista."),
    db: Session = Depends(get_db),
) -> dict:
    return await _run_indre_fosen_job(force=force, protocol_index=protocol_index, db=db)


@app.get("/run/indre-fosen")
async def run_indre_fosen_get(
    force: bool = Query(default=False, description="Prosesser dokumentet selv om det er sett før."),
    protocol_index: int = Query(default=0, ge=0, description="0 er beste/siste treff. 1 er neste protokoll i lista."),
    db: Session = Depends(get_db),
) -> dict:
    return await _run_indre_fosen_job(force=force, protocol_index=protocol_index, db=db)


@app.post("/run/osen")
async def run_osen_post(
    force: bool = Query(default=False, description="Prosesser dokumentet selv om det er sett før."),
    protocol_index: int = Query(default=0, ge=0, description="0 er beste/siste treff. 1 er neste protokoll i lista."),
    db: Session = Depends(get_db),
) -> dict:
    return await _run_osen_job(force=force, protocol_index=protocol_index, db=db)


@app.get("/run/osen")
async def run_osen_get(
    force: bool = Query(default=False, description="Prosesser dokumentet selv om det er sett før."),
    protocol_index: int = Query(default=0, ge=0, description="0 er beste/siste treff. 1 er neste protokoll i lista."),
    db: Session = Depends(get_db),
) -> dict:
    return await _run_osen_job(force=force, protocol_index=protocol_index, db=db)


@app.post("/run/afjord")
async def run_afjord_post(
    force: bool = Query(default=False, description="Prosesser dokumentet selv om det er sett før."),
    protocol_index: int = Query(default=0, ge=0, description="0 er beste/siste treff. 1 er neste protokoll i lista."),
    db: Session = Depends(get_db),
) -> dict:
    return await _run_afjord_job(force=force, protocol_index=protocol_index, db=db)


@app.get("/run/afjord")
async def run_afjord_get(
    force: bool = Query(default=False, description="Prosesser dokumentet selv om det er sett før."),
    protocol_index: int = Query(default=0, ge=0, description="0 er beste/siste treff. 1 er neste protokoll i lista."),
    db: Session = Depends(get_db),
) -> dict:
    return await _run_afjord_job(force=force, protocol_index=protocol_index, db=db)


@app.post("/run/orland")
async def run_orland_post(
    force: bool = Query(default=False, description="Prosesser dokumentet selv om det er sett før."),
    protocol_index: int = Query(default=0, ge=0, description="0 er beste/siste treff. 1 er neste protokoll i lista."),
    db: Session = Depends(get_db),
) -> dict:
    return await _run_orland_job(force=force, protocol_index=protocol_index, db=db)


@app.get("/run/orland")
async def run_orland_get(
    force: bool = Query(default=False, description="Prosesser dokumentet selv om det er sett før."),
    protocol_index: int = Query(default=0, ge=0, description="0 er beste/siste treff. 1 er neste protokoll i lista."),
    db: Session = Depends(get_db),
) -> dict:
    return await _run_orland_job(force=force, protocol_index=protocol_index, db=db)


@app.get("/documents/indre-fosen")
async def list_indre_fosen_documents() -> list[dict]:
    links = await find_indre_fosen_documents()
    sorted_links = sorted(links, key=lambda item: item.score, reverse=True)
    return [
        {
            "protocol_index": index,
            "title": link.title,
            "document_type": link.document_type,
            "score": link.score,
            "url": link.url,
        }
        for index, link in enumerate(sorted_links)
    ]


@app.get("/documents/osen")
async def list_osen_documents() -> list[dict]:
    links = await find_osen_documents()
    sorted_links = sorted(links, key=lambda item: item.score, reverse=True)
    return [
        {
            "protocol_index": index,
            "title": link.title,
            "document_type": link.document_type,
            "score": link.score,
            "url": link.url,
        }
        for index, link in enumerate(sorted_links)
    ]


@app.get("/documents/afjord")
async def list_afjord_documents() -> list[dict]:
    links = await find_afjord_documents()
    sorted_links = sorted(links, key=lambda item: item.score, reverse=True)
    return [
        {
            "protocol_index": index,
            "title": link.title,
            "document_type": link.document_type,
            "score": link.score,
            "url": link.url,
        }
        for index, link in enumerate(sorted_links)
    ]


@app.get("/documents/orland")
async def list_orland_documents() -> list[dict]:
    links = await find_orland_documents()
    sorted_links = sorted(links, key=lambda item: item.score, reverse=True)
    return [
        {
            "protocol_index": index,
            "title": link.title,
            "document_type": link.document_type,
            "score": link.score,
            "url": link.url,
        }
        for index, link in enumerate(sorted_links)
    ]


@app.get("/test/sample-protocol")
def test_sample_protocol() -> dict:
    return run_sample_protocol_test()


@app.get("/articles/{filename}", response_class=HTMLResponse)
def get_article(filename: str) -> HTMLResponse:
    if "/" in filename or not filename.endswith(".html"):
        raise HTTPException(status_code=400, detail="Ugyldig filnavn.")
    path = settings.articles_dir / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Fant ikke artikkel.")
    return HTMLResponse(Path(path).read_text(encoding="utf-8"))
