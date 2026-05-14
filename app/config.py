from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    app_name: str = "Kommunenytt Robotjournalist"
    articles_dir: Path = BASE_DIR / "articles"
    raw_dir: Path = BASE_DIR / "data" / "raw"
    processed_dir: Path = BASE_DIR / "data" / "processed"
    state_file: Path = BASE_DIR / "data" / "processed" / "processed_documents.json"

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.2")

    database_url: str | None = os.getenv("DATABASE_URL")

    smtp_host: str | None = os.getenv("SMTP_HOST")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str | None = os.getenv("SMTP_USERNAME")
    smtp_password: str | None = os.getenv("SMTP_PASSWORD")
    smtp_from: str = os.getenv("SMTP_FROM", "robotjournalist@example.com")
    smtp_to: str | None = os.getenv("SMTP_TO")
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    dry_run_email: bool = os.getenv("DRY_RUN_EMAIL", "true").lower() == "true"
    skip_weekend_email: bool = os.getenv("SKIP_WEEKEND_EMAIL", "true").lower() == "true"
    email_timezone: str = os.getenv("EMAIL_TIMEZONE", "Europe/Oslo")

    indre_fosen_url: str = os.getenv(
        "INDRE_FOSEN_URL",
        "https://www.indrefosen.kommune.no/tjenester/politikk-planer-og-okonomi/politikk/moteoversikt-og-sok-etter-vedtak/",
    )
    osen_url: str = os.getenv(
        "OSEN_URL",
        "https://www.osen.kommune.no/vare-tjenester/politikk-planer-og-organisasjon/politikk/politiske-moter-og-saksdokumenter/",
    )
    afjord_url: str = os.getenv(
        "AFJORD_URL",
        "https://www.afjord.kommune.no/tjenester/politikk-planer-og-organisasjon/politikk-og-okonomi/politisk-moteplan-og-saksdokumenter/",
    )
    orland_url: str = os.getenv(
        "ORLAND_URL",
        "https://www.orland.kommune.no/vare-tjenester/politikk-planer-og-organisasjon/politikk/politisk-moteplan/",
    )


settings = Settings()


def ensure_directories() -> None:
    for path in (settings.articles_dir, settings.raw_dir, settings.processed_dir):
        path.mkdir(parents=True, exist_ok=True)
