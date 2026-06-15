# 🔍 SERP Analyzer — analiza konkurencji SEO dla Claude Code

Wpisujesz frazę → narzędzie pobiera wyniki Google, crawluje wszystkie strony z TOP10
i zwraca raport: **intencja zapytania**, **co mają wspólnego strony z TOP10** oraz
**gotową strukturę strony**, która ma szansę rankować na tę frazę.

Działa jako **skill Claude Code** (komenda w czacie) albo jako zwykły skrypt w terminalu.

---

## ⚡ Szybki start (3 minuty)

```bash
# 1. Pobierz / sklonuj ten folder i wejdź do niego
cd serp-analyzer

# 2. Zainstaluj zależności (raz)
pip install -r requirements.txt
crawl4ai-setup          # pobiera przeglądarkę dla Crawl4AI

# 3. Wklej swój klucz Nodeshub
cp .env.example .env
#   otwórz .env i wklej klucz z https://nodeshub.io (100 darmowych tokenów, bez karty)

# 4. Sprawdź, czy wszystko działa
python3 scripts/check_setup.py

# 5. Pierwsza analiza
python3 scripts/serp_full_analysis.py "pozycjonowanie warszawa" --gl pl --hl pl
```

Wynik ląduje w `output/pozycjonowanie-warszawa/` — najważniejszy plik to **`analysis.md`**.

---

## 🤖 Użycie w Claude Code (zalecane)

1. Skopiuj cały ten folder do swojego projektu (albo otwórz go jako projekt).
2. Uruchom `claude` w tym folderze.
3. Skill `serp-analyzer` zostanie wykryty automatycznie (leży w `.claude/skills/`).
4. Napisz po prostu:

   > Przeanalizuj SERP dla frazy „pozycjonowanie warszawa", rynek PL, desktop

   Claude pobierze dane, scrawluje TOP10 i przedstawi Ci podsumowanie.

---

## 🔑 Skąd wziąć klucz Nodeshub

1. Wejdź na **https://nodeshub.io**
2. Zjedź do sekcji **API Playground**
3. Kliknij **„Copy to clipboard"** przy polu API key
4. Wklej do pliku `.env` jako `NODESHUB_API_KEY=...`

100 darmowych tokenów na start — bez rejestracji, bez karty. 1 analiza frazy = 1 token.

---

## 📦 Co dostajesz w wyniku

Dla każdej frazy w `output/<slug-frazy>/`:

| Plik | Zawartość |
|------|-----------|
| `analysis.md` | **Raport końcowy** — intencja, elementy wspólne, sugerowana struktura |
| `serp.json` | Surowa odpowiedź Nodeshub (organic + snippety SERP) |
| `pages/NN_domena.md` | Czysty markdown każdej strony z TOP10 (Crawl4AI + PruningContentFilter) |
| `pages_meta.json` | Title, meta description, nagłówki H1–H3, liczba słów każdej strony |

---

## ⚙️ Parametry

```bash
python3 scripts/serp_full_analysis.py "FRAZA" [opcje]
```

| Opcja | Opis | Domyślnie |
|-------|------|-----------|
| `--gl` | Kraj (geolokalizacja Google): `pl`, `us`, `de`, `uk`… | `pl` |
| `--hl` | Język interfejsu: `pl`, `en`, `de`… | `pl` |
| `--device` | `desktop` lub `mobile` | `desktop` |
| `--top` | Ile stron z TOP crawlować | `10` |

---

## 🛡️ Odporność na błędy (wbudowane retry)

- **Nodeshub** — 3 próby z narastającym odstępem (błędy sieci, limit 429, błędy 5xx, pusta odpowiedź).
- **Crawl4AI** — strony, które padły lub zwróciły < 50 słów (np. blokada / treść z JS),
  są ponawiane z mocniejszą konfiguracją: dłuższy timeout, `networkidle`, scroll całej strony,
  obejście popupów/cookie.

---

## 🧩 Struktura folderu

```
serp-analyzer/
├── README.md
├── requirements.txt
├── .env.example              # skopiuj do .env i wklej klucz
├── .gitignore
├── .claude/
│   └── skills/
│       └── serp-analyzer/
│           └── SKILL.md       # definicja skilla dla Claude Code
├── scripts/
│   ├── serp_full_analysis.py  # główny skrypt
│   └── check_setup.py         # weryfikacja konfiguracji
└── output/                    # tu lądują wyniki (gitignored)
```

---

## ❓ FAQ

**Czy muszę używać Claude Code?** Nie — skrypty działają z każdego terminala. Claude Code dodaje
wygodną komendę i automatyczne podsumowanie.

**Ile to kosztuje?** 1 token Nodeshub za frazę (start: 100 darmowych). Crawlowanie stron jest lokalne i darmowe.

**Działa dla innych krajów/języków?** Tak — ustaw `--gl` i `--hl` pod swój rynek.

**Skąd biorą się dane?** SERP na żywo z Google (przez Nodeshub), treść stron pobierana lokalnie przez Crawl4AI.
