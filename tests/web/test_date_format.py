from datetime import UTC, date, datetime

from bayios.web.templating import iso_date, tr_date, tr_date_long, tr_datetime


def test_turkish_short_and_long_dates_use_istanbul_time() -> None:
    moment = datetime(2026, 11, 10, 20, 30, tzinfo=UTC)

    assert tr_date(moment) == "10.11.2026"
    assert tr_date_long(moment) == "10 Kasım 2026"
    assert tr_datetime(moment) == "10.11.2026 23:30"
    assert iso_date(moment) == "2026-11-10"


def test_turkish_dates_handle_utc_midnight_shift() -> None:
    # 22:30 UTC is already the next day in Istanbul (UTC+3).
    moment = datetime(2026, 11, 9, 22, 30, tzinfo=UTC)

    assert tr_date(moment) == "10.11.2026"
    assert tr_date_long(moment) == "10 Kasım 2026"


def test_turkish_dates_accept_plain_dates_and_none() -> None:
    assert tr_date(date(2026, 2, 28)) == "28.02.2026"
    assert tr_date_long(date(2026, 2, 28)) == "28 Şubat 2026"
    assert tr_datetime(date(2026, 2, 28)) == "28.02.2026"
    assert tr_date(None) == ""
    assert tr_datetime(None) == ""
    assert iso_date(None) == ""


def test_all_turkish_months_are_named() -> None:
    names = [tr_date_long(datetime(2026, month, 1, tzinfo=UTC)) for month in range(1, 13)]

    assert names == [
        "1 Ocak 2026",
        "1 Şubat 2026",
        "1 Mart 2026",
        "1 Nisan 2026",
        "1 Mayıs 2026",
        "1 Haziran 2026",
        "1 Temmuz 2026",
        "1 Ağustos 2026",
        "1 Eylül 2026",
        "1 Ekim 2026",
        "1 Kasım 2026",
        "1 Aralık 2026",
    ]
