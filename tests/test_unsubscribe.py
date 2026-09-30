from datetime import datetime, timezone

import pytest

from vanish import api
from vanish.analyzer import analyze
from vanish.mbox import iter_messages, unsubscribe_https_url
from vanish.synthetic import _message


@pytest.mark.parametrize(
    "header, url",
    [
        ("<mailto:u@x.com>, <https://x.com/u?id=1>", "https://x.com/u?id=1"),
        ("<https://a.example.com/one>, <https://b.example.com/two>", "https://a.example.com/one"),
        ("<mailto:u@x.com>", ""),
        ("<http://x.com/u>", ""),                        # только https
        ("<https://x.com/u?a=1&b=2>", "https://x.com/u?a=1&b=2"),
        ("<mailto:u@x.com>,  <https://x.com/very/\n long>", "https://x.com/very/long"),  # свёрнутая ссылка
        ("https://x.com/no-brackets", "https://x.com/no-brackets"),
        ('<https://x.com/"><script>>', ""),
        ("<https://user@evil.com/u>", ""),              # логин в адресе — подозрительно
        ("<https://localhost/u>", ""),
        ("<javascript:alert(1)>", ""),
        ("", ""),
    ],
)
def test_unsubscribe_https_url(header, url):
    assert unsubscribe_https_url(header) == url


def by_domain(conn):
    return {s["domain"]: s for s in api.list_services(conn)}


def test_link_from_latest_message(analyzed, mbox_path):
    links = [
        (m.date, m.unsubscribe_url) for m in iter_messages(mbox_path)
        if m.domain == "mail.ozon.ru" and m.unsubscribe_url
    ]
    newest = max(links)[1]
    u = by_domain(analyzed)["ozon.ru"]["unsubscribe"]
    assert u["url"] == newest
    assert u["host"] == "mail.ozon.ru.invalid"
    assert u["warning"] is None
    assert u["date"] == max(links)[0].date().isoformat()


def test_no_button_for_spam_or_unconfirmed(analyzed):
    s = by_domain(analyzed)
    # Хабр: аккаунт точно есть, но письмо от него лежало в «Спаме».
    habr = s["habr.com"]["unsubscribe"]
    assert habr["warning"] == "spam" and habr["url"] is None and habr["spam"] == 1
    assert s["habr.com"]["count"] == 3  # письмо из «Спама» сервисом не считается
    # Только рассылка — аккаунт не подтверждён.
    sky = s["skyeng.ru"]["unsubscribe"]
    assert s["skyeng.ru"]["confidence"] == "newsletter"
    assert sky["warning"] == "unconfirmed" and sky["url"] is None and sky["host"] == "skyeng.ru.invalid"
    # «Вероятно» — тоже не подтверждён.
    booking = s["booking.com"]
    assert booking["confidence"] == "likely" and booking["unsubscribe"]["warning"] == "unconfirmed"


def test_mailto_only_and_no_header(analyzed):
    s = by_domain(analyzed)
    ph = s["producthunt.com"]
    assert ph["has_unsub"] and ph["unsubscribe"]["url"] is None and ph["unsubscribe"]["warning"] is None
    gh = s["github.com"]["unsubscribe"]
    assert gh == {"url": None, "host": None, "date": None, "warning": None, "spam": 0}


def _write(path, messages):
    path.write_bytes("\n".join(messages).encode("utf-8"))


def test_reimport_keeps_newest_link(analyzed, tmp_path):
    old = datetime(2010, 1, 1, tzinfo=timezone.utc)
    new = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sender = "noreply@mail.ozon.ru"
    older = _message(None, 9001, sender, "OZON", "Старая акция", old, True, "Входящие")
    newer = _message(None, 9002, sender, "OZON", "Новая акция", new, True, "Входящие")

    _write(tmp_path / "new.mbox", [newer])
    analyze(analyzed, tmp_path / "new.mbox")
    assert by_domain(analyzed)["ozon.ru"]["unsubscribe"]["url"].endswith("synthetic-9002")

    # Архив со старыми письмами не затирает более свежую ссылку.
    _write(tmp_path / "old.mbox", [older])
    analyze(analyzed, tmp_path / "old.mbox")
    assert by_domain(analyzed)["ozon.ru"]["unsubscribe"]["url"].endswith("synthetic-9002")


def test_links_are_not_exported(analyzed):
    assert "unsubscribe?u=" not in api.export_csv(analyzed)
    assert "unsubscribe?u=" not in str(api.export_progress(analyzed))
