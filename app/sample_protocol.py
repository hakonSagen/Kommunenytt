from __future__ import annotations

from app.ai_writer import fallback_article
from app.parser import extract_cases
from app.repository import save_article_html
from models.schemas import ParsedProtocol


SAMPLE_PROTOCOL_TEXT = """
Moteprotokoll
Kommunestyret

PS 12/2026 Rehabilitering av kommunal vei ved skoleomradet
Behandling
Kommunestyret behandlet saken i mote.
Avstemning:
Innstillingen ble vedtatt med 21 mot 4 stemmer.
Kommunestyrets vedtak:
Kommunestyret bevilger 4 500 000 kroner til rehabilitering av kommunal vei ved skoleomradet.
Tiltaket finansieres innenfor vedtatt investeringsbudsjett for 2026.

PS 13/2026 Justering av foreldrebetaling i SFO
Behandling
Kommunestyret behandlet saken etter innstilling fra formannskapet.
Avstemning:
Forslaget ble enstemmig vedtatt.
Kommunestyrets vedtak:
Foreldrebetalingen i SFO justeres med 3 prosent fra 1. august 2026.
Kommunedirektoren bes informere berorte foresatte for oppstart av nytt skolear.
"""


def run_sample_protocol_test() -> dict:
    cases = extract_cases(SAMPLE_PROTOCOL_TEXT)
    protocol = ParsedProtocol(
        municipality="Testkommune",
        source_url="local://sample-protocol",
        title="Eksempelprotokoll fra kommunestyret",
        full_text=SAMPLE_PROTOCOL_TEXT,
        cases=cases,
    )
    article = fallback_article(protocol, cases[0])
    return {
        "status": "ok",
        "note": "Dette er en lokal test-fixture. Den henter ikke nettdata, bruker ikke OpenAI og sender ikke e-post.",
        "cases_found": len(cases),
        "cases": [case.model_dump() for case in cases],
        "sample_article": article.model_dump(mode="json"),
    }


def write_sample_article() -> str:
    cases = extract_cases(SAMPLE_PROTOCOL_TEXT)
    protocol = ParsedProtocol(
        municipality="Testkommune",
        source_url="local://sample-protocol",
        title="Eksempelprotokoll fra kommunestyret",
        full_text=SAMPLE_PROTOCOL_TEXT,
        cases=cases,
    )
    article = fallback_article(protocol, cases[0])
    article.slug = "testartikkel-kommunestyre-vei"
    article.title = "Kommunestyret bevilger 4,5 millioner til kommunal vei"
    article.ingress = "Kommunestyret har vedtatt å bruke 4,5 millioner kroner på rehabilitering av en kommunal vei ved skoleområdet."
    article.body = (
        "Kommunestyret har behandlet saken om rehabilitering av kommunal vei ved skoleområdet.\n\n"
        "Vedtaket går ut på å bevilge 4 500 000 kroner til arbeidet. Ifølge protokollen skal tiltaket finansieres innenfor vedtatt investeringsbudsjett for 2026.\n\n"
        "Innstillingen ble vedtatt med 21 mot 4 stemmer.\n\n"
        "For innbyggerne betyr vedtaket at kommunen prioriterer opprusting av veien ved skoleområdet."
    )
    saved = save_article_html(article)
    return saved.html_path or ""


if __name__ == "__main__":
    import json

    result = run_sample_protocol_test()
    result["written_article_path"] = write_sample_article()
    print(json.dumps(result, ensure_ascii=False, indent=2))
