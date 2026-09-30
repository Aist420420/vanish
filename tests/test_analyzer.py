import json

from vanish import api
from vanish.analyzer import analyze
from vanish.synthetic import write_mbox


def stats(conn):
    return {r["domain"]: dict(r) for r in conn.execute("SELECT * FROM domain_stats")}


def test_groups_by_root_domain(analyzed):
    s = stats(analyzed)
    assert "ozon.ru" in s and "mail.ozon.ru" not in s
    assert "bbc.co.uk" in s
    assert "rozetka.com.ua" in s
    assert "yandex.ru" in s  # noreply@id.yandex.ru
    assert s["ozon.ru"]["count"] == 11
    assert s["skyeng.ru"]["count"] == 15


def test_aliases_and_esp(analyzed):
    s = stats(analyzed)
    assert "facebook.com" in s and "facebookmail.com" not in s
    assert "aliexpress.com" in s and "aliexpress.ru" not in s
    assert "sendgrid.net" not in s


def test_noise_filtered(analyzed):
    s = stats(analyzed)
    for noise in ("gmail.com", "mail.ru", "yandex.ru-personal", "casino-bonus.xyz"):
        assert noise not in s
    # yandex.ru есть только как сервис (id.yandex.ru), а письмо olga@yandex.ru — личное.
    assert s["yandex.ru"]["count"] == 2
    # Коллега, которому я отвечал, — переписка, а не сервис.
    assert s["acme-corp.com"]["confidence"] == "personal"
    assert s["acme-corp.com"]["sent_to"] == 1
    mine = {r["address"] for r in analyzed.execute("SELECT address FROM my_addresses")}
    assert "me.vanish.demo@gmail.com" in mine


def test_confidence_levels(analyzed):
    s = stats(analyzed)
    for dom in ("ozon.ru", "github.com", "netflix.com", "habr.com", "wildberries.ru", "steampowered.com",
                "google.com", "2gis.ru", "some-very-old-forum.net"):
        assert s[dom]["confidence"] == "sure", dom
    for dom in ("dns-shop.ru", "booking.com", "aliexpress.com"):
        assert s[dom]["confidence"] == "likely", dom
    for dom in ("skyeng.ru", "duolingo.com", "vc.ru", "producthunt.com"):
        assert s[dom]["confidence"] == "newsletter", dom


def test_dates_and_unsubscribe(analyzed):
    s = stats(analyzed)
    ozon = s["ozon.ru"]
    assert ozon["unsub"] > 0
    assert s["github.com"]["unsub"] == 0
    assert ozon["first_ts"] < ozon["last_ts"]
    service = api.get_service(analyzed, "ozon.ru")
    assert service["first_year"] == 2017
    assert service["has_unsub"] is True


def test_samples_limited_and_prioritized(analyzed):
    for row in analyzed.execute("SELECT samples FROM domain_info"):
        assert len(json.loads(row["samples"])) <= 5
    ozon = api.get_service(analyzed, "ozon.ru")
    assert ozon["samples"][0] == "Добро пожаловать в Ozon!"  # сильный сигнал первым
    assert len(set(ozon["samples"])) == len(ozon["samples"])


def test_body_never_stored(analyzed, tmp_path):
    analyzed.commit()
    dump = "\n".join(analyzed.iterdump())
    assert "SECRET-BODY-MARKER" not in dump
    assert "тело письма" not in dump


def test_jdm_match_and_links(analyzed):
    gh = api.get_service(analyzed, "github.com")
    assert gh["jdm"] is not None
    assert gh["name"] == "GitHub"
    assert gh["difficulty"] in ("easy", "medium", "hard", "limited", "impossible")
    assert gh["links"]["delete"].startswith("http")
    assert gh["links"]["gmail"] == "https://mail.google.com/mail/u/0/#search/from%3Agithub.com"
    unknown = api.get_service(analyzed, "some-very-old-forum.net")
    assert unknown["jdm"] is None
    assert unknown["links"]["delete"] is None
    assert "google.com/search" in unknown["links"]["search_delete"]


def test_google_linked(analyzed):
    assert api.get_service(analyzed, "notion.so")["google_linked"] is True
    assert api.get_service(analyzed, "figma.com")["google_linked"] is True
    assert api.get_service(analyzed, "ozon.ru")["google_linked"] is False


def test_reimport_is_idempotent_and_keeps_decisions(analyzed, mbox_path):
    before = stats(analyzed)
    api.decide(analyzed, "ozon.ru", "delete")
    api.update(analyzed, "ozon.ru", {"status": "deleted", "note": "удалил через поддержку"})
    api.add_service(analyzed, "forgotten.example.com", "Забытый сервис")

    report = analyze(analyzed, mbox_path)
    assert report.new_messages == 0
    assert stats(analyzed) == before
    ozon = api.get_service(analyzed, "ozon.ru")
    assert ozon["decision"] == "delete"
    assert ozon["status"] == "deleted"
    assert ozon["note"] == "удалил через поддержку"
    assert api.get_service(analyzed, "forgotten.example.com")["manual"] is True


def test_merge_new_archive(analyzed, tmp_path):
    api.decide(analyzed, "github.com", "keep")
    other = tmp_path / "other.mbox"
    write_mbox(other, crlf=True)  # тот же архив в другом формате → одни дубликаты
    newer = tmp_path / "newer.mbox"
    newer.write_bytes(
        b"From 1@xxx Mon Jan 06 10:00:00 +0000 2025\n"
        b"From: GitHub <noreply@github.com>\n"
        b"Subject: [GitHub] Sudo email verification code\n"
        b"Date: Mon, 06 Jan 2025 10:00:00 +0000\n"
        b"Message-ID: <brand-new@github.com>\n\nbody\n\n"
        b"From 2@xxx Mon Jan 06 11:00:00 +0000 2025\n"
        b"From: New Service <hello@newservice.io>\n"
        b"Subject: Welcome to New Service\n"
        b"Date: Mon, 06 Jan 2025 11:00:00 +0000\n"
        b"Message-ID: <x@newservice.io>\n\nbody\n"
    )
    assert analyze(analyzed, other).new_messages == 0
    report = analyze(analyzed, newer)
    assert report.new_messages == 2
    s = stats(analyzed)
    assert s["github.com"]["count"] == 4
    assert "newservice.io" in s
    gh = api.get_service(analyzed, "github.com")
    assert gh["decision"] == "keep"
    assert gh["last"] == "2025-01-06"


def test_bounces_and_drafts_are_not_services(conn, tmp_path):
    path = tmp_path / "bounce.mbox"
    path.write_bytes(
        b"From 1@xxx Mon Jan 06 10:00:00 +0000 2025\n"
        b"X-Gmail-Labels: Inbox\n"
        b"From: Mail Delivery Subsystem <mailer-daemon@googlemail.com>\n"
        b"Subject: Delivery Status Notification (Failure)\n"
        b"Date: Mon, 06 Jan 2025 10:00:00 +0000\n\nbody\n\n"
        b"From 2@xxx Mon Jan 06 11:00:00 +0000 2025\n"
        b"X-Gmail-Labels: =?UTF-8?B?0KfQtdGA0L3QvtCy0LjQutC4?=\n"
        b"From: Me <me@custom-domain.org>\n"
        b"To: support@draftservice.io\n"
        b"Subject: Draft\n"
        b"Date: Mon, 06 Jan 2025 11:00:00 +0000\n\nbody\n"
    )
    report = analyze(conn, path)
    assert report.total == 2
    assert stats(conn) == {}
