import base64

from vanish.mbox import iter_header_blocks, iter_messages, parse_headers
from vanish.synthetic import build_messages


def test_counts_every_message(mbox_path):
    messages = list(iter_messages(mbox_path))
    assert len(messages) == len(build_messages())
    assert 50 <= len(messages) <= 100


def test_body_lines_are_not_separators_and_never_parsed(mbox_path):
    for block in iter_header_blocks(mbox_path):
        assert b"SECRET-BODY-MARKER" not in block
        assert b"From here on" not in block
        assert b"From: " in block


def test_crlf_gives_same_result(mbox_path, mbox_crlf_path):
    lf = [(m.from_addr, m.subject, m.date) for m in iter_messages(mbox_path)]
    crlf = [(m.from_addr, m.subject, m.date) for m in iter_messages(mbox_crlf_path)]
    assert lf == crlf


def test_encoded_subjects_are_decoded(mbox_path):
    subjects = {m.subject for m in iter_messages(mbox_path)}
    # base64, quoted-printable со свёрткой и «сырой» UTF-8 — все декодируются одинаково.
    assert "Добро пожаловать в Ozon!" in subjects
    assert "Подтвердите регистрацию на Хабре" in subjects
    assert "Как выучить английский за 3 месяца" in subjects
    assert not any("=?" in s for s in subjects)


def test_headers_parsed(mbox_path):
    msgs = list(iter_messages(mbox_path))
    ozon = next(m for m in msgs if m.subject == "Добро пожаловать в Ozon!")
    assert ozon.from_addr == "noreply@mail.ozon.ru"
    assert ozon.from_name == "OZON"
    assert ozon.domain == "mail.ozon.ru"
    assert ozon.date.year == 2017
    assert ozon.message_id.startswith("<synthetic-")
    assert "Входящие" in ozon.labels
    assert ozon.delivered_to == "me.vanish.demo@gmail.com"

    promo = next(m for m in msgs if m.subject == "Скидки недели: до −70% на технику")
    assert promo.list_unsubscribe is True
    assert ozon.list_unsubscribe is False

    habr = next(m for m in msgs if m.from_addr == "noreply@habr.com")
    assert habr.from_name == "Хабр"


def test_progress_reaches_end(mbox_path):
    calls = []
    list(iter_header_blocks(mbox_path, progress=lambda pos, size, n: calls.append((pos, size, n))))
    assert calls
    pos, size, n = calls[-1]
    assert pos == size
    assert n == len(build_messages())


def test_empty_file(tmp_path):
    empty = tmp_path / "empty.mbox"
    empty.write_bytes(b"")
    assert list(iter_messages(empty)) == []


def test_folded_and_broken_headers():
    block = (
        b"From: =?utf-8?B?0KLQtdGB0YI=?= <Test@Example.COM>\n"
        b"Subject: very long\n subject line\n"
        b"Date: not a date\n"
        b"garbage line without colon\n"
        b"List-Unsubscribe: <mailto:x@example.com>"
    )
    msg = parse_headers(block)
    assert msg.from_addr == "test@example.com"
    assert msg.from_name == "Тест"
    assert msg.subject == "very long subject line"
    assert msg.date is None
    assert msg.list_unsubscribe


def _takeout_message(n: int, nl: str) -> str:
    return nl.join([
        f"From 17000000000000000{n:02d}@xxx Mon Jan 01 12:00:00 +0000 2024",
        f"X-GM-THRID: 17000000000000000{n:02d}",
        "X-Gmail-Labels: Inbox",
        f"From: shop{n} <noreply@shop{n}.ru>",
        f"Subject: Письмо {n}",
        "",
        "From the team with love",
        "",
    ])


def test_mixed_line_endings_do_not_merge_messages(tmp_path):
    # В одном архиве встречаются письма и с CRLF, и с LF — ни одно не должно «приклеиться» к соседнему.
    path = tmp_path / "mixed.mbox"
    parts = [_takeout_message(n, "\r\n" if n % 3 else "\n") for n in range(9)]
    path.write_bytes("".join(parts).encode("utf-8"))
    msgs = list(iter_messages(path))
    assert [m.subject for m in msgs] == [f"Письмо {n}" for n in range(9)]
    assert [m.from_addr for m in msgs] == [f"noreply@shop{n}.ru" for n in range(9)]


def test_labels_encoded_as_one_word():
    block = "X-Gmail-Labels: =?UTF-8?B?{}?=\nFrom: a@b.ru".format(
        base64.b64encode("Входящие,Спам".encode()).decode()
    ).encode()
    assert parse_headers(block).labels == ["Входящие", "Спам"]


def test_implausible_dates_are_dropped():
    assert parse_headers(b"From: a@b.ru\nDate: Thu, 01 Jan 1970 00:00:00 +0000").date is None
    assert parse_headers(b"From: a@b.ru\nDate: Fri, 01 Jan 2100 00:00:00 +0000").date is None
    assert parse_headers(b"From: a@b.ru\nDate: Mon, 01 Jan 2024 00:00:00 +0000").date.year == 2024


def test_raw_cp1251_subject():
    msg = parse_headers("From: a@b.ru\nSubject: Ваш заказ".encode("cp1251"))
    assert msg.subject == "Ваш заказ"
