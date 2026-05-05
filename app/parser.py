from __future__ import annotations

import re
from io import BytesIO

from bs4 import BeautifulSoup
from pypdf import PdfReader

from models.schemas import MeetingDocument, ParsedCase, ParsedProtocol


CASE_MARKER_RE = re.compile(
    r"(?im)^\s*((?:(?:PS|RS|DS|OS|FO|Sak)\s*)?\d{1,4}[/\-]\d{2,4})\s+(.+)$"
)
DECISION_RE = re.compile(
    r"(?is)(?:(?:KST|KOM)\s*-\s*\d{1,4}[/\-]\d{2,4}\s+vedtak|vedtak|kommunestyrets vedtak|formannskapets innstilling)\s*[:\-]?\s*(.+?)(?=\n\s*(?:behandling|avstemning|votering|votering nr|kommunedirektørens forslag|kommunedirektørens innstilling|formannskapet\s+\d{2}\.\d{2}\.\d{4}|FSK\s*-|\d{1,4}[/\-]\d{2,4}\s+.+|PS\s+\d|RS\s+\d|Sak\s+\d)|\Z)"
)
VOTE_RE = re.compile(
    r"(?is)(?:avstemning|votering(?:\s+nr\s+\d+)?(?:\s*-\s*votering over forslag)?)\s*[:\-]?\s*(.+?)(?=\n\s*(?:(?:KST|KOM)\s*-\s*\d{1,4}[/\-]\d{2,4}\s+vedtak|FSK\s*-\s*\d{1,4}[/\-]\d{2,4}\s+vedtak|vedtak|kommunestyrets vedtak|formannskapets innstilling|\d{1,4}[/\-]\d{2,4}\s+.+|PS\s+\d|RS\s+\d|Sak\s+\d)|\Z)"
)
NUMBER_RE = re.compile(
    r"\b(?:kr\.?\s*)?(?:\d{1,3}(?:[ .]\d{3})+|\d+)(?:,\d+)?\s*(?:mill\.?|millioner|mrd\.?|kroner|prosent|%)?\b",
    re.IGNORECASE,
)


def document_to_text(document: MeetingDocument) -> str:
    if "pdf" in document.content_type.lower() or document.source_url.lower().endswith(".pdf"):
        return pdf_to_text(document.content)
    return html_to_text(document.content.decode("utf-8", errors="ignore"))


def pdf_to_text(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return clean_text("\n".join(pages))


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "noscript", "svg"]):
        element.decompose()
    return clean_text(soup.get_text("\n"))


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\bSide\s+\d+\s+av\s+\d+\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def parse_protocol(document: MeetingDocument) -> ParsedProtocol:
    full_text = document_to_text(document)
    supporting_texts = []
    for supporting_document in document.supporting_documents:
        try:
            supporting_texts.append(document_to_text(supporting_document))
        except Exception:
            continue
    cases = extract_cases(full_text)
    return ParsedProtocol(
        municipality=document.municipality,
        source_url=document.source_url,
        title=document.title,
        full_text=full_text,
        cases=cases,
        supporting_texts=supporting_texts,
    )


def extract_cases(text: str) -> list[ParsedCase]:
    matches = list(CASE_MARKER_RE.finditer(text))
    if not matches:
        return [
            ParsedCase(
                title=first_meaningful_line(text) or "Ukjent sak",
                decision=extract_decision(text),
                vote=extract_vote(text),
                numbers=extract_numbers(text),
                source_excerpt=text[:3000],
            )
        ]

    cases: list[ParsedCase] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        case_id = normalize_space(match.group(1))
        title = extract_case_title(match, chunk) or first_meaningful_line(chunk.replace(match.group(0), "", 1))
        if not title:
            title = case_id
        cases.append(
            ParsedCase(
                case_id=case_id,
                title=title,
                decision=extract_decision(chunk),
                vote=extract_vote(chunk),
                numbers=extract_numbers(chunk),
                source_excerpt=chunk[:3000],
            )
        )
    return cases


def extract_decision(text: str) -> str | None:
    match = DECISION_RE.search(text)
    if not match:
        return None
    return normalize_space(match.group(1))[:1800]


def extract_case_title(match: re.Match[str], chunk: str) -> str | None:
    title_parts = [normalize_space(match.group(2)).rstrip(" -")]
    lines = chunk.splitlines()
    for line in lines[1:4]:
        cleaned = normalize_space(line).strip(" -")
        lower = cleaned.lower()
        if not cleaned:
            continue
        if (
            CASE_MARKER_RE.match(cleaned)
            or lower.startswith(
                (
                    "kommunestyret ",
                    "kommunestyre ",
                    "formannskap",
                    "behandling",
                    "votering",
                    "kst -",
                    "kom -",
                    "fsk -",
                    "kommunedirektørens innstilling",
                    "rådmannens innstilling",
                )
            )
            or lower in {"saksliste", "saksnr sakstittel"}
        ):
            break
        title_parts.append(cleaned)
    title = normalize_space(" ".join(part for part in title_parts if part))
    return title or None


def extract_vote(text: str) -> str | None:
    match = VOTE_RE.search(text)
    if not match:
        return None
    return normalize_space(match.group(1))[:800]


def extract_numbers(text: str) -> list[str]:
    text = CASE_MARKER_RE.sub("", text)
    seen: set[str] = set()
    numbers: list[str] = []
    for match in NUMBER_RE.finditer(text):
        value = normalize_space(match.group(0))
        lower_value = value.lower()
        has_unit = any(unit in lower_value for unit in ("kr", "kroner", "prosent", "%", "mill", "millioner", "mrd"))
        has_grouped_digits = bool(re.search(r"\d[ .]\d", value))
        if not has_unit and not has_grouped_digits:
            continue
        if value not in seen:
            seen.add(value)
            numbers.append(value)
        if len(numbers) >= 20:
            break
    return numbers


def first_meaningful_line(text: str) -> str | None:
    for line in text.splitlines():
        line = normalize_space(line)
        if len(line) > 5 and not line.lower().startswith(("side ", "møteprotokoll", "saksliste")):
            return line[:180]
    return None


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()
