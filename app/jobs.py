from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai_writer import article_to_html, generate_article
from app.config import ensure_directories
from app.email_sender import send_article_email
from app.parser import parse_protocol
from app.repository import is_processed, mark_processed, save_article_html, save_article_record, save_raw_document
from app.scraper import fetch_afjord_protocol, fetch_indre_fosen_protocol, fetch_orland_protocol, fetch_osen_protocol


async def run_indre_fosen_once(
    db: Session | None = None,
    force: bool = False,
    protocol_index: int = 0,
) -> dict:
    return await run_protocol_job(
        fetch_document=lambda: fetch_indre_fosen_protocol(protocol_index=protocol_index),
        db=db,
        force=force,
        protocol_index=protocol_index,
    )


async def run_osen_once(
    db: Session | None = None,
    force: bool = False,
    protocol_index: int = 0,
) -> dict:
    return await run_protocol_job(
        fetch_document=lambda: fetch_osen_protocol(protocol_index=protocol_index),
        db=db,
        force=force,
        protocol_index=protocol_index,
    )


async def run_afjord_once(
    db: Session | None = None,
    force: bool = False,
    protocol_index: int = 0,
) -> dict:
    return await run_protocol_job(
        fetch_document=lambda: fetch_afjord_protocol(protocol_index=protocol_index),
        db=db,
        force=force,
        protocol_index=protocol_index,
    )


async def run_orland_once(
    db: Session | None = None,
    force: bool = False,
    protocol_index: int = 0,
) -> dict:
    return await run_protocol_job(
        fetch_document=lambda: fetch_orland_protocol(protocol_index=protocol_index),
        db=db,
        force=force,
        protocol_index=protocol_index,
    )


async def run_protocol_job(fetch_document, db: Session | None, force: bool, protocol_index: int) -> dict:
    ensure_directories()
    document = await fetch_document()

    if not force and is_processed(document.source_url, db):
        return {
            "status": "skipped",
            "reason": "Dokumentet er allerede prosessert.",
            "municipality": document.municipality,
            "document_title": document.title,
            "source_url": document.source_url,
            "already_processed": True,
            "email_attempted": False,
            "email_sent": False,
            "protocol_index": protocol_index,
        }

    raw_path = save_raw_document(document)
    protocol = parse_protocol(document)
    article = generate_article(protocol)
    article = save_article_html(article)
    html = article_to_html(article)
    email_sent = send_article_email(article, html)
    save_article_record(article, db)
    mark_processed(document, db)

    return {
        "status": "ok",
        "municipality": document.municipality,
        "document_title": document.title,
        "source_url": document.source_url,
        "already_processed": False,
        "raw_path": str(raw_path),
        "article_title": article.title,
        "html_path": article.html_path,
        "email_attempted": True,
        "email_sent": email_sent,
        "cases_found": len(protocol.cases),
        "protocol_index": protocol_index,
        "supporting_documents": len(document.supporting_documents),
    }
