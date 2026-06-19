"""Testy dla common_h2_themes — data-driven struktura H2 z TOP10."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from serp_full_analysis import common_h2_themes  # noqa: E402


def _page(h2):
    return {"success": True, "h2": h2}


def test_surfaces_theme_shared_across_pages():
    # Arrange: identyczny token "odszkodowanie" w H2 na 2 z 3 stron
    pages = [
        _page(["Odszkodowanie za błąd medyczny"]),
        _page(["Odszkodowanie — ile wynosi?"]),
        _page(["Zupełnie inny nagłówek"]),
    ]
    # Act
    themes = common_h2_themes(pages, "błędy medyczne", min_pages=2)
    # Assert
    examples = [t["example"] for t in themes]
    assert any("Odszkodowanie" in e for e in examples)
    assert all(t["pages"] >= 2 for t in themes)


def test_inflected_forms_do_not_cluster():
    # Dokumentuje ograniczenie: brak stemmingu -> "odszkodowanie" != "odszkodowania",
    # więc różne odmiany na osobnych stronach nie tworzą wspólnego tematu.
    pages = [
        _page(["Odszkodowanie za błąd medyczny"]),
        _page(["Wysokość odszkodowania"]),
    ]
    themes = common_h2_themes(pages, "błędy medyczne", min_pages=2)
    assert themes == []


def test_excludes_query_tokens():
    # Arrange: H2 zbudowane tylko z tokenów frazy -> brak istotnych tematów
    pages = [
        _page(["Błędy medyczne"]),
        _page(["Błąd medyczny"]),
    ]
    # Act
    themes = common_h2_themes(pages, "błędy medyczne", min_pages=2)
    # Assert: same tokeny frazy nie tworzą tematu
    assert themes == []


def test_min_pages_threshold_filters_single_page_tokens():
    # Arrange: każdy temat tylko na 1 stronie
    pages = [
        _page(["Przedawnienie roszczeń"]),
        _page(["Zadośćuczynienie pieniężne"]),
    ]
    # Act
    themes = common_h2_themes(pages, "błędy medyczne", min_pages=2)
    # Assert
    assert themes == []


def test_empty_pages_return_empty():
    # Arrange / Act: strony bez H2
    themes = common_h2_themes([_page([]), _page([])], "błędy medyczne", min_pages=2)
    # Assert
    assert themes == []
