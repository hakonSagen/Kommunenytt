from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


class ProcessedDocument(Base):
    __tablename__ = "processed_documents"
    __table_args__ = (UniqueConstraint("source_url", name="uq_processed_source_url"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    municipality: Mapped[str] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ArticleRecord(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    slug: Mapped[str] = mapped_column(unique=True, index=True)
    municipality: Mapped[str] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    ingress: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    html_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
