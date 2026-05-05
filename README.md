# Kommunenytt Robotjournalist

MVP for en automatisert lokalavis som henter kommunale møtedokumenter, parser protokolltekst, lager en kort faktabasert nyhetssak med OpenAI API, lagrer artikkelen som HTML og sender den på e-post.

Denne første versjonen bruker informasjon og direkte lenker fra disse kommunesidene:

https://www.indrefosen.kommune.no/tjenester/politikk-planer-og-okonomi/politikk/moteoversikt-og-sok-etter-vedtak/

https://www.osen.kommune.no/vare-tjenester/politikk-planer-og-organisasjon/politikk/politiske-moter-og-saksdokumenter/

https://www.afjord.kommune.no/tjenester/politikk-planer-og-organisasjon/politikk-og-okonomi/politisk-moteplan-og-saksdokumenter/

https://www.orland.kommune.no/vare-tjenester/politikk-planer-og-organisasjon/politikk/politisk-moteplan/

## Hva MVP-en gjør

- Leser de oppgitte kommunesidene med Playwright
- Utvider eventuelle knapper/accordion-elementer på siden
- Finner direkte lenker på siden som ligner på møteprotokoll, saksliste eller kommunestyredokument
- Henter én protokoll
- Kobler møteinnkalling fra samme møte til protokollen når den er publisert
- Konverterer PDF eller HTML til tekst
- Prøver å identifisere sakstitler, vedtak, avstemning og tall
- Bruker møteinnkalling og saksliste som bakgrunnskilder, mens protokollen styrer vedtak og avstemning
- Genererer én kort nyhetssak
- Lagrer HTML i `articles/`
- Sender artikkelen via SMTP, eller tørrkjører e-post når `DRY_RUN_EMAIL=true`
- Hopper over dokumenter som allerede er prosessert
- Følger Fosna-Folkets skriveregler for KI-saker, se `docs/fosna-folket-ki-stil.md`

## Prosjektstruktur

```text
app/
  main.py          FastAPI-app
  scraper.py       Playwright-scraper for Indre Fosen, Osen, Åfjord og Ørland
  parser.py        PDF/HTML til strukturert tekst
  ai_writer.py     OpenAI-basert artikkelgenerator
  email_sender.py  SMTP-sending
  jobs.py          Orkestrerer hele robotjournalist-jobben
  cli.py           Kjøring fra cron/terminal
db/
  database.py      SQLAlchemy-oppsett
  models.py        Database-tabeller
models/
  schemas.py       Pydantic-modeller
articles/          Genererte HTML-artikler
data/raw/          Nedlastede dokumenter
data/processed/    Lokal state og SQLite fallback
render.yaml        Render web service + cron job
```

## Lokal kjøring

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Prosjektet er satt opp for Python 3.12 via `.python-version`.

Fyll inn minst:

```env
OPENAI_API_KEY=sk-...
SMTP_TO=din@epost.no
```

For første test kan du la `DRY_RUN_EMAIL=true`, slik at artikkelen ikke sendes.

Kjør én jobb fra terminal:

```bash
python -m app.cli --force
```

Kjør Osen:

```bash
python -m app.cli --municipality osen --force
```

Kjør Åfjord:

```bash
python -m app.cli --municipality afjord --force
```

Kjør Ørland:

```bash
python -m app.cli --municipality orland --force
```

Start webserveren:

```bash
uvicorn app.main:app --reload
```

Kjør roboten via API:

```bash
curl -X POST "http://127.0.0.1:8000/run/indre-fosen?force=true"
```

Du kan også kjøre fra nettleseren:

```text
http://127.0.0.1:8000/run/indre-fosen?force=true
```

Kjør Osen fra nettleseren:

```text
http://127.0.0.1:8000/run/osen?force=true
```

Kjør Åfjord fra nettleseren:

```text
http://127.0.0.1:8000/run/afjord?force=true
```

Kjør Ørland fra nettleseren:

```text
http://127.0.0.1:8000/run/orland?force=true
```

For å se hvilke dokumenter scraperen finner fra Indre Fosen-siden:

```text
http://127.0.0.1:8000/documents/indre-fosen
```

For Osen:

```text
http://127.0.0.1:8000/documents/osen
```

For Åfjord:

```text
http://127.0.0.1:8000/documents/afjord
```

For Ørland:

```text
http://127.0.0.1:8000/documents/orland
```

For å teste en eldre protokoll bruker du `protocol_index`. `0` er beste/siste treff, `1` er neste dokument i lista:

```text
http://127.0.0.1:8000/run/indre-fosen?force=true&protocol_index=1
```

For Osen:

```text
http://127.0.0.1:8000/run/osen?force=true&protocol_index=1
```

For Åfjord:

```text
http://127.0.0.1:8000/run/afjord?force=true&protocol_index=1
```

For Ørland:

```text
http://127.0.0.1:8000/run/orland?force=true&protocol_index=1
```

Fra terminal:

```bash
python -m app.cli --force --protocol-index 1
python -m app.cli --municipality osen --force --protocol-index 1
python -m app.cli --municipality afjord --force --protocol-index 1
python -m app.cli --municipality orland --force --protocol-index 1
```

Du kan teste parseren uten nett, OpenAI og e-post med en lokal eksempelprotokoll:

```text
http://127.0.0.1:8000/test/sample-protocol
```

Eller i terminal:

```bash
python -m app.sample_protocol
```

Åpne generert artikkel:

```text
http://127.0.0.1:8000/articles/navn-pa-artikkel.html
```

## E-post

SMTP styres med miljøvariabler:

```env
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=bruker
SMTP_PASSWORD=passord
SMTP_FROM=robotjournalist@example.com
SMTP_TO=redaksjon@example.com
SMTP_USE_TLS=true
DRY_RUN_EMAIL=false
```

## Database

Hvis `DATABASE_URL` ikke er satt, bruker appen lokal SQLite i `data/processed/`.

På Render kan du legge til PostgreSQL og sette:

```env
DATABASE_URL=postgresql://...
```

Duplikatkontroll gjøres på `source_url`, slik at samme protokoll ikke prosesseres flere ganger.

## Automatisering og dobbeltutsending

Cron-jobbene på Render er satt opp til å sjekke alle fire kommuner klokken 08.00, 12.00 og 15.00 norsk tid.

Render kjører cron-uttrykk i UTC. Derfor starter `render.yaml` jobbene på begge mulige UTC-tider for norsk sommer- og vintertid, og CLI-en slipper bare gjennom kjøringer der lokal tid i `Europe/Oslo` er 08, 12 eller 15.

Eksempel:

```bash
python -m app.cli --municipality indre-fosen --only-at-hours 8,12,15
```

Regelen for e-post er enkel:

- Hvis protokollen er ny, genereres artikkel og e-post forsøkes sendt.
- Hvis `source_url` allerede finnes i `processed_documents` eller lokal state, returnerer jobben `status: skipped` og sender ikke e-post.
- `--force` overstyrer sperren og kan sende samme sak på nytt. Bruk derfor ikke `--force` i cron.
- Hvis SMTP-sending feiler, stopper jobben før protokollen markeres som prosessert.
- Hvis `DRY_RUN_EMAIL=true`, tørrkjøres e-post. Dette er nyttig lokalt, men bør være `false` i produksjon.

## Deploy til Render

1. Legg repoet på GitHub.
2. Opprett en ny Blueprint på Render og pek den på repoet.
3. Render leser `render.yaml` og oppretter:
   - web service med FastAPI
   - cron job for Indre Fosen
   - cron job for Osen
   - cron job for Åfjord
   - cron job for Ørland
   - hver cron job sjekker klokken 08.00, 12.00 og 15.00 norsk tid
4. Sett hemmelige miljøvariabler i Render:
   - `OPENAI_API_KEY`
   - SMTP-verdier
   - eventuelt `DATABASE_URL`
5. Sett `DRY_RUN_EMAIL=false` når e-post skal sendes på ordentlig.

## Utvidelse til flere kommuner

Neste naturlige steg er å legge inn én scraper-funksjon per kommune:

Alle fire målkommuner i MVP-en er nå lagt inn. Neste naturlige steg er å forbedre nyhetsutvalg og språkregler per kommune.

Hold samme kontrakt som `fetch_indre_fosen_protocol()`, `fetch_osen_protocol()`, `fetch_afjord_protocol()` og `fetch_orland_protocol()`: funksjonen skal returnere et `MeetingDocument`. Da kan resten av pipeline gjenbrukes uten store endringer.
