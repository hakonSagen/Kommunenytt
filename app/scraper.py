from __future__ import annotations

import hashlib
import re
import urllib.request
from urllib.parse import urljoin, urlparse

from playwright.async_api import Page, Route, async_playwright

from app.config import settings
from models.schemas import DocumentLink, MeetingDocument, SupportingDocument


PROTOCOL_WORDS = ("møteprotokoll", "protokoll", "vedtaksprotokoll")
AGENDA_WORDS = ("saksliste", "innkalling")
CHROMIUM_ARGS = [
    "--disable-dev-shm-usage",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-gpu",
    "--no-sandbox",
]


async def fetch_indre_fosen_protocol(protocol_index: int = 0) -> MeetingDocument:
    return await fetch_protocol_from_links(
        links=await find_indre_fosen_documents(min_protocols=protocol_index + 1),
        municipality="Indre Fosen",
        protocol_index=protocol_index,
    )


async def fetch_osen_protocol(protocol_index: int = 0) -> MeetingDocument:
    return await fetch_protocol_from_links(
        links=await find_osen_documents(min_protocols=protocol_index + 1),
        municipality="Osen",
        protocol_index=protocol_index,
    )


async def fetch_afjord_protocol(protocol_index: int = 0) -> MeetingDocument:
    return await fetch_protocol_from_links(
        links=await find_afjord_documents(min_protocols=protocol_index + 1),
        municipality="Åfjord",
        protocol_index=protocol_index,
    )


async def fetch_orland_protocol(protocol_index: int = 0) -> MeetingDocument:
    return await fetch_protocol_from_links(
        links=await find_orland_documents(min_protocols=protocol_index + 1),
        municipality="Ørland",
        protocol_index=protocol_index,
    )


async def fetch_indre_fosen_latest_protocol() -> MeetingDocument:
    return await fetch_indre_fosen_protocol(protocol_index=0)


async def fetch_protocol_from_links(
    links: list[DocumentLink],
    municipality: str,
    protocol_index: int = 0,
) -> MeetingDocument:
    protocol_links = [link for link in links if link.document_type == "protocol"]
    candidates = protocol_links or links
    if not candidates:
        raise RuntimeError(f"Fant ingen dokumentlenker for {municipality}.")

    sorted_candidates = sorted(candidates, key=lambda item: item.score, reverse=True)
    if protocol_index >= len(sorted_candidates):
        raise RuntimeError(
            f"Fant bare {len(sorted_candidates)} aktuelle dokumenter. "
            f"protocol_index={protocol_index} er utenfor lista."
        )

    selected = sorted_candidates[protocol_index]
    return await download_document(selected, municipality=municipality)


async def find_indre_fosen_documents(min_protocols: int = 8) -> list[DocumentLink]:
    return await find_acos_meeting_documents(settings.indre_fosen_url, min_protocols=min_protocols)


async def find_osen_documents(min_protocols: int = 8) -> list[DocumentLink]:
    return await find_acos_meeting_documents(settings.osen_url, min_protocols=min_protocols)


async def find_afjord_documents(min_protocols: int = 8) -> list[DocumentLink]:
    return await find_acos_meeting_documents(settings.afjord_url, min_protocols=min_protocols)


async def find_orland_documents(min_protocols: int = 8) -> list[DocumentLink]:
    return await find_acos_meeting_documents(settings.orland_url, min_protocols=min_protocols)


async def find_acos_meeting_documents(base_url: str, min_protocols: int = 8) -> list[DocumentLink]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=CHROMIUM_ARGS)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.route("**/*", _block_heavy_resource)
            await page.goto(base_url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(2500)
            await _dismiss_cookie_dialog(page)
            detail_links = await _collect_held_meeting_detail_links(page, base_url=base_url, max_pages=2)
            protocol_links = await _collect_protocol_links_from_details(
                page,
                detail_links,
                base_url=base_url,
                min_protocols=min_protocols,
            )
            if protocol_links:
                return protocol_links

            await _try_expand_document_lists(page)
            return await _collect_document_links(page, base_url)
        finally:
            await browser.close()


async def _block_heavy_resource(route: Route) -> None:
    if route.request.resource_type in {"image", "media", "font", "stylesheet"}:
        await route.abort()
        return
    await route.continue_()


async def _dismiss_cookie_dialog(page: Page) -> None:
    for label in ("Kun nødvendige", "Godta alle"):
        try:
            await page.get_by_text(label, exact=True).click(timeout=2500)
            await page.wait_for_timeout(500)
            return
        except Exception:
            continue
    try:
        await page.get_by_text("Skjul denne meldingen", exact=True).click(timeout=1500)
        await page.wait_for_timeout(300)
    except Exception:
        pass


async def _collect_held_meeting_detail_links(page: Page, base_url: str, max_pages: int = 4) -> list[str]:
    detail_links: list[str] = []
    try:
        await page.get_by_text("Gjennomførte møter", exact=True).click(timeout=10_000)
        await page.wait_for_timeout(2500)
    except Exception:
        pass

    for _ in range(max_pages):
        for link in await _collect_detail_links_from_current_page(page, base_url=base_url):
            if link not in detail_links:
                detail_links.append(link)
        try:
            await page.get_by_label("Gå til neste side").click(timeout=4000)
            await page.wait_for_timeout(2500)
        except Exception:
            break
    return detail_links


async def _collect_detail_links_from_current_page(page: Page, base_url: str) -> list[str]:
    links: list[str] = []
    anchors = await page.locator("a[href]").all()
    for anchor in anchors:
        try:
            href = await anchor.get_attribute("href")
            text = await anchor.inner_text(timeout=1000)
            aria_label = await anchor.get_attribute("aria-label") or ""
        except Exception:
            continue
        haystack = f"{text} {aria_label} {href}".lower()
        if href and "details/m-" in href and ("kommunestyret" in haystack or "kommunestyre" in haystack):
            links.append(urljoin(base_url, href))
    return links


async def _collect_protocol_links_from_details(
    page: Page,
    detail_links: list[str],
    base_url: str,
    min_protocols: int,
) -> list[DocumentLink]:
    protocol_links: list[DocumentLink] = []
    for detail_url in detail_links[:8]:
        try:
            await page.goto(detail_url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(1200)
        except Exception:
            continue

        meeting_title = await _meeting_title_from_page(page)
        anchors = await page.locator("a[href]").all()
        agenda_links: list[DocumentLink] = []
        protocol_candidates: list[DocumentLink] = []
        for anchor in anchors:
            try:
                href = await anchor.get_attribute("href")
                text = normalize_text(await anchor.inner_text(timeout=1000))
            except Exception:
                continue
            if not href:
                continue
            haystack = f"{text} {href}".lower()
            if "ikke publisert" in haystack:
                continue
            if "møteinnkalling" in haystack or "moteinnkalling" in haystack:
                agenda_links.append(
                    DocumentLink(
                        title=normalize_text(f"{meeting_title} - {text}"),
                        url=urljoin(base_url, href),
                        document_type="agenda",
                        score=150,
                    )
                )
                continue
            if "møteprotokoll" not in haystack and "moteprotokoll" not in haystack:
                continue
            protocol_candidates.append(
                DocumentLink(
                    title=normalize_text(f"{meeting_title} - {text}"),
                    url=urljoin(base_url, href),
                    document_type="protocol",
                    score=200,
                )
            )
        for protocol_link in protocol_candidates:
            protocol_link.related_links = agenda_links
            protocol_links.append(protocol_link)
            if len(protocol_links) >= min_protocols:
                return protocol_links
    return protocol_links


async def _meeting_title_from_page(page: Page) -> str:
    text = await page.locator("body").inner_text()
    lines = [normalize_text(line) for line in text.splitlines() if normalize_text(line)]
    date = None
    for index, line in enumerate(lines):
        if line == "Dato:" and index + 1 < len(lines):
            date = lines[index + 1]
            break
    return f"Kommunestyret {date}" if date else "Kommunestyret"


async def download_document(link: DocumentLink, municipality: str) -> MeetingDocument:
    content_type, content = _http_get(link.url)
    supporting_documents = []
    for related_link in link.related_links:
        try:
            supporting_documents.append(_download_supporting_document(related_link))
        except Exception:
            continue

    return MeetingDocument(
        municipality=municipality,
        source_url=link.url,
        title=link.title,
        document_type=link.document_type,
        content_type=content_type,
        content=content,
        supporting_documents=supporting_documents,
    )


def _http_get(url: str) -> tuple[str, bytes]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Kommunenytt/1.0 (+https://kommunenytt-web.onrender.com)",
            "Accept": "application/pdf,text/html,application/octet-stream,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        content_type = response.headers.get("content-type", "application/octet-stream")
        return content_type, response.read()


def _download_supporting_document(link: DocumentLink) -> SupportingDocument:
    content_type, content = _http_get(link.url)
    return SupportingDocument(
        title=link.title,
        source_url=link.url,
        document_type=link.document_type,
        content_type=content_type,
        content=content,
    )


async def _try_expand_document_lists(page: Page) -> None:
    selectors = [
        "button[aria-expanded='false']",
        "[role='button'][aria-expanded='false']",
        "summary",
    ]
    for selector in selectors:
        locators = await page.locator(selector).all()
        for locator in locators[:15]:
            try:
                tag_name = await locator.evaluate("node => node.tagName.toLowerCase()")
                href = await locator.get_attribute("href")
                if tag_name == "a" or href:
                    continue
                await locator.click(timeout=1000)
            except Exception:
                continue
    await page.wait_for_timeout(1000)


async def _collect_document_links(page: Page, base_url: str) -> list[DocumentLink]:
    raw_links: list[tuple[str, str]] = []
    frames = [page.main_frame, *page.frames]
    seen_frames = set()

    for frame in frames:
        if frame in seen_frames:
            continue
        seen_frames.add(frame)
        try:
            anchors = await frame.locator("a[href]").all()
        except Exception:
            continue
        for anchor in anchors:
            try:
                href = await anchor.get_attribute("href")
                text = await anchor.inner_text(timeout=1000)
            except Exception:
                continue
            if href:
                absolute_url = urljoin(base_url, href)
                if _is_allowed_direct_link(absolute_url):
                    raw_links.append((normalize_text(text), absolute_url))

    scored = [_score_link(text, href) for text, href in raw_links]
    unique: dict[str, DocumentLink] = {}
    for link in scored:
        if link.score <= 0:
            continue
        previous = unique.get(link.url)
        if previous is None or link.score > previous.score:
            unique[link.url] = link
    return list(unique.values())


def _is_allowed_direct_link(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return True


def _score_link(text: str, href: str) -> DocumentLink:
    haystack = f"{text} {href}".lower()
    score = 0
    document_type = "unknown"

    if any(word in haystack for word in PROTOCOL_WORDS):
        score += 100
        document_type = "protocol"
    if any(word in haystack for word in AGENDA_WORDS):
        score += 60
        document_type = "agenda"
    if "kommunesty" in haystack:
        score += 25
    if href.lower().endswith(".pdf") or ".pdf" in urlparse(href).path.lower():
        score += 20
    if any(word in haystack for word in ("politikk", "mote", "møte", "sak")):
        score += 10

    title = text or filename_from_url(href) or "Ukjent dokument"
    return DocumentLink(title=title[:250], url=href, document_type=document_type, score=score)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def filename_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return hashlib.sha256(url.encode()).hexdigest()[:12]
    return path.split("/")[-1].replace("-", " ").replace("_", " ")
