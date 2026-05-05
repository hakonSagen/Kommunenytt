from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class DocumentLink(BaseModel):
    title: str
    url: str
    document_type: Literal["protocol", "agenda", "attachment", "unknown"] = "unknown"
    score: int = 0
    related_links: list["DocumentLink"] = Field(default_factory=list)


class SupportingDocument(BaseModel):
    title: str
    source_url: str
    document_type: str
    content_type: str
    content: bytes


class MeetingDocument(BaseModel):
    municipality: str
    source_url: str
    title: str
    document_type: str
    content_type: str
    content: bytes
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    supporting_documents: list[SupportingDocument] = Field(default_factory=list)


class ParsedCase(BaseModel):
    case_id: str | None = None
    title: str
    decision: str | None = None
    vote: str | None = None
    numbers: list[str] = Field(default_factory=list)
    source_excerpt: str


class ParsedProtocol(BaseModel):
    municipality: str
    source_url: str
    title: str
    full_text: str
    cases: list[ParsedCase]
    supporting_texts: list[str] = Field(default_factory=list)


class Article(BaseModel):
    slug: str
    municipality: str
    title: str
    ingress: str
    body: str
    social_text: str | None = None
    source_url: str
    html_path: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
