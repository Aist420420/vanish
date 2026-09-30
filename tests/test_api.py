import csv
import io

import pytest

from vanish import api, game


def test_decide_and_undo(analyzed):
    r = api.decide(analyzed, "ozon.ru", "delete")
    assert r["service"]["decision"] == "delete"
    assert r["service"]["status"] == "pending"
    assert r["service"]["risk"]["level"] == "high"
    assert r["game"]["xp"] == game.XP_DECISION["high"] + game.XP_ACHIEVEMENT  # «Первый шаг»
    assert [a["id"] for a in r["new_achievements"]] == ["first_decision"]
    assert r["game"]["today"] == 1

    r = api.undo(analyzed)
    assert r["service"]["decision"] is None
    assert r["service"]["status"] is None
    assert r["game"]["today"] == 0
    # Достижение остаётся, очки за решение — нет.
    assert r["game"]["xp"] == game.XP_ACHIEVEMENT
    with pytest.raises(api.ApiError):
        api.undo(analyzed)


def test_invalid_input(analyzed):
    with pytest.raises(api.ApiError):
        api.decide(analyzed, "ozon.ru", "explode")
    with pytest.raises(api.ApiError):
        api.decide(analyzed, "nope.example", "keep")
    with pytest.raises(api.ApiError):
        api.update(analyzed, "ozon.ru", {"status": "weird"})


def test_deletion_xp_depends_on_difficulty(analyzed):
    gh = api.get_service(analyzed, "github.com")
    api.decide(analyzed, "github.com", "delete")
    r = api.update(analyzed, "github.com", {"status": "deleted"})
    level = gh["risk"]["level"]
    expected = game.XP_DECISION[level] + round(game.XP_DELETE[gh["difficulty"]] * game.RISK_MULTIPLIER[level])
    ids = {a["id"] for a in r["new_achievements"]}
    assert "first_delete" in ids
    achievements = sum(1 for a in r["game"]["achievements"] if a["unlocked_at"])
    assert r["game"]["xp"] == expected + game.XP_ACHIEVEMENT * achievements
    assert r["service"]["finished_at"]

    # Откат статуса убирает очки за удаление, но не за достижения.
    r = api.update(analyzed, "github.com", {"status": "pending"})
    assert r["game"]["xp"] == game.XP_DECISION[level] + game.XP_ACHIEVEMENT * achievements


def test_unsubscribe_flow(analyzed):
    api.decide(analyzed, "skyeng.ru", "unsubscribe")
    r = api.update(analyzed, "skyeng.ru", {"unsub_done": True})
    assert r["service"]["unsub_done"] is True
    assert r["service"]["risk"]["level"] == "low"
    assert r["game"]["xp"] == game.XP_DECISION["low"] + game.XP_UNSUB_DONE + game.XP_ACHIEVEMENT


def test_changing_decision_resets_status(analyzed):
    api.decide(analyzed, "ozon.ru", "delete")
    api.update(analyzed, "ozon.ru", {"status": "failed"})
    r = api.update(analyzed, "ozon.ru", {"decision": "keep"})
    assert r["service"]["status"] is None
    assert r["service"]["decision"] == "keep"


def test_progress_percent(analyzed):
    state = api.full_state(analyzed)
    assert state["game"]["progress"] == 0
    tracked = [s for s in state["services"] if api.is_tracked(s)]
    assert all(s["confidence"] != "personal" for s in tracked)
    for s in tracked:
        api.decide(analyzed, s["domain"], "keep")
    state = api.full_state(analyzed)
    assert state["game"]["progress"] == 100
    unlocked = {a["id"] for a in state["game"]["achievements"] if a["unlocked_at"]}
    assert {"queue_empty", "vanish", "decisions_10", "year_cleared"} <= unlocked


def test_service_progress_weights():
    assert game.service_progress({"decision": None}) == 0
    assert game.service_progress({"decision": "later"}) == 0
    assert game.service_progress({"decision": "keep"}) == 1
    assert game.service_progress({"decision": "delete", "status": "pending"}) == 0.5
    assert game.service_progress({"decision": "delete", "status": "deleted"}) == 1
    assert game.service_progress({"decision": "unsubscribe", "unsub_done": False}) == 0.5


def test_levels():
    assert game.level_for(0)["level"] == 1
    assert game.level_for(49)["level"] == 1
    assert game.level_for(50)["level"] == 2
    top = game.level_for(10**6)
    assert top["xp_next"] is None and top["name"] == "Абсолютный Vanish"


def test_streak():
    from datetime import date
    today = date(2026, 9, 30)
    assert game.streak({"2026-09-30", "2026-09-29", "2026-09-28"}, today) == 3
    assert game.streak({"2026-09-29", "2026-09-28"}, today) == 2  # сегодня ещё не начинал
    assert game.streak({"2026-09-27"}, today) == 0


def test_manual_add_and_undo(analyzed):
    r = api.add_service(analyzed, "https://www.Forgotten-Forum.org/login", "Старый форум", "delete")
    s = r["service"]
    assert s["domain"] == "forgotten-forum.org"
    assert s["manual"] and s["decision"] == "delete" and s["confidence"] == "sure"
    assert "manual_add" in {a["id"] for a in r["new_achievements"]}
    with pytest.raises(api.ApiError):
        api.add_service(analyzed, "forgotten-forum.org")
    with pytest.raises(api.ApiError):
        api.add_service(analyzed, "not a domain")
    api.undo(analyzed)
    with pytest.raises(api.ApiError):
        api.get_service(analyzed, "forgotten-forum.org")


def test_note_is_not_an_undoable_action(analyzed):
    api.decide(analyzed, "ozon.ru", "delete")
    api.update(analyzed, "ozon.ru", {"note": "через чат поддержки"})
    r = api.undo(analyzed)
    assert r["undone"]["kind"] == "decide"
    assert r["service"]["decision"] is None
    assert r["service"]["note"] == "через чат поддержки"


def test_csv_export(analyzed):
    api.decide(analyzed, "ozon.ru", "delete")
    text = api.export_csv(analyzed)
    assert text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))
    header, body = rows[0], rows[1:]
    assert header[0] == "Домен"
    ozon = dict(zip(header, next(r for r in body if r[0] == "ozon.ru")))
    assert ozon["Решение"] == "удалить"
    assert ozon["Статус удаления"] == "в очереди"
    assert ozon["Риск"] == "высокий" and ozon["Категория"] == "Магазин"
    assert body[0][0] == "facebook.com"  # сортировка по риску, утечки первыми
    assert "Facebook" in dict(zip(header, body[0]))["Утечки"]


def test_progress_roundtrip(analyzed, conn):
    from vanish.analyzer import analyze
    api.decide(analyzed, "ozon.ru", "delete")
    api.update(analyzed, "ozon.ru", {"status": "deleted", "note": "готово"})
    api.add_service(analyzed, "manual.example.org", "Ручной")
    exported = api.export_progress(analyzed)
    assert exported["app"] == "vanish"

    # Импорт в чистую базу (например, на другом компьютере до анализа почты).
    result = api.import_progress(conn, exported)
    assert result["imported"] == 2
    ozon = api.get_service(conn, "ozon.ru")
    assert ozon["status"] == "deleted" and ozon["note"] == "готово"
    assert api.get_service(conn, "manual.example.org")["manual"]
    g1 = api.game_state(analyzed)
    g2 = api.game_state(conn)
    assert g1["xp"] == g2["xp"]

    with pytest.raises(api.ApiError):
        api.import_progress(conn, {"foo": 1})


def test_undo_target_describes_next_undo(analyzed):
    assert api.full_state(analyzed)["meta"]["undo_target"] is None
    r = api.decide(analyzed, "github.com", "keep")
    assert r["undo_target"] == {
        "kind": "decide", "domain": "github.com",
        "before": {"decision": None, "status": None, "unsub_done": False},
    }
    r = api.bulk(analyzed, "skip_low")
    assert r["undo_target"] == {"kind": "bulk", "domain": None, "before": None}
    api.undo(analyzed)
    assert api.undo(analyzed)["undo_target"] is None
