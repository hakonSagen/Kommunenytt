from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import settings
from models.schemas import Article


def send_article_email(article: Article, html: str) -> bool:
    if settings.dry_run_email:
        print(f"DRY_RUN_EMAIL=true: ville sendt artikkel til {settings.smtp_to}: {article.title}")
        return False

    required = [settings.smtp_host, settings.smtp_username, settings.smtp_password, settings.smtp_to]
    if not all(required):
        raise RuntimeError("SMTP mangler konfigurasjon. Sjekk SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD og SMTP_TO.")

    message = EmailMessage()
    message["Subject"] = article.title
    message["From"] = settings.smtp_from
    message["To"] = settings.smtp_to
    social = f"\n\nSoMe:\n{article.social_text}" if article.social_text else ""
    message.set_content(f"{article.ingress}\n\n{article.body}{social}\n\nKilde: {article.source_url}")
    message.add_alternative(html, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
    return True
