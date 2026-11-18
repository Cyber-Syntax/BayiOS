from __future__ import annotations

from bayios.domain.naming import canonical_display_name, normalize_name


def test_normalize_name_folds_turkish_case_and_spaces() -> None:
    assert normalize_name("  AKBANK ") == "akbank"
    assert normalize_name("Akbank") == "akbank"
    assert normalize_name("İŞ BANKASI") == "iş bankası"
    assert normalize_name("IŞIK") == "ışık"


def test_canonical_bank_name() -> None:
    assert canonical_display_name("AKBANK", always_title=True) == "Akbank"
    assert canonical_display_name("akbank", always_title=True) == "Akbank"
    assert canonical_display_name("AkbanK", always_title=True) == "Akbank"
    assert canonical_display_name("İŞ BANKASI", always_title=True) == "İş Bankası"
    assert canonical_display_name("QNB", always_title=True) == "QNB"


def test_canonical_category_name_preserves_mixed_case() -> None:
    assert canonical_display_name("ÇAMAŞIR MAKİNESİ") == "Çamaşır Makinesi"
    assert canonical_display_name("buzdolabı") == "Buzdolabı"
    assert canonical_display_name("TV") == "TV"
    assert canonical_display_name("Bulaşık Makinesi") == "Bulaşık Makinesi"
