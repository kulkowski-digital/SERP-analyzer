#!/usr/bin/env python3
"""
SERP Full Analysis
==================
Pełna analiza frazy: SERP z Nodeshub -> crawl TOP10 (Crawl4AI + PruningContentFilter)
-> agregacja danych -> raport (intencja, elementy wspólne, sugerowana struktura strony).

Użycie:
    python3 serp_full_analysis.py "pozycjonowanie warszawa" --gl pl --hl pl --device desktop
    python3 serp_full_analysis.py "best seo tools" --gl us --hl en --top 10

Wyniki zapisywane do: output/<slug-zapytania>/
    serp.json          - surowa odpowiedź Nodeshub
    pages/NN_domena.md  - fit_markdown każdej strony z TOP10
    pages_meta.json    - metadane (title, description, nagłówki, liczba słów) każdej strony
    analysis.md        - raport końcowy
"""

import os
import re
import sys
import time
import json
import asyncio
import argparse
from pathlib import Path
from collections import Counter
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

NODESHUB_SEARCH = "https://api.nodeshub.io/v1/search"

# Polskie + angielskie stopwords do analizy częstości słów
STOPWORDS = set("""
a aby albo ale ani aż bardzo bez bo bowiem by byli bylo było bym byc był była były
będzie będą cała cały ci cie ciebie co coraz czy czyli dla do gdy gdyby gdyż gdzie
go i ich ile im inne inny iż ja jak jako je jego jej jest jestem jeszcze jeśli jeżeli
już ją każdy kiedy kilka kto która które którego której który których którym którzy ma
mają mamy mi mnie mogą może można my na nad nam nami nas nasz nasze nawet nią nic nich
nie niej nim niż no nowy o od on ona one oni ono oraz pan po pod podczas pomiędzy ponad
ponieważ poza przed przede przez przy raz roku również są się sa skąd sobie sposob są ta
tak taka taki takie tam te tego tej temu ten teraz też to tobie tu tutaj twoje twój twoja
ty tych tylko tym tys u w we wam was wasz we większość wiele więc wszyscy wszystkie wszystko
www właśnie z za zawsze ze że żeby aż https http com pl
the and for are with you your this that from have has was were will can our its their
""".split())

# elementy/tematy często spotykane na stronach usługowych SEO – do mapowania struktury
SECTION_HINTS = {
    "cennik / wycena": ["cennik", "cena", "koszt", "wycena", "ile kosztuje", "pricing", "price"],
    "proces / jak działamy": ["proces", "jak działa", "krok", "etap", "współpraca", "audyt"],
    "oferta / usługi": ["oferta", "usługi", "zakres", "co obejmuje", "services"],
    "opinie / referencje": ["opinie", "referencje", "klienci", "case study", "zaufali", "recenzje", "testimonial"],
    "FAQ / pytania": ["faq", "pytania", "najczęściej zadawane", "pytań"],
    "efekty / wyniki": ["efekty", "wyniki", "wzrost", "rezultaty", "results"],
    "kontakt / CTA": ["kontakt", "skontaktuj", "zadzwoń", "formularz", "darmowa", "bezpłatna", "konsultacja"],
    "blog / poradniki": ["blog", "poradnik", "artykuł", "wiedza"],
    "lokalność (geo)": ["warszawa", "lokaln", "okolic", "miasto", "dzielnic"],
}


def slugify(text: str) -> str:
    text = text.lower().strip()
    repl = {"ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s", "ż": "z", "ź": "z"}
    for a, b in repl.items():
        text = text.replace(a, b)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


REPO_ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> root paczki


def _read_env_file(path: Path):
    vals = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def load_api_key() -> str:
    # 1) zmienna środowiskowa
    key = os.environ.get("NODESHUB_API_KEY")
    if key:
        return key.strip()
    # 2) .env w typowych lokalizacjach: root paczki, cwd, katalog wyżej
    for cand in (REPO_ROOT / ".env", Path.cwd() / ".env", REPO_ROOT.parent / ".env"):
        v = _read_env_file(cand).get("NODESHUB_API_KEY")
        if v:
            return v
    sys.exit(
        "BŁĄD: brak NODESHUB_API_KEY.\n"
        "  Ustaw go w pliku .env (skopiuj .env.example -> .env) lub:\n"
        "  export NODESHUB_API_KEY=twoj_klucz\n"
        "  Klucz pobierzesz za darmo na https://nodeshub.io (100 darmowych tokenów)."
    )


def fetch_serp(keyword: str, gl: str, hl: str, device: str, retries: int = 3) -> dict:
    """Pobiera SERP z Nodeshub z retry (exponential backoff) na błędy sieci/5xx/429."""
    key = load_api_key()
    print(f"[1/4] Pobieram SERP z Nodeshub: '{keyword}' (gl={gl}, hl={hl}, {device})...")
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                NODESHUB_SEARCH,
                headers={"Authorization": f"Bearer {key}"},
                params={"keyword": keyword, "gl": gl, "hl": hl, "device": device},
                timeout=60,
            )
            # 4xx (poza 429) nie ma sensu ponawiać
            if resp.status_code in (400, 401, 403):
                resp.raise_for_status()
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            organic = data.get("data", {}).get("results", {}).get("organic_results", [])
            if not organic:
                raise ValueError("pusta lista organic_results")
            return data
        except (requests.RequestException, ValueError) as e:
            last_err = e
            if attempt < retries:
                wait = 2 ** attempt
                print(f"   ⚠ Nodeshub próba {attempt}/{retries} nieudana ({e}). Ponawiam za {wait}s...")
                time.sleep(wait)
            else:
                print(f"   ✗ Nodeshub: wyczerpano {retries} prób.")
    sys.exit(f"BŁĄD Nodeshub: {last_err}")


def extract_headings(html: str):
    """Wyciąga nagłówki H1-H3, title i meta description z HTML."""
    soup = BeautifulSoup(html or "", "html.parser")
    title = (soup.title.string.strip() if soup.title and soup.title.string else "")
    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = desc_tag.get("content", "").strip() if desc_tag else ""
    headings = []
    for level in ("h1", "h2", "h3"):
        for tag in soup.find_all(level):
            txt = tag.get_text(" ", strip=True)
            if txt:
                headings.append({"level": level, "text": txt})
    return title, description, headings


# Treść poniżej tego progu uznajemy za nieudany crawl (np. zablokowane / JS)
MIN_WORDS = 50


def _result_to_entry(o: dict, r, pages_dir: Path):
    """Konwertuje wynik Crawl4AI na wpis meta + zapisuje markdown. Zwraca (entry, ok)."""
    pos, url, domain = o["pos"], o["url"], o["domain"]
    entry = {"pos": pos, "domain": domain, "url": url,
             "serp_title": o.get("title", ""), "serp_description": o.get("description", "")}
    if r and r.success:
        try:
            fit = r.markdown.fit_markdown or r.markdown.raw_markdown
        except Exception:
            fit = r.markdown if isinstance(r.markdown, str) else ""
        title, description, headings = extract_headings(r.html)
        word_count = len((fit or "").split())
        if word_count >= MIN_WORDS:
            fname = f"{pos:02d}_{slugify(domain)}.md"
            (pages_dir / fname).write_text(
                f"# {domain} (pozycja {pos})\nURL: {url}\nTitle: {title}\n\n{fit}",
                encoding="utf-8",
            )
            entry.update({
                "success": True, "file": f"pages/{fname}",
                "page_title": title, "meta_description": description,
                "word_count": word_count,
                "h1": [h["text"] for h in headings if h["level"] == "h1"],
                "h2": [h["text"] for h in headings if h["level"] == "h2"],
                "h3": [h["text"] for h in headings if h["level"] == "h3"],
                "fit_markdown": fit,
            })
            return entry, True
        entry.update({"success": False, "error": f"za mało treści ({word_count} słów)"})
        return entry, False
    entry.update({"success": False, "error": (r.error_message if r else "brak wyniku")})
    return entry, False


async def crawl_pages(organic: list, out_dir: Path, crawl_retries: int = 2):
    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    md_gen = DefaultMarkdownGenerator(
        content_filter=PruningContentFilter(threshold=0.4, threshold_type="fixed")
    )
    # Konfiguracja szybka (1. próba) – batch
    fast_config = CrawlerRunConfig(
        markdown_generator=md_gen,
        cache_mode=CacheMode.BYPASS,
        page_timeout=45000,
        excluded_tags=["nav", "footer", "aside", "form"],
        remove_overlay_elements=True,
    )
    # Konfiguracja "mocna" (retry) – dłuższy timeout, pełne ładowanie JS + scroll
    robust_config = CrawlerRunConfig(
        markdown_generator=md_gen,
        cache_mode=CacheMode.BYPASS,
        page_timeout=90000,
        wait_until="networkidle",
        scan_full_page=True,
        delay_before_return_html=2.0,
        remove_overlay_elements=True,
        magic=True,
    )

    urls = [o["url"] for o in organic]
    by_pos = {o["pos"]: o for o in organic}
    print(f"[2/4] Crawluję {len(urls)} stron z TOP10 (PruningContentFilter)...")

    entries = {}
    async with AsyncWebCrawler() as crawler:
        # Próba 1 – batch
        results = await crawler.arun_many(urls=urls, config=fast_config)
        by_url = {r.url: r for r in results}
        for o in organic:
            entry, ok = _result_to_entry(o, by_url.get(o["url"]), pages_dir)
            entries[o["pos"]] = entry
            mark = "✓" if ok else "✗"
            info = f"({entry['word_count']} słów, {len(entry.get('h2', []))} H2)" if ok else f"BŁĄD: {entry['error']}"
            print(f"   {mark} {o['pos']:>2}. {o['domain']}  {info}")

        # Próby 2..N – pojedynczo, mocna konfiguracja, tylko dla nieudanych
        for attempt in range(1, crawl_retries):
            failed = [pos for pos, e in entries.items() if not e.get("success")]
            if not failed:
                break
            print(f"   ↻ Retry Crawl4AI (próba {attempt + 1}) dla {len(failed)} stron: {failed}")
            for pos in failed:
                o = by_pos[pos]
                try:
                    r = await crawler.arun(url=o["url"], config=robust_config)
                except Exception as e:
                    r = None
                    print(f"      ⚠ {pos}. {o['domain']} wyjątek: {e}")
                entry, ok = _result_to_entry(o, r, pages_dir)
                entries[pos] = entry
                mark = "✓" if ok else "✗"
                info = f"({entry['word_count']} słów)" if ok else f"nadal błąd: {entry['error']}"
                print(f"      {mark} {pos}. {o['domain']}  {info}")

    return [entries[o["pos"]] for o in organic]


def common_h2_themes(ok_pages: list, keyword: str, min_pages: int) -> list:
    """Wyciąga powtarzalne tematy H2 z faktycznie sklawlowanych stron TOP10.

    Zamiast zahardkodowanego szablonu zwraca tematy, które realnie powtarzają się
    w nagłówkach H2 konkurencji (na ile odrębnych stron token się pojawia), wraz
    z reprezentatywnym przykładem nagłówka. Tokeny samej frazy są pomijane.
    """
    query_tokens = set(re.findall(r"[a-ząćęłńóśżź0-9]{3,}", keyword.lower()))
    token_pages = {}      # token -> set indeksów stron z tym tokenem w H2
    token_examples = {}   # token -> Counter przykładowych nagłówków
    for i, p in enumerate(ok_pages):
        for h in p.get("h2", []):
            tokens = [t for t in re.findall(r"[a-ząćęłńóśżź0-9]{4,}", h.lower())
                      if t not in STOPWORDS and t not in query_tokens]
            for t in tokens:
                token_pages.setdefault(t, set()).add(i)
                token_examples.setdefault(t, Counter())[h.strip()] += 1

    themes = []
    used_headings = set()
    for tok, pages in sorted(token_pages.items(), key=lambda x: (-len(x[1]), x[0])):
        if len(pages) < min_pages:
            continue
        example = next((h for h, _ in token_examples[tok].most_common()
                        if h not in used_headings), None)
        if not example:
            continue
        used_headings.add(example)
        themes.append({"pages": len(pages), "example": example})
    return themes[:12]


def analyze(serp: dict, pages_meta: list, keyword: str) -> dict:
    results = serp.get("data", {}).get("results", {})
    snippets_found = results.get("snippets_found", []) or []
    snippets = results.get("snippets", {}) or {}

    ok_pages = [p for p in pages_meta if p.get("success")]
    word_counts = [p["word_count"] for p in ok_pages if p.get("word_count")]
    avg_words = round(sum(word_counts) / len(word_counts)) if word_counts else 0

    # częstość słów w treści (fit_markdown) wszystkich stron
    term_counter = Counter()
    for p in ok_pages:
        words = re.findall(r"[a-ząćęłńóśżź0-9]{4,}", (p.get("fit_markdown") or "").lower())
        for w in words:
            if w not in STOPWORDS:
                term_counter[w] += 1
    top_terms = [(w, c) for w, c in term_counter.most_common(40)]

    # częstość tematów nagłówków H2/H3 -> mapowanie na sekcje
    all_headings = []
    for p in ok_pages:
        all_headings += [h.lower() for h in p.get("h2", []) + p.get("h3", [])]
    section_presence = {}
    for section, hints in SECTION_HINTS.items():
        count = sum(1 for h in all_headings if any(hint in h for hint in hints))
        # liczymy na ilu stronach temat się pojawia (po treści + nagłówkach)
        pages_with = 0
        for p in ok_pages:
            blob = " ".join(p.get("h1", []) + p.get("h2", []) + p.get("h3", [])).lower() + " " + (p.get("fit_markdown") or "").lower()[:4000]
            if any(hint in blob for hint in hints):
                pages_with += 1
        section_presence[section] = pages_with
    section_presence = dict(sorted(section_presence.items(), key=lambda x: -x[1]))

    # heurystyka intencji
    has_local = "local_pack" in snippets_found
    has_ai = "ai_overview" in snippets_found
    has_shop = any(s in snippets_found for s in ("popular_products", "ads"))
    intent = "informacyjna"
    if has_shop:
        intent = "komercyjna/transakcyjna"
    elif has_local:
        intent = "komercyjna lokalna"
    else:
        # po treści TOP10: jeśli dużo "usługi/oferta/kontakt" -> komercyjna
        commercial_signals = section_presence.get("oferta / usługi", 0) + section_presence.get("kontakt / CTA", 0)
        intent = "komercyjna" if commercial_signals >= len(ok_pages) else "informacyjna/mieszana"

    h2_themes = common_h2_themes(ok_pages, keyword, min_pages=max(2, len(ok_pages) // 3))

    return {
        "intent": intent,
        "h2_themes": h2_themes,
        "has_local_pack": has_local,
        "has_ai_overview": has_ai,
        "snippets_found": snippets_found,
        "related_searches": (snippets.get("related_searches", {}) or {}).get("queries", []),
        "paa": [q.get("text") for q in (snippets.get("people_also_ask", {}) or {}).get("questions", [])],
        "avg_words": avg_words,
        "word_counts": word_counts,
        "top_terms": top_terms,
        "section_presence": section_presence,
        "n_pages": len(ok_pages),
    }


def build_report(keyword, gl, hl, device, serp, pages_meta, a) -> str:
    n = a["n_pages"]
    lines = []
    L = lines.append
    L(f"# Analiza SERP: „{keyword}\"\n")
    L(f"**Rynek:** gl={gl}, hl={hl}, urządzenie={device}  ")
    L(f"**Stron sklawlowanych:** {n}/10  ")
    L(f"**Elementy SERP:** {', '.join(a['snippets_found']) or 'brak'}\n")

    L("## 1. Intencja zapytania\n")
    L(f"**Wykryta intencja: {a['intent'].upper()}**\n")
    sig = []
    if a["has_local_pack"]:
        sig.append("- Obecny **Local Pack** (mapka + firmy lokalne) → Google traktuje frazę lokalnie; kluczowe są Google Business Profile, opinie i NAP.")
    if a["has_ai_overview"]:
        sig.append("- Obecny **AI Overview** → fraza częściowo informacyjna, warto pisać treści cytowalne (chunki, E-E-A-T).")
    if not a["has_local_pack"] and not a["has_ai_overview"]:
        sig.append("- Brak Local Pack i AI Overview → klasyczny ranking organiczny.")
    commercial = a["section_presence"].get("oferta / usługi", 0) + a["section_presence"].get("kontakt / CTA", 0)
    if commercial >= n:
        sig.append("- W treści TOP10 dominują sekcje ofertowo-kontaktowe → silny komponent komercyjny.")
    else:
        sig.append("- W treści TOP10 przeważają sekcje merytoryczno-poradnikowe → komponent informacyjny przy ewentualnym CTA.")
    L("\n".join(sig) + "\n")

    L("## 2. Najważniejsze elementy wspólne (co mają strony z TOP10)\n")
    L(f"- **Średnia długość treści:** ~{a['avg_words']} słów "
      f"(zakres {min(a['word_counts']) if a['word_counts'] else 0}–{max(a['word_counts']) if a['word_counts'] else 0}).")
    L("- **Sekcje obecne na stronach** (na ilu z {0}):".format(n))
    for sec, cnt in a["section_presence"].items():
        bar = "█" * cnt + "░" * (n - cnt)
        L(f"   - `{bar}` {cnt}/{n} — {sec}")
    L("")
    L("- **Najczęstsze słowa/frazy w treści** (top 25):")
    terms = ", ".join(f"{w} ({c})" for w, c in a["top_terms"][:25])
    L(f"   {terms}\n")

    if a["related_searches"]:
        L("- **Powiązane wyszukiwania:** " + ", ".join(a["related_searches"]))
    if a["paa"]:
        L("- **People Also Ask:**")
        for q in a["paa"]:
            L(f"   - {q}")
    L("")

    L("## 3. Wyniki TOP10\n")
    L("| # | Domena | Słów | H2 | Title |")
    L("|---|--------|------|----|-------|")
    for p in pages_meta:
        if p.get("success"):
            L(f"| {p['pos']} | {p['domain']} | {p['word_count']} | {len(p.get('h2', []))} | {p.get('page_title','')[:60]} |")
        else:
            L(f"| {p['pos']} | {p['domain']} | — | — | ❌ {p.get('error','')[:40]} |")
    L("")

    L("## 4. Sugerowana struktura strony pod tę frazę\n")
    h1 = keyword[0].upper() + keyword[1:]
    L(f"**H1:** {h1}\n")
    themes = a.get("h2_themes", [])
    if themes:
        L("Tematy H2 powtarzające się w nagłówkach TOP10 (kolejność wg pokrycia):\n")
        for idx, t in enumerate(themes, start=1):
            L(f"{idx}. **H2: {t['example']}** _(na {t['pages']}/{n} stronach TOP10)_")
    else:
        L("_Zbyt mało nagłówków H2 w sklawlowanych stronach, by wskazać powtarzalne tematy — "
          "oprzyj strukturę na liście najczęstszych terminów i PAA powyżej._")
    L("")
    if a["paa"]:
        L(f"- **H2: FAQ** — odpowiedz wprost na {len(a['paa'])} pytań z People Also Ask (Schema `FAQPage`, szansa na featured snippet).")
    wc = sorted(a["word_counts"])
    median = wc[len(wc) // 2] if wc else 0
    L(f"\n**Cel objętości:** mediana TOP10 ~{median} słów (średnia ~{a['avg_words']}; "
      f"zakres {min(wc) if wc else 0}–{max(wc) if wc else 0} — kieruj się medianą, średnią zawyżają outliery).  ")
    L("**On-page:** fraza w title, H1, URL, pierwszym akapicie; nasycenie pokrewnymi terminami (lista wyżej).  ")
    if a["has_local_pack"]:
        L("**Local SEO:** zoptymalizuj Google Business Profile, zbieraj opinie, dodaj Schema LocalBusiness + dane NAP.")
    L("")
    return "\n".join(lines)


async def main():
    ap = argparse.ArgumentParser(description="Pełna analiza SERP + crawl TOP10")
    ap.add_argument("keyword", help="fraza do analizy")
    ap.add_argument("--gl", default="pl")
    ap.add_argument("--hl", default="pl")
    ap.add_argument("--device", default="desktop", choices=["desktop", "mobile"])
    ap.add_argument("--top", type=int, default=10, help="ile stron z TOP crawlować")
    args = ap.parse_args()

    out_dir = REPO_ROOT / "output" / slugify(args.keyword)
    out_dir.mkdir(parents=True, exist_ok=True)

    serp = fetch_serp(args.keyword, args.gl, args.hl, args.device)
    (out_dir / "serp.json").write_text(json.dumps(serp, ensure_ascii=False, indent=2), encoding="utf-8")

    organic = serp.get("data", {}).get("results", {}).get("organic_results", [])[: args.top]
    if not organic:
        sys.exit("BŁĄD: brak wyników organicznych w odpowiedzi Nodeshub.")

    pages_meta = await crawl_pages(organic, out_dir)
    (out_dir / "pages_meta.json").write_text(
        json.dumps([{k: v for k, v in p.items() if k != "fit_markdown"} for p in pages_meta],
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print("[3/4] Analizuję dane...")
    a = analyze(serp, pages_meta, args.keyword)

    print("[4/4] Generuję raport...")
    report = build_report(args.keyword, args.gl, args.hl, args.device, serp, pages_meta, a)
    (out_dir / "analysis.md").write_text(report, encoding="utf-8")

    print("\n" + "=" * 70)
    print(report)
    print("=" * 70)
    print(f"\n✅ Wyniki zapisane w: {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
