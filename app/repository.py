from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai_writer import article_to_html
from app.config import settings
from db.models import ArticleRecord, ProcessedDocument
from models.schemas import Article, MeetingDocument


def save_raw_document(document: MeetingDocument) -> Path:
    suffix = ".pdf" if "pdf" in document.content_type.lower() else ".html"
    path = settings.raw_dir / f"{document.municipality.lower().replace(' ', '-')}-{abs(hash(document.source_url))}{suffix}"
    path.write_bytes(document.content)
    return path


def save_article_html(article: Article) -> Article:
    html = article_to_html(article)
    path = settings.articles_dir / f"{article.slug}.html"
    counter = 2
    while path.exists():
        path = settings.articles_dir / f"{article.slug}-{counter}.html"
        counter += 1
    path.write_text(html, encoding="utf-8")
    article.html_path = str(path)
    return article


def is_processed(source_url: str, db: Session | None = None) -> bool:
    if db is not None:
        return db.query(ProcessedDocument).filter(ProcessedDocument.source_url == source_url).first() is not None
    return source_url in _read_state()


def mark_processed(document: MeetingDocument, db: Session | None = None) -> None:
    if db is not None:
        db.add(
            ProcessedDocument(
                source_url=document.source_url,
                municipality=document.municipality,
                title=document.title,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        return

    state = _read_state()
    state[document.source_url] = {"municipality": document.municipality, "title": document.title}
    settings.state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def save_article_record(article: Article, db: Session | None = None) -> None:
    if db is None:
        return
    db.add(
        ArticleRecord(
            slug=article.slug,
            municipality=article.municipality,
            title=article.title,
            ingress=article.ingress,
            body=article.body,
            source_url=article.source_url,
            html_path=article.html_path,
        )
    )
    db.commit()


def _read_state() -> dict[str, dict[str, str]]:
    if not settings.state_file.exists():
        return {}
    return json.loads(settings.state_file.read_text(encoding="utf-8"))
