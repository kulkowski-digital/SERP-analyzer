---
name: serp-analyzer
description: Pełna analiza SERP dla dowolnej frazy. Pobiera wyniki Google przez Nodeshub API, crawluje TOP10 stron (Crawl4AI + PruningContentFilter) i generuje raport z intencją zapytania, elementami wspólnymi konkurencji i sugerowaną strukturą strony pod ranking. Użyj gdy user chce przeanalizować frazę kluczową, sprawdzić konkurencję w Google, zaplanować treść pod SEO albo zobaczyć co mają strony z TOP10.
---

# SERP Analyzer

Kompletna analiza pojedynczej frazy kluczowej: SERP → crawl TOP10 → raport SEO.

## Kiedy używać
Gdy użytkownik chce:
- przeanalizować frazę kluczową / „sprawdź SERP dla …",
- zobaczyć kto rankuje w TOP10 i co mają na stronach,
- poznać intencję zapytania i zaplanować strukturę strony pod ranking.

## Wymagania (jednorazowo)
1. Python 3.9+
2. Zależności: `pip install -r requirements.txt` (lub `python3 -m pip install crawl4ai requests beautifulsoup4 && crawl4ai-setup`)
3. Klucz Nodeshub w pliku `.env` (skopiuj `.env.example` → `.env`). Darmowe 100 tokenów na https://nodeshub.io

Sprawdź konfigurację: `python3 scripts/check_setup.py`

## Jak uruchomić
```bash
python3 scripts/serp_full_analysis.py "FRAZA" --gl pl --hl pl --device desktop
```
Parametry:
- `--gl` kraj (np. `pl`, `us`, `de`) — domyślnie `pl`
- `--hl` język interfejsu (np. `pl`, `en`) — domyślnie `pl`
- `--device` `desktop` lub `mobile` — domyślnie `desktop`
- `--top` ile stron z TOP crawlować (domyślnie 10)

## Workflow dla Claude Code
1. Zapytaj użytkownika o **frazę**, **rynek** (`gl`/`hl`) i **urządzenie**, jeśli nie podał — desktop i mobile dają różne SERP-y.
2. Uruchom skrypt przez Bash. Każde zapytanie SERP to 1 token Nodeshub.
3. Po zakończeniu przeczytaj `output/<slug-frazy>/analysis.md` i przedstaw użytkownikowi:
   - **Intencję zapytania** (informacyjna / komercyjna / lokalna / transakcyjna),
   - **Elementy wspólne** TOP10 (sekcje, średnia długość treści, najczęstsze terminy, PAA),
   - **Sugerowaną strukturę strony** (H1 + H2) pod ranking na tę frazę.
4. W razie potrzeby pogłęb analizę czytając pojedyncze pliki z `output/<slug>/pages/`.

## Co generuje skrypt
W `output/<slug-frazy>/`:
- `serp.json` — surowa odpowiedź Nodeshub (organic + snippety SERP)
- `pages/NN_domena.md` — czysty markdown (fit_markdown) każdej strony z TOP10
- `pages_meta.json` — title, meta description, nagłówki H1–H3, liczba słów
- `analysis.md` — raport końcowy (to czytaj jako podsumowanie)

## Odporność (wbudowane retry)
- **Nodeshub:** 3 próby z backoff (sieć / 429 / 5xx / pusta odpowiedź).
- **Crawl4AI:** strony, które padły lub zwróciły < 50 słów, są ponawiane z mocniejszą
  konfiguracją (dłuższy timeout, `networkidle`, scroll całej strony, obejście overlay).

## Koszt
1 token Nodeshub za każdą frazę (1 zapytanie SERP). Crawl stron jest darmowy (lokalny).
