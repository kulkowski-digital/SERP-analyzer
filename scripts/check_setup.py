#!/usr/bin/env python3
"""Weryfikacja konfiguracji: zależności, przeglądarka Crawl4AI, klucz Nodeshub."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ok = True


def check(label, cond, hint=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {label}")
    if not cond:
        ok = False
        if hint:
            print(f"      → {hint}")


print("Sprawdzam konfigurację SERP Analyzer...\n")

# Python
check(f"Python {sys.version_info.major}.{sys.version_info.minor}",
      sys.version_info >= (3, 9), "Wymagany Python 3.9+")

# Zależności
for mod, hint in [("crawl4ai", "pip install crawl4ai && crawl4ai-setup"),
                  ("requests", "pip install requests"),
                  ("bs4", "pip install beautifulsoup4")]:
    try:
        __import__(mod)
        check(f"moduł {mod}", True)
    except ImportError:
        check(f"moduł {mod}", False, hint)

# Klucz Nodeshub
import os
key = os.environ.get("NODESHUB_API_KEY")
if not key:
    for cand in (REPO_ROOT / ".env", Path.cwd() / ".env"):
        if cand.exists():
            for line in cand.read_text().splitlines():
                if line.strip().startswith("NODESHUB_API_KEY="):
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if v and v != "wklej_tutaj_swoj_klucz":
                        key = v
check("klucz NODESHUB_API_KEY", bool(key),
      "Skopiuj .env.example -> .env i wklej klucz z https://nodeshub.io")

# Test połączenia + saldo
if key:
    try:
        import requests
        r = requests.get("https://api.nodeshub.io/v1/api-key/balance",
                         headers={"Authorization": f"Bearer {key}"}, timeout=30)
        if r.ok:
            b = r.json()
            check(f"połączenie z Nodeshub (saldo: {b.get('left')} / {b.get('limit')} tokenów)", True)
        else:
            check("połączenie z Nodeshub", False, f"HTTP {r.status_code} – sprawdź klucz")
    except Exception as e:
        check("połączenie z Nodeshub", False, str(e))

print()
print("✅ Wszystko gotowe! Uruchom: python3 scripts/serp_full_analysis.py \"twoja fraza\""
      if ok else "⚠ Uzupełnij braki powyżej i uruchom ponownie.")
sys.exit(0 if ok else 1)
