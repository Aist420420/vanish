import sqlite3

import pytest

from vanish import api, breaches, game, risk
from vanish.store import connect


@pytest.mark.parametrize(
    "subject, topic, purchase",
    [
        ("Ваш заказ №48213 оформлен", "", True),
        ("Ваш заказ доставлен в пункт выдачи", "delivery", True),
        ("Your Spotify Premium receipt", "", True),
        ("Invoice #123 for March", "", True),
        ("Ваше бронирование подтверждено", "tickets", True),
        ("Электронный билет на рейс SU 1234", "tickets", False),
        ("Выписка по карте за март", "finance", False),
        ("Результаты анализов готовы", "medical", False),
        ("Новая вакансия: Python-разработчик", "jobs", False),
        ("Иван добавил вас в друзья", "social", False),
        ("У вас новая симпатия!", "dating", False),
        ("Ваш штраф ГИБДД оплачен", "gov", True),
        ("Medium Daily Digest", "newsletter", False),
        ("Лучшие статьи недели", "newsletter", False),
        ("Your support ticket #4411 was updated", "", False),
        ("Build job failed on main", "", False),
        ("Чек-лист для запуска проекта", "", False),
        ("", "", False),
    ],
)
def test_subject_topics(subject, topic, purchase):
    assert risk.subject_topics(subject) == (topic, purchase)


def test_dominant_topic_prefers_high_risk():
    assert risk.dominant_topic({"newsletter": 20, "shop": 1}) == "shop"
    assert risk.dominant_topic({"newsletter": 3, "news": 5}) == "news"
    assert risk.dominant_topic({}) == ""


@pytest.mark.parametrize(
    "domain, category",
    [
        ("ozon.ru", "shop"),
        ("sberbank.ru", "finance"),
        ("hh.ru", "jobs"),
        ("gosuslugi.ru", "gov"),
        ("hmrc.gov.uk", "gov"),
        ("steampowered.com", "shop"),       # store.steampowered.com в справочнике
        ("medium.com", "blog"),
        ("my-super-bank.com", "finance"),    # по слову в домене
        ("citytaxi.ru", "taxi"),
        ("github.com", None),
    ],
)
def test_category_for_domain(domain, category):
    assert risk.category_for_domain(domain) == category


def _leaks(*items):
    return breaches.BreachIndex(list(items))


def test_assess_scoring():
    empty = _leaks()
    shop = risk.assess("ozon.ru", purchases=3, confidence="sure", index=empty)
    assert shop["level"] == "high" and shop["category"] == "shop"
    assert "были покупки или заказы" in shop["reasons"]

    news = risk.assess("vc.ru", confidence="newsletter", index=empty)
    assert news["level"] == "low"

    plain = risk.assess("github.com", confidence="sure", index=empty)
    assert plain["level"] == "medium" and plain["category"] == "other"

    # Подборки «на этой неделе» не превращают сервис с аккаунтом в рассылку.
    netflix = risk.assess("netflix.com", topic="newsletter", purchases=1, confidence="sure", index=empty)
    assert netflix["category"] == "other" and netflix["level"] == "high"
    only_news = risk.assess("unknown-digest.io", topic="newsletter", confidence="newsletter", index=empty)
    assert only_news["category"] == "newsletter" and only_news["level"] == "low"


def test_breach_marks_and_raises_risk():
    leaks = _leaks({"Name": "Duo", "Title": "Duo", "Domain": "mail.duolingo.com", "BreachDate": "2023-01-24",
                    "PwnCount": 10, "DataClasses": ["Email addresses", "Names"]})
    after = risk.assess("duolingo.com", confidence="newsletter", first_day="2022-05-01", index=leaks)
    assert after["breached"] and after["breach_after_signup"]
    assert after["level"] == "medium"  # утечка после регистрации — не ниже среднего
    assert after["breaches"][0]["data_ru"] == ["e-mail", "имена"]

    before = risk.assess("duolingo.com", confidence="newsletter", first_day="2024-01-01", index=leaks)
    assert before["breached"] and not before["breach_after_signup"]
    assert before["score"] < after["score"]


def test_breach_index_filters_noise():
    index = _leaks(
        {"Name": "A", "Domain": "shop.example.com", "BreachDate": "2020-01-01"},
        {"Name": "Fake", "Domain": "fake.com", "BreachDate": "2020-01-01", "IsFabricated": True},
        {"Name": "Spam", "Domain": "spam.com", "BreachDate": "2020-01-01", "IsSpamList": True},
        {"Name": "NoDomain", "Domain": "", "BreachDate": "2020-01-01"},
    )
    assert [b.name for b in index.match("example.com")] == ["A"]
    assert index.match("fake.com") == [] and index.match("spam.com") == []
    assert len(index) == 1


def test_bundled_breach_list_is_usable():
    index = breaches.default_index()
    assert len(index) > 500
    assert index.match("linkedin.com")


def test_state_sorted_by_risk(analyzed):
    services = api.full_state(analyzed)["services"]
    tracked = [s for s in services if api.is_tracked(s)]
    levels = [risk.LEVEL_ORDER[s["risk"]["level"]] for s in tracked]
    assert levels == sorted(levels)
    high = [s for s in tracked if s["risk"]["level"] == "high"]
    # Внутри высокого риска утёкшие сервисы идут первыми.
    flags = [s["risk"]["breached"] for s in high]
    assert flags == sorted(flags, reverse=True) and flags[0]
    assert tracked[0]["domain"] == "facebook.com"
    by = {s["domain"]: s["risk"] for s in services}
    assert by["ozon.ru"]["level"] == "high" and by["ozon.ru"]["purchases"] > 0
    assert by["skyeng.ru"]["level"] == "low"
    assert by["duolingo.com"]["breached"]


def test_top_services(analyzed):
    services = api.list_services(analyzed)
    top = api.top_services(services, n=5)
    assert len(top) == 5
    assert all(s["risk"]["level"] == "high" for s in top)
    summary = api.risk_summary(services)
    assert summary["index"] == 100
    assert summary["high_open"] == summary["high_total"] > 0


def test_risk_index_goes_down(analyzed):
    api.decide(analyzed, "facebook.com", "delete")
    r = api.update(analyzed, "facebook.com", {"status": "deleted"})
    summary = r["game"]["risk"]
    assert summary["index"] < 100
    assert summary["high_open"] == summary["high_total"] - 1
    ids = {a["id"] for a in r["new_achievements"]}
    assert "breach_closed" in ids
    # Удаление высокорискового аккаунта из утечки даёт больше очков, чем такого же низкорискового.
    assert game.finish_xp("delete", "deleted", False, "", "high") > game.finish_xp("delete", "deleted", False, "", "low")


def test_bulk_unsubscribe_low_and_undo(analyzed):
    services = api.list_services(analyzed)
    targets = {s["domain"] for s in api.bulk_targets(services, "unsub_low")}
    assert {"skyeng.ru", "vc.ru", "producthunt.com"} <= targets
    assert "ozon.ru" not in targets
    assert all(s["risk"]["level"] == "low" for s in services if s["domain"] in targets)

    r = api.bulk(analyzed, "unsub_low")
    assert r["bulk"]["count"] == len(targets)
    after = {s["domain"]: s for s in api.list_services(analyzed)}
    assert all(after[d]["decision"] == "unsubscribe" for d in targets)
    assert r["game"]["today"] == 1  # одно действие

    r = api.undo(analyzed)
    assert r["undone"]["kind"] == "bulk" and r["undone"]["count"] == len(targets)
    after = {s["domain"]: s for s in api.list_services(analyzed)}
    assert all(after[d]["decision"] is None for d in targets)
    unlocked = sum(1 for a in r["game"]["achievements"] if a["unlocked_at"])
    assert r["game"]["xp"] == game.XP_ACHIEVEMENT * unlocked  # очки за решения откатились


def test_bulk_skip_low_leaves_decided_alone(analyzed):
    api.decide(analyzed, "medium.com", "delete")
    r = api.bulk(analyzed, "skip_low")
    after = {s["domain"]: s for s in api.list_services(analyzed)}
    assert after["medium.com"]["decision"] == "delete"
    skipped = [d for d, s in after.items() if s["decision"] == "skip"]
    assert skipped and all(after[d]["risk"]["level"] == "low" for d in skipped)
    assert r["game"]["progress"] > 0
    # Пропуск не засчитывается в «решения» для достижений.
    ctx = api._context(analyzed, list(after.values()))
    assert ctx["decided"] == 1
    with pytest.raises(api.ApiError):
        api.bulk(analyzed, "skip_low")  # больше нечего пропускать
    with pytest.raises(api.ApiError):
        api.bulk(analyzed, "nuke_everything")


def test_migration_adds_columns(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE messages (hash TEXT PRIMARY KEY, domain TEXT NOT NULL, kind INTEGER NOT NULL DEFAULT 0,"
        " ts INTEGER, unsub INTEGER NOT NULL DEFAULT 0, signal INTEGER NOT NULL DEFAULT 0,"
        " sender TEXT NOT NULL DEFAULT '');"
        "INSERT INTO messages(hash, domain) VALUES ('h', 'ozon.ru');"
    )
    old.close()
    conn = connect(path)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(messages)")}
    assert {"topic", "purchase"} <= cols
    assert tuple(conn.execute("SELECT topic, purchase FROM messages").fetchone()) == ("", 0)
    conn.close()


def test_reimport_fills_topics_for_old_rows(conn, mbox_path):
    from vanish.analyzer import analyze
    analyze(conn, mbox_path)
    conn.execute("UPDATE messages SET topic = '', purchase = 0")
    conn.commit()
    analyze(conn, mbox_path)
    assert conn.execute("SELECT SUM(purchase) FROM messages").fetchone()[0] > 0
