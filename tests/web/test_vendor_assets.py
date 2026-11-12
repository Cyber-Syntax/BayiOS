from __future__ import annotations

from hashlib import sha256

from bayios.web.templating import STATIC_DIR

VENDOR_DIR = STATIC_DIR / "vendor"
FLATPICKR_DIR = VENDOR_DIR / "flatpickr"
FLATPICKR_ASSETS = (
    "flatpickr/flatpickr.min.js",
    "flatpickr/flatpickr.min.css",
    "flatpickr/l10n/tr.js",
)


def test_flatpickr_is_vendored_locally_with_matching_hashes() -> None:
    versions = (VENDOR_DIR / "VERSIONS.txt").read_text(encoding="utf-8")

    assert "flatpickr 4.6.13" in versions
    for relative_path in FLATPICKR_ASSETS:
        asset = VENDOR_DIR / relative_path
        assert asset.is_file(), f"missing vendor asset: {relative_path}"
        assert asset.stat().st_size > 0
        digest = sha256(asset.read_bytes()).hexdigest()
        assert f"{digest}  {relative_path}" in versions


def test_flatpickr_license_is_kept_next_to_assets() -> None:
    license_text = (FLATPICKR_DIR / "LICENSE.md").read_text(encoding="utf-8")

    assert "MIT License" in license_text


def test_turkish_locale_ships_with_the_vendor_bundle() -> None:
    locale_text = (FLATPICKR_DIR / "l10n" / "tr.js").read_text(encoding="utf-8")

    assert "Ocak" in locale_text
    assert "Kasım" in locale_text
    assert 'firstDayOfWeek: 1' in locale_text


def test_print_stylesheet_hides_the_picker() -> None:
    print_css = (STATIC_DIR / "css" / "print.css").read_text(encoding="utf-8")

    assert ".flatpickr-calendar" in print_css
    assert ".flatpickr-tr-actions" in print_css


def test_picker_copies_ghost_text_to_the_visible_input() -> None:
    script = (STATIC_DIR / "js" / "date-picker.js").read_text(encoding="utf-8")

    assert "input.getAttribute(\"placeholder\")" in script
    assert "altInput.placeholder = placeholder" in script


def test_sticky_table_scroll_asset_is_present_and_used_by_import_preview() -> None:
    from bayios.web.templating import TEMPLATES_DIR

    script = (STATIC_DIR / "js" / "table-scroll.js").read_text(encoding="utf-8")
    assert "data-table-scroll" in script
    assert "table-scroll-bar" in script
    template = (TEMPLATES_DIR / "imports" / "preview.html").read_text(
        encoding="utf-8"
    )
    assert "data-table-scroll" in template
