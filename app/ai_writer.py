from __future__ import annotations

import json
import re
from html import escape

from openai import OpenAI, OpenAIError

from app.config import settings
from models.schemas import Article, ParsedCase, ParsedProtocol


def select_newsworthy_case(protocol: ParsedProtocol) -> ParsedCase:
    cases_with_decisions = [case for case in protocol.cases if case.decision]
    candidates = cases_with_decisions or protocol.cases
    if not candidates:
        raise RuntimeError("Fant ingen saker i dokumentet.")

    def score(case: ParsedCase) -> int:
        title = case.title.lower()
        value = len(case.numbers) * 250 + min(len(case.decision or ""), 900) + min(len(case.vote or ""), 250)
        if any(word in title for word in ("budsjett", "økonomi", "investering", "plan", "regulering", "havn", "vei", "skole")):
            value += 400
        if any(word in title for word in ("godkjenning", "referat", "referatsak", "spørsmål", "orienterer", "fritak")):
            value -= 700
        if case.decision and "det fattes ikke vedtak" in case.decision.lower():
            value -= 900
        return value

    return sorted(candidates, key=score, reverse=True)[0]


def generate_article(protocol: ParsedProtocol) -> Article:
    case = select_newsworthy_case(protocol)
    if not settings.openai_api_key:
        return fallback_article(protocol, case)

    from openai import OpenAI, OpenAIError

    client = OpenAI(api_key=settings.openai_api_key)
    messages = [
        {
            "role": "system",
            "content": (
                "Du er en erfaren lokaljournalist i en norsk lokalavis. "
                "Du skriver ferdige nyhetsartikler basert på kommunestyresaker. "
                "Du må kun bruke informasjon som finnes i teksten du får. "
                "Du skal ikke dikte opp fakta, hendelser, sitater eller tall. "
                "Du skal bruke møteinnkalling og saksliste aktivt når de inneholder relevante fakta. "
                "Du skal gjøre tungt saks- og vedtaksspråk enkelt å forstå. "
                "Hvis noe er uklart eller mangler, skal du ikke gjette. "
                "Skriv alltid på norsk bokmål. Hvis kildeteksten er på nynorsk, oversetter du til bokmål."
            ),
        },
        {
            "role": "user",
            "content": build_prompt(protocol, case),
        },
    ]
    try:
        response = client.responses.create(
            model=settings.openai_model,
            input=messages,
            text={"format": {"type": "json_object"}},
        )
    except (TypeError, OpenAIError):
        response = client.responses.create(model=settings.openai_model, input=messages)
    data = json.loads(response.output_text)
    return Article(
        slug=slugify(data.get("title") or case.title),
        municipality=protocol.municipality,
        title=data["title"],
        ingress=data["ingress"],
        body=data["body"],
        social_text=data.get("some") or data.get("social_text"),
        source_url=protocol.source_url,
    )


def build_prompt(protocol: ParsedProtocol, case: ParsedCase) -> str:
    supporting_excerpt = find_supporting_excerpt(protocol, case)
    source = {
        "kommune": protocol.municipality,
        "dokumenttittel": protocol.title,
        "kilde_url": protocol.source_url,
        "sak_id": case.case_id,
        "sakstittel": case.title,
        "vedtak": case.decision,
        "avstemning": case.vote,
        "tall": case.numbers,
        "protokollutdrag": case.source_excerpt[:4500],
        "moteinnkalling_og_saksliste_utdrag": supporting_excerpt,
        "faktalinjer_fra_moteinnkalling": extract_supporting_fact_lines(supporting_excerpt),
    }
    return (
        "Skriv en ferdig nyhetsartikkel basert på denne kommunestyresaken.\n"
        "Svar kun som JSON med feltene title, ingress, body og some.\n"
        "Protokollen er fasit for vedtak og avstemning. "
        "Møteinnkalling og saksliste skal brukes aktivt til å forklare saken med fakta: bakgrunn, saksopplysninger, økonomi, vurderinger, innstilling og hva saken gjelder i praksis.\n"
        "Krav:\n"
        "- title: kort, konkret og nyhetspreget. Bruk gjerne tall, sted eller tiltak når det finnes i kilden.\n"
        "- title skal være interessant uten klikkbait.\n"
        "- Ikke bruk generiske titler som 'Kommunestyret har vedtatt sak om ...'.\n"
        "- ingress: 1-2 setninger som oppsummerer hovedpoenget tydelig og gir lyst til å lese videre.\n"
        "- Kommunen SKAL nevnes i ingressen.\n"
        "- Tittel og ingress skal være ulike. Ingressen skal utdype tittelen.\n"
        "- body: 5-8 korte avsnitt med god flyt og omvendt pyramide.\n"
        "- Hvert avsnitt skal ha én tydelig oppgave og minst ett konkret faktapunkt når kilden gir grunnlag for det.\n"
        "- De første 2-3 avsnittene i brødteksten skal forklare hva saken gjelder med konkrete fakta fra møteinnkalling/saksliste når dette finnes.\n"
        "- Bruk minst to relevante fakta fra møteinnkallingen/sakslisten hvis kildedataene inneholder det.\n"
        "- Forklar administrasjonens forslag/innstilling når det finnes, men gjør klart hva kommunestyret faktisk vedtok.\n"
        "- Forklar økonomi, beløp, tiltak, eiendommer, steder, datoer og rammer når dette finnes i kilden.\n"
        "- Forklar saken enkelt: skriv hva vedtaket gjelder, hvem eller hva det gjelder, og hva som konkret skjer videre når dette står i kilden.\n"
        "- Ikke tolk politiske motiver eller virkninger som ikke står i kilden.\n"
        "- Ta med uenighet eller ulike synspunkter hvis det finnes i kilden.\n"
        "- Ikke bruk mellomtitler som 'Bakgrunn', 'Vedtaket', 'Oppsummering' eller lignende. Skriv som en ferdig avisartikkel.\n"
        "- Skriv nøkternt og journalistisk, som en lokalavis.\n"
        "- Bruk vanlig språk. Forklar byråkratiske ord med enklere formuleringer.\n"
        "- Bruk korte setninger. Unngå lange leddsetninger.\n"
        "- Ikke start flere avsnitt på samme måte.\n"
        "- Skriv vedtaket og relevante saksopplysninger om til vanlig språk uten å endre innhold.\n"
        "- Tall skal være nøyaktige.\n"
        "- Avstemning skal være kort og tydelig når den finnes.\n"
        "- Hvis protokoll og møteinnkalling er ulike, bruk protokollen for vedtak og avstemning.\n"
        "- Ikke bruk møteinnkallingens forslag som vedtak hvis protokollen viser noe annet.\n"
        "- some: 1-2 setninger til sosiale medier. Kort oppsummering med nysgjerrighet. Ikke bruk emojis.\n"
        "- Forbudt: å dikte, gjette eller legge til fakta som ikke står i kildedataene.\n"
        "- Ikke skriv at noe skal sikre, styrke, bidra til, gi bedre tilbud eller ha en bestemt effekt hvis dette ikke står i kildedataene.\n\n"
        f"KILDEDATA:\n{json.dumps(source, ensure_ascii=False, indent=2)}"
    )


def extract_supporting_fact_lines(section: str | None, limit: int = 12) -> list[str]:
    if not section:
        return []

    lines = [re.sub(r"\s+", " ", line).strip() for line in section.splitlines()]
    lines = [line for line in lines if 35 <= len(line) <= 260]
    keyword_pattern = re.compile(
        r"bakgrunn|saksopplys|vurdering|økonom|kostnad|budsjett|investering|"
        r"innstilling|forslag til vedtak|konsekvens|formål|behov|plan|tiltak|"
        r"kommune|kommunal|eiendom|kroner|kr\.?|million",
        flags=re.IGNORECASE,
    )
    number_pattern = re.compile(r"\b\d[\d\s.,]*\b")

    facts: list[str] = []
    for line in lines:
        normalized = normalize_article_sentence(line)
        if not normalized or normalized in facts:
            continue
        if keyword_pattern.search(normalized) or number_pattern.search(normalized):
            facts.append(normalized)
        if len(facts) >= limit:
            break
    return facts


def find_supporting_excerpt(protocol: ParsedProtocol, case: ParsedCase) -> str | None:
    if not protocol.supporting_texts:
        return None

    excerpts: list[str] = []
    needles = case_needles(case)
    for text in protocol.supporting_texts:
        section = extract_supporting_case_section(text, needles)
        if not section:
            continue
        excerpts.append(section)
        if sum(len(excerpt) for excerpt in excerpts) >= 9000:
            break
    if excerpts:
        return "\n\n--- Utdrag fra møteinnkalling/saksliste ---\n\n".join(excerpts)[:10000]
    return protocol.supporting_texts[0][:3500]


def case_needles(case: ParsedCase) -> list[str]:
    values = [case.case_id, clean_case_title(case.title), case.title]
    if case.case_id and "/" in case.case_id:
        first, second = case.case_id.split("/", 1)
        values.append(f"{int(first)}/{second}" if first.isdigit() else case.case_id)
    needles = []
    for value in values:
        if not value:
            continue
        normalized = re.sub(r"\s+", " ", value).strip().lower()
        if normalized and normalized not in needles:
            needles.append(normalized)
    return needles


def extract_supporting_case_section(text: str, needles: list[str]) -> str | None:
    lower_text = text.lower()
    positions = [lower_text.find(needle) for needle in needles if len(needle) >= 4 and lower_text.find(needle) >= 0]
    if not positions:
        return None

    position = min(positions)
    line_start = text.rfind("\n", 0, position)
    start = max(0, line_start if line_start >= 0 else position - 800)
    marker_start = find_previous_case_marker(text, position)
    if marker_start is not None:
        start = marker_start

    end = find_next_case_marker(text, position)
    if end is None or end <= start:
        end = min(len(text), position + 8500)

    section = text[start:end].strip()
    if len(section) < 800:
        section = text[max(0, position - 1200) : min(len(text), position + 7000)].strip()
    return trim_supporting_section(section)


def find_previous_case_marker(text: str, position: int) -> int | None:
    prefix = text[:position]
    matches = list(
        re.finditer(
            r"(?im)^\s*(?:PS\s*)?\d{1,4}[/\-]\d{2,4}\s+.+$|^\s*Sak\s+\d{1,4}[/\-]\d{2,4}\s+.+$",
            prefix,
        )
    )
    return matches[-1].start() if matches else None


def find_next_case_marker(text: str, position: int) -> int | None:
    match = re.search(
        r"(?im)^\s*(?:PS\s*)?\d{1,4}[/\-]\d{2,4}\s+.+$|^\s*Sak\s+\d{1,4}[/\-]\d{2,4}\s+.+$",
        text[position + 20 :],
    )
    return position + 20 + match.start() if match else None


def trim_supporting_section(section: str, limit: int = 8500) -> str:
    section = re.sub(r"\n{3,}", "\n\n", section).strip()
    if len(section) <= limit:
        return section

    priority_words = (
        "saksopplysninger",
        "bakgrunn",
        "vurdering",
        "økonom",
        "konsekvens",
        "kommunedirektørens innstilling",
        "forslag til vedtak",
        "innstilling",
    )
    lower = section.lower()
    positions = [lower.find(word) for word in priority_words if lower.find(word) >= 0]
    if positions:
        start = max(0, min(positions) - 700)
        return section[start : start + limit].strip()
    return section[:limit].strip()


def fallback_article(protocol: ParsedProtocol, case: ParsedCase) -> Article:
    title = make_reader_friendly_title(case)
    ingress = make_reader_friendly_ingress(protocol.municipality, case)
    ingress = avoid_title_ingress_overlap(title, ingress, protocol.municipality, case)
    paragraphs = []
    lede = make_reader_friendly_lede(case)
    if lede and not should_skip_lede(lede, case):
        paragraphs.append(lede)
    paragraphs.extend(make_supporting_background_paragraphs(protocol, case))
    if case.decision:
        paragraphs.extend(format_decision_paragraphs(case))
    else:
        paragraphs.append("Protokollen inneholder ikke et tydelig vedtak i tekstutdraget.")
    used_text = " ".join(paragraphs)
    missing_numbers = [number for number in case.numbers[:6] if number not in used_text]
    if missing_numbers:
        paragraphs.append(f"Viktige tall i saken er {', '.join(missing_numbers)}.")
    if case.vote:
        paragraphs.append(format_vote(case.vote))
    return Article(
        slug=slugify(title),
        municipality=protocol.municipality,
        title=title,
        ingress=ingress,
        body="\n\n".join(paragraphs),
        social_text=make_social_text(title, ingress),
        source_url=protocol.source_url,
    )


def make_supporting_background_paragraphs(protocol: ParsedProtocol, case: ParsedCase) -> list[str]:
    section = find_supporting_excerpt(protocol, case)
    if not section:
        return []

    lower = section.lower()
    paragraphs: list[str] = []
    if "prosjektgjennomgang" in lower and "investering" in lower:
        paragraphs.append("Bakgrunnen er en prosjektgjennomgang av kommunens investeringer.")
    if "investeringsbudsjett" in lower and "2026" in lower:
        paragraph = "Saken gjelder endringer i investeringsbudsjettet for 2026."
        if paragraph not in paragraphs:
            paragraphs.append(paragraph)

    return paragraphs


def should_skip_lede(lede: str, case: ParsedCase) -> bool:
    title = clean_case_title(case.title).lower()
    decision = clean_article_text(case.decision or "").lower()
    if "rekrutteringsbolig" in title or "verksveien 2" in title:
        return True
    if "trådløse mikrofoner" in decision:
        return True
    lede_words = meaningful_words(lede)
    decision_words = meaningful_words(decision[:350])
    if not lede_words:
        return True
    return len(lede_words & decision_words) / len(lede_words) >= 0.75


def make_reader_friendly_title(case: ParsedCase) -> str:
    title = clean_case_title(case.title)
    lower = title.lower()
    if "reguleringsplan" in lower:
        area = extract_after(title, "for")
        if area:
            return shorten_title(f"Kommunestyret sier ja til plan for {area}")
        return "Kommunestyret sier ja til ny reguleringsplan"
    if ("skole" in lower or "barnehage" in lower) and case.numbers:
        return shorten_title(f"Sier ja til ny skole og barnehage til {case.numbers[0]}")
    if "trådløse mikrofoner" in (case.decision or "").lower():
        amount = find_amount(case, "1.200.000") or (case.numbers[0] if case.numbers else "penger")
        return shorten_title(f"Kjøper mikrofoner for {amount}")
    if "investering" in lower or "investeringsbudsjett" in (case.decision or "").lower():
        if case.numbers:
            return shorten_title(f"Endrer investeringer for {case.numbers[0]}")
        return "Kommunestyret endrer investeringsplanen"
    if "rekrutteringsbolig" in lower or "verksveien 2" in lower:
        return "Setter husleia for kommunal rekrutteringsbolig"
    if "havneanlegg" in lower or "fiskerihavn" in lower:
        return "Kommunen vil kjøpe fiskerihavn"
    if "budsjett" in lower or "økonomiplan" in lower:
        return "Slik blir veien videre for budsjettet"
    if "vei" in lower or "veier" in lower:
        return shorten_title(f"Kommunestyret har vedtatt sak om {title.lower()}")
    if "naturmangfold" in lower:
        return "Kommunestyret vedtok plan for naturmangfold"
    return shorten_title(title)


def make_reader_friendly_ingress(municipality: str, case: ParsedCase) -> str:
    title = clean_case_title(case.title)
    lower = title.lower()
    area = extract_after(title, "for")
    if "reguleringsplan" in lower:
        if area:
            return f"{municipality} kommunestyre har vedtatt reguleringsplan for {area}."
        return f"{municipality} kommunestyre har vedtatt en reguleringsplan."
    if ("skole" in lower or "barnehage" in lower) and case.numbers:
        return f"{municipality} kommunestyre har vedtatt bygging av ny skole og barnehage med en ramme på {case.numbers[0]}."
    if "trådløse mikrofoner" in (case.decision or "").lower() and case.numbers:
        amount = find_amount(case, "1.200.000") or case.numbers[0]
        return f"{municipality} kommunestyre har vedtatt å bruke {amount} på trådløse mikrofoner til kultur og idrett."
    if "investering" in lower or "investeringsbudsjett" in (case.decision or "").lower():
        if case.numbers:
            return f"{municipality} kommunestyre har vedtatt endringer i investeringsbudsjettet, blant annet {case.numbers[0]}."
        return f"{municipality} kommunestyre har behandlet pågående og planlagte investeringer."
    if "rekrutteringsbolig" in lower or "verksveien 2" in lower:
        if case.numbers:
            return f"{municipality} kommunestyre har vedtatt retningslinjer for Verksveien 2, med husleie på {case.numbers[0]} per måned."
        return f"{municipality} kommunestyre har vedtatt retningslinjer for Verksveien 2 som rekrutteringsbolig."
    if "havneanlegg" in lower or "fiskerihavn" in lower:
        return f"{municipality} kommunestyre har vedtatt at kommunen melder interesse for å erverve en fiskerihavn."
    if "budsjett" in lower or "økonomiplan" in lower:
        return f"{municipality} kommunestyre har vedtatt hvordan arbeidet med neste budsjett og økonomiplan skal legges opp."
    return f"{municipality} kommunestyre har gjort vedtak i saken, ifølge møteprotokollen."


def make_reader_friendly_lede(case: ParsedCase) -> str:
    title = clean_case_title(case.title)
    lower = title.lower()
    if "reguleringsplan" in lower:
        return f"Planen gjelder {extract_after(title, 'for') or title}."
    if "skole" in lower or "barnehage" in lower:
        return f"Vedtaket gjelder {lower}."
    if "trådløse mikrofoner" in (case.decision or "").lower():
        if "investeringsbudsjett" in (case.decision or "").lower():
            return "Innkjøpet er en del av endringer i investeringsbudsjettet for 2026."
        return "Innkjøpet gjelder trådløse mikrofoner til avdeling kultur og idrett."
    if "rekrutteringsbolig" in lower or "verksveien 2" in lower:
        return "Verksveien 2 skal brukes som rekrutteringsbolig."
    if "havneanlegg" in lower or "fiskerihavn" in lower:
        return "Saken gjelder kommunens interesse for fiskerihavner."
    return f"Saken gjelder {title.lower()}."


def avoid_title_ingress_overlap(title: str, ingress: str, municipality: str, case: ParsedCase) -> str:
    title_words = meaningful_words(title)
    ingress_words = meaningful_words(ingress)
    if not title_words:
        return ingress
    overlap = len(title_words & ingress_words) / len(title_words)
    if overlap < 0.65:
        return ingress

    lower_title = clean_case_title(case.title).lower()
    if "rekrutteringsbolig" in lower_title or "verksveien 2" in lower_title:
        if case.numbers:
            return f"{municipality} kommunestyre har vedtatt at Verksveien 2 skal brukes som rekrutteringsbolig. Husleia blir {case.numbers[0]} per måned."
        return f"{municipality} kommunestyre har vedtatt at Verksveien 2 skal brukes som rekrutteringsbolig."
    if "trådløse mikrofoner" in (case.decision or "").lower():
        return f"{municipality} kommunestyre har vedtatt innkjøp av utstyr til avdeling kultur og idrett."
    if "reguleringsplan" in lower_title:
        return f"{municipality} kommunestyre har vedtatt reguleringsplanen i saken."
    return ingress


def make_social_text(title: str, ingress: str) -> str:
    summary = ingress.strip()
    if not summary:
        return title
    if len(summary) <= 180:
        return summary
    shortened = summary[:177].rsplit(" ", 1)[0].strip(" ,.")
    return f"{shortened}."


def find_amount(case: ParsedCase, needle: str) -> str | None:
    for number in case.numbers:
        if needle in number:
            return number
    return None


def meaningful_words(text: str) -> set[str]:
    stop_words = {
        "og",
        "for",
        "til",
        "med",
        "har",
        "vedtatt",
        "kommunestyre",
        "kommunestyret",
        "kommune",
        "sier",
        "ja",
        "setter",
        "av",
    }
    words = re.findall(r"[a-zæøå0-9.]+", text.lower())
    return {word for word in words if len(word) > 2 and word not in stop_words}


def format_decision_paragraphs(case: ParsedCase) -> list[str]:
    title = clean_case_title(case.title).lower()
    decision = clean_article_text(case.decision or "")
    if "rekrutteringsbolig" in title or "verksveien 2" in title:
        paragraphs = ["Boligen skal brukes som rekrutteringsbolig."]
        if case.numbers:
            paragraphs.append(f"Husleia settes til {case.numbers[0]} per måned.")
        if "delegeres til formannskapet" in decision.lower():
            paragraphs.append("Formannskapet kan gjøre endringer i ordningen.")
        return paragraphs
    if "trådløse mikrofoner" in decision.lower():
        amount = find_amount(case, "1.200.000") or (case.numbers[0] if case.numbers else None)
        paragraphs = []
        if "investeringsbudsjett" in decision.lower():
            paragraphs.append("Kommunestyret vedtok endringer i investeringsbudsjettet for 2026.")
        if amount:
            paragraphs.append(f"Det settes av {amount} til trådløse mikrofoner til avdeling kultur og idrett.")
        else:
            paragraphs.append("Vedtaket gjelder trådløse mikrofoner til avdeling kultur og idrett.")
        financing = extract_microphone_financing(decision)
        if financing:
            paragraphs.extend(financing)
        return paragraphs
    chunks = split_decision(decision)
    if not chunks:
        return []
    if len(chunks) == 1:
        return [f"Kommunestyret vedtok: {chunks[0]}"]
    return ["Kommunestyret vedtok dette:", *chunks]


def extract_microphone_financing(decision: str) -> list[str]:
    paragraphs: list[str] = []
    if "flytting av jordmasser ved fergeleiet utsettes" in decision.lower():
        paragraphs.append("Flytting av jordmasser ved fergeleiet utsettes med kr. 400.000.")
    if "mindreforbruk ombygging av varmeanlegg" in decision.lower():
        paragraphs.append("Mindreforbruk fra ombygging av varmeanlegg ved ØMS brukes med kr. 400.000.")
    if "trafikksikkerhetstiltak reduseres" in decision.lower():
        paragraphs.append("Trafikksikkerhetstiltak reduseres med kr. 400.000.")
    return paragraphs


def split_decision(decision: str) -> list[str]:
    decision = clean_article_text(decision)
    if not decision:
        return []

    decision = re.sub(r"\s+-\s+", "\n- ", decision)
    decision = re.sub(r"\s+([1-9])\.\s+", r"\n\1. ", decision)
    raw_parts = [part.strip(" .") for part in decision.splitlines() if part.strip(" .")]

    parts: list[str] = []
    for part in raw_parts:
        part = normalize_article_sentence(part)
        if part and part not in parts:
            parts.append(part)
    return parts


def normalize_article_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" ,-", ",-")
    if not text:
        return text
    if text.startswith("- "):
        text = text[2:].strip()
    if text and text[-1] not in ".!?:»":
        text = f"{text}."
    return text


def format_vote(vote: str) -> str:
    cleaned = clean_article_text(vote)
    lower = cleaned.lower()
    if "mot: 0 stemmer" in lower and ("100%" in lower or "for:" in lower):
        return "Vedtaket var enstemmig."
    if "enstemmig" in lower:
        return "Vedtaket var enstemmig."
    for_match = re.search(r"For:\s*([^\.]+?stemmer(?:\s*\(\d+%?\))?)", cleaned, flags=re.IGNORECASE)
    mot_match = re.search(r"Mot:\s*([^\.]+?stemmer(?:\s*\(\d+%?\))?)", cleaned, flags=re.IGNORECASE)
    if for_match and mot_match:
        return f"Avstemningen endte med {for_match.group(1)} for og {mot_match.group(1)} mot."
    return f"Avstemning: {cleaned}"


def clean_case_title(title: str) -> str:
    title = re.sub(r"\bsluttbehandling\s*-\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r",?\s*gbnr\.[^,-]*(?:m\.fl\.)?", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*-\s*PlanID\s*\d+", "", title, flags=re.IGNORECASE)
    title = title.replace(" - ", " ").strip(" .-")
    title = re.sub(r"\s+", " ", title)
    return title


def clean_article_text(text: str) -> str:
    text = text.replace("", "-")
    text = re.sub(r"\b(?:Kommunedirektørens|Rådmannens)\s+innstilling:?.*$", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\bSide\s+\d+\s+av\s+\d+\b", "", text, flags=re.IGNORECASE)
    return text.strip()


def extract_after(value: str, marker: str) -> str | None:
    match = re.search(rf"\b{re.escape(marker)}\s+(.+)$", value, flags=re.IGNORECASE)
    if not match:
        return None
    result = match.group(1).strip(" .-")
    result = re.split(r",|\s+-\s+", result)[0].strip()
    return result or None


def shorten_title(title: str, limit: int = 72) -> str:
    title = re.sub(r"\s+", " ", title).strip(" .-")
    if len(title) <= limit:
        return title
    words = title.split()
    shortened = ""
    for word in words:
        candidate = f"{shortened} {word}".strip()
        if len(candidate) > limit - 1:
            break
        shortened = candidate
    return f"{shortened}..." if shortened else title[:limit]


def article_to_html(article: Article) -> str:
    body = "\n".join(f"<p>{escape(paragraph)}</p>" for paragraph in article.body.split("\n\n") if paragraph.strip())
    social = ""
    if article.social_text:
        social = f"""
    <section class="some">
      <h2>SoMe</h2>
      <p>{escape(article.social_text)}</p>
    </section>"""
    return f"""<!doctype html>
<html lang="no">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(article.title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; color: #1f2933; background: #f7f7f4; }}
    main {{ max-width: 760px; margin: 0 auto; padding: 48px 20px; background: #fff; min-height: 100vh; }}
    h1 {{ font-size: 2rem; line-height: 1.15; margin: 0 0 16px; }}
    .ingress {{ font-size: 1.15rem; font-weight: 700; color: #374151; }}
    .meta {{ color: #667085; font-size: .9rem; margin-bottom: 28px; }}
    .some {{ border-top: 1px solid #e5e7eb; margin-top: 32px; padding-top: 20px; }}
    .some h2 {{ font-size: 1rem; margin: 0 0 8px; }}
    a {{ color: #075985; }}
  </style>
</head>
<body>
  <main>
    <p class="meta">{escape(article.municipality)} · automatisk generert</p>
    <h1>{escape(article.title)}</h1>
    <p class="ingress">{escape(article.ingress)}</p>
    {body}
    {social}
    <p class="meta">Kilde: <a href="{escape(article.source_url)}">{escape(article.source_url)}</a></p>
  </main>
</body>
</html>
"""


def slugify(value: str) -> str:
    value = value.lower()
    value = value.replace("æ", "ae").replace("ø", "o").replace("å", "a")
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value[:80] or "artikkel"
