"""Бизнес-логика приложения поверх SQLite: состояние, решения, отмена, экспорт."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import date, datetime, timezone
from urllib.parse import quote, urlsplit

from . import breaches, game, jdm, risk
from .psl import normalize_host
from .signals import NEWSLETTER, PERSONAL, SURE
from .store import get_meta

DECISIONS = ("delete", "keep", "unsubscribe", "later", "skip")
# «Решено» для счётчиков и достижений: пропуск (обычно массовый) сюда не входит.
RESOLVING = ("delete", "keep", "unsubscribe")
OPEN = (None, "later")
DELETE_STATUSES = ("pending", "deleted", "failed", "later")
# Поля, которые откатывает «Отменить» (заметки и названия не откатываются).
UNDO_FIELDS = ("decision", "status", "unsub_done", "decided_at", "finished_at", "xp_decision", "xp_finish")
GOOGLE_CONNECTIONS = "https://myaccount.google.com/connections"


class ApiError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> date:
    return datetime.now().date()


def _iso_day(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


SERVICE_QUERY = """
SELECT s.*, st.count, st.first_ts, st.last_ts, st.unsub, st.strong, st.weak, st.sent_to,
       st.confidence, st.purchases, st.topic, st.spam, di.samples, di.display_name, di.google_linked,
       di.unsub_url, di.unsub_ts
FROM services s
LEFT JOIN domain_stats st ON st.domain = s.domain
LEFT JOIN domain_info di ON di.domain = s.domain
"""


def _pick_name(row: sqlite3.Row, entry: jdm.JdmEntry | None) -> str:
    if row["name"]:
        return row["name"]
    if entry:
        return entry.name
    display = (row["display_name"] or "").strip().strip('"')
    if display and len(display) <= 32 and "@" not in display:
        return display
    label = row["domain"].split(".")[0]
    return label[:1].upper() + label[1:]


def unsubscribe_view(row: sqlite3.Row, confidence: str) -> dict:
    """Прямая ссылка отписки из List-Unsubscribe — только там, где нажать её безопасно.

    Переход по ссылке сообщает отправителю, что адрес живой. Для сервиса, где у меня точно есть
    аккаунт, это не новость, а спамеру или непонятной рассылке — подтверждение адреса.
    Поэтому ссылка отдаётся в интерфейс, только если аккаунт подтверждён и писем в «Спаме» не было.
    """
    url = row["unsub_url"] or ""
    spam = row["spam"] or 0
    warning = None
    if url:
        if spam:
            warning = "spam"
        elif confidence != SURE:
            warning = "unconfirmed"
    return {
        "url": url if url and not warning else None,
        "host": urlsplit(url).hostname if url else None,
        "date": _iso_day(row["unsub_ts"]) if url and row["unsub_ts"] else None,
        "warning": warning,
        "spam": spam,
    }


def service_view(row: sqlite3.Row, index: jdm.JdmIndex, leaks: breaches.BreachIndex | None = None) -> dict:
    domain = row["domain"]
    entry = index.match(domain)
    name = _pick_name(row, entry)
    samples = json.loads(row["samples"] or "[]")
    first_day = _iso_day(row["first_ts"])
    confidence = row["confidence"] or (SURE if row["manual"] else "newsletter")
    site = row["site"] or f"https://{domain}"
    assessment = risk.assess(
        domain, topic=row["topic"] or "", purchases=row["purchases"] or 0, confidence=confidence,
        first_day=first_day, index=leaks,
    )
    return {
        "domain": domain,
        "name": name,
        "manual": bool(row["manual"]),
        "decision": row["decision"],
        "status": row["status"],
        "unsub_done": bool(row["unsub_done"]),
        "note": row["note"],
        "decided_at": row["decided_at"],
        "finished_at": row["finished_at"],
        "count": row["count"] or 0,
        "first": first_day,
        "last": _iso_day(row["last_ts"]),
        "first_year": int(first_day[:4]) if first_day else None,
        "has_unsub": bool(row["unsub"]),
        "strong": row["strong"] or 0,
        "weak": row["weak"] or 0,
        "sent_to": row["sent_to"] or 0,
        "confidence": confidence,
        "samples": [s["s"] for s in samples],
        "google_linked": bool(row["google_linked"]),
        "unsubscribe": unsubscribe_view(row, confidence),
        "difficulty": entry.difficulty if entry else "",
        "risk": assessment,
        "jdm": {
            "name": entry.name,
            "url": entry.url,
            "notes": entry.notes,
            "email": entry.email,
        } if entry else None,
        "links": {
            "site": site,
            "delete": entry.url if entry and entry.url else None,
            "gmail": f"https://mail.google.com/mail/u/0/#search/from%3A{quote(domain)}",
            "google_connections": GOOGLE_CONNECTIONS,
            "search_delete": "https://www.google.com/search?q=" + quote(f"как удалить аккаунт {name}"),
        },
    }


def list_services(conn: sqlite3.Connection) -> list[dict]:
    index = jdm.default_index()
    leaks = breaches.default_index()
    return [service_view(r, index, leaks) for r in conn.execute(SERVICE_QUERY)]


def get_service(conn: sqlite3.Connection, domain: str) -> dict:
    row = conn.execute(SERVICE_QUERY + " WHERE s.domain = ?", (domain,)).fetchone()
    if row is None:
        raise ApiError(f"Сервис {domain} не найден")
    return service_view(row, jdm.default_index())


def is_tracked(s: dict) -> bool:
    """Учитывается ли сервис в прогрессе (личная переписка — нет, пока я сам не решу)."""
    return s["confidence"] != PERSONAL or s["decision"] is not None or s["manual"]


def progress_percent(services: list[dict]) -> float:
    tracked = [s for s in services if is_tracked(s)]
    if not tracked:
        return 0.0
    return round(100.0 * sum(game.service_progress(s) for s in tracked) / len(tracked), 1)


def _activity(conn: sqlite3.Connection) -> dict[str, int]:
    return {r["day"]: r["count"] for r in conn.execute("SELECT day, count FROM activity WHERE count > 0")}


def top_services(services: list[dict], n: int = risk.TOP_N) -> list[dict]:
    """«Главное за 30 минут»: самые рискованные сервисы (набор не зависит от решений)."""
    return sorted((s for s in services if is_tracked(s)), key=risk.sort_key)[:n]


def risk_summary(services: list[dict]) -> dict:
    tracked = [s for s in services if is_tracked(s)]
    high = [s for s in tracked if s["risk"]["level"] == risk.HIGH]
    total_score = sum(s["risk"]["score"] for s in tracked)
    open_score = sum(s["risk"]["score"] for s in tracked if not risk.is_closed(s))
    top = top_services(services)
    return {
        "index": round(100 * open_score / total_score) if total_score else 0,
        "high_total": len(high),
        "high_open": sum(1 for s in high if not risk.is_closed(s)),
        "breached_open": sum(1 for s in tracked if s["risk"]["breached"] and not risk.is_closed(s)),
        "top_total": len(top),
        "top_open": sum(1 for s in top if s["decision"] in OPEN),
    }


def _context(conn: sqlite3.Connection, services: list[dict]) -> dict:
    tracked = [s for s in services if is_tracked(s)]
    activity = _activity(conn)
    today = _today()
    summary = risk_summary(services)
    return {
        **{k: summary[k] for k in ("high_total", "high_open", "top_total", "top_open")},
        "services": tracked,
        "today": today,
        "total": len(tracked),
        "decided": sum(1 for s in tracked if s["decision"] in RESOLVING),
        "undecided": sum(1 for s in tracked if s["decision"] is None),
        "deleted": sum(1 for s in tracked if s["decision"] == "delete" and s["status"] == "deleted"),
        "to_delete": sum(1 for s in tracked if s["decision"] == "delete"),
        "delete_open": sum(
            1 for s in tracked if s["decision"] == "delete" and s["status"] not in ("deleted", "failed")
        ),
        "unsub_done": sum(1 for s in tracked if s["decision"] == "unsubscribe" and s["unsub_done"]),
        "manual": sum(1 for s in services if s["manual"]),
        "streak": game.streak(set(activity), today),
        "today_count": activity.get(today.isoformat(), 0),
        "progress": progress_percent(services),
    }


def game_state(conn: sqlite3.Connection, services: list[dict] | None = None) -> dict:
    services = services if services is not None else list_services(conn)
    unlocked = {r["id"]: r["unlocked_at"] for r in conn.execute("SELECT id, unlocked_at FROM achievements")}
    xp_row = conn.execute("SELECT COALESCE(SUM(xp_decision + xp_finish), 0) FROM services").fetchone()
    xp = xp_row[0] + game.XP_ACHIEVEMENT * len(unlocked)
    activity = _activity(conn)
    today = _today()
    return {
        "xp": xp,
        **game.level_for(xp),
        "streak": game.streak(set(activity), today),
        "today": activity.get(today.isoformat(), 0),
        "progress": progress_percent(services),
        "risk": risk_summary(services),
        "achievements": [
            {
                "id": a.id,
                "title": a.title,
                "description": a.description,
                "icon": a.icon,
                "unlocked_at": unlocked.get(a.id),
            }
            for a in game.ACHIEVEMENTS
        ],
    }


def check_achievements(conn: sqlite3.Connection, services: list[dict]) -> list[dict]:
    ctx = _context(conn, services)
    unlocked = {r["id"] for r in conn.execute("SELECT id FROM achievements")}
    new = []
    for a in game.ACHIEVEMENTS:
        if a.id in unlocked:
            continue
        if a.check(ctx):
            conn.execute("INSERT INTO achievements(id, unlocked_at) VALUES (?, ?)", (a.id, _now()))
            new.append({"id": a.id, "title": a.title, "description": a.description, "icon": a.icon})
    return new


def full_state(conn: sqlite3.Connection) -> dict:
    services = list_services(conn)
    services.sort(key=risk.sort_key)
    return {
        "services": services,
        "game": game_state(conn, services),
        "meta": {
            "last_import": get_meta(conn, "last_import"),
            "last_import_file": get_meta(conn, "last_import_file"),
            "jdm_count": len(jdm.default_index()),
            "breaches_count": len(breaches.default_index()),
            "top_n": risk.TOP_N,
            "can_undo": _last_action(conn) is not None,
            "undo_target": undo_target(conn),
            "demo": get_meta(conn, "demo") == "1",
        },
    }


# --- Изменения ---------------------------------------------------------------

def _snapshot(conn: sqlite3.Connection, domain: str) -> dict:
    row = conn.execute(
        f"SELECT {', '.join(UNDO_FIELDS)} FROM services WHERE domain = ?", (domain,)
    ).fetchone()
    if row is None:
        raise ApiError(f"Сервис {domain} не найден")
    return dict(row)


def _log(conn: sqlite3.Connection, kind: str, domain: str, before: dict | None) -> None:
    day = _today().isoformat()
    conn.execute(
        "INSERT INTO actions(ts, day, kind, domain, before) VALUES (?, ?, ?, ?, ?)",
        (_now(), day, kind, domain, json.dumps(before, ensure_ascii=False)),
    )
    conn.execute(
        "INSERT INTO activity(day, count) VALUES (?, 1) "
        "ON CONFLICT(day) DO UPDATE SET count = count + 1",
        (day,),
    )


def _recompute_xp(conn: sqlite3.Connection, domain: str) -> None:
    s = get_service(conn, domain)
    conn.execute(
        "UPDATE services SET xp_decision = ?, xp_finish = ? WHERE domain = ?",
        (
            game.decision_xp(s["decision"], s["risk"]["level"]),
            game.finish_xp(s["decision"], s["status"], s["unsub_done"], s["difficulty"], s["risk"]["level"]),
            domain,
        ),
    )


def _result(conn: sqlite3.Connection, domain: str | None) -> dict:
    services = list_services(conn)
    new = check_achievements(conn, services)
    conn.commit()
    service = next((s for s in services if s["domain"] == domain), None) if domain else None
    return {
        "service": service,
        "game": game_state(conn, services),
        "new_achievements": new,
        "can_undo": _last_action(conn) is not None,
        "undo_target": undo_target(conn),
    }


def decide(conn: sqlite3.Connection, domain: str, decision: str | None) -> dict:
    if decision is not None and decision not in DECISIONS:
        raise ApiError(f"Неизвестное решение: {decision}")
    before = _snapshot(conn, domain)
    status = "pending" if decision == "delete" else None
    if decision == "delete" and before["decision"] == "delete":
        status = before["status"]
    unsub_done = before["unsub_done"] if decision == "unsubscribe" else 0
    conn.execute(
        "UPDATE services SET decision = ?, status = ?, unsub_done = ?, decided_at = ?, "
        "finished_at = CASE WHEN ? THEN finished_at END, updated_at = ? WHERE domain = ?",
        (decision, status, unsub_done, _now() if decision else None,
         decision == before["decision"], _now(), domain),
    )
    _recompute_xp(conn, domain)
    _log(conn, "decide", domain, before)
    return _result(conn, domain)


def update(conn: sqlite3.Connection, domain: str, fields: dict) -> dict:
    before = _snapshot(conn, domain)
    changes: dict = {}
    if "decision" in fields:
        decision = fields["decision"]
        if decision is not None and decision not in DECISIONS:
            raise ApiError(f"Неизвестное решение: {decision}")
        if decision != before["decision"]:
            changes["decision"] = decision
            changes["decided_at"] = _now() if decision else None
            changes["status"] = "pending" if decision == "delete" else None
            if decision != "unsubscribe":
                changes["unsub_done"] = 0
    if "status" in fields:
        status = fields["status"]
        if status is not None and status not in DELETE_STATUSES:
            raise ApiError(f"Неизвестный статус: {status}")
        changes["status"] = status
        changes["finished_at"] = _now() if status in ("deleted", "failed") else None
    if "unsub_done" in fields:
        changes["unsub_done"] = 1 if fields["unsub_done"] else 0
        changes["finished_at"] = _now() if fields["unsub_done"] else None
    if "note" in fields:
        changes["note"] = str(fields["note"] or "")[:2000]
    if "name" in fields:
        changes["name"] = str(fields["name"] or "")[:100]
    if not changes:
        return _result(conn, domain)
    changes["updated_at"] = _now()
    assignments = ", ".join(f"{k} = ?" for k in changes)
    conn.execute(f"UPDATE services SET {assignments} WHERE domain = ?", (*changes.values(), domain))
    _recompute_xp(conn, domain)
    # Правка заметки — не игровое действие: не засчитывается в серию и не отменяется через Z.
    if set(changes) - {"note", "name", "updated_at"}:
        _log(conn, "update", domain, before)
    return _result(conn, domain)


def add_service(conn: sqlite3.Connection, domain_or_url: str, name: str = "", decision: str | None = None) -> dict:
    raw = (domain_or_url or "").strip()
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    host = normalize_host(raw.split("/", 1)[0].split("?", 1)[0]).removeprefix("www.")
    if not host or "." not in host:
        raise ApiError("Укажите домен сервиса, например example.com")
    if decision is not None and decision not in DECISIONS:
        raise ApiError(f"Неизвестное решение: {decision}")
    existing = conn.execute("SELECT domain FROM services WHERE domain = ?", (host,)).fetchone()
    if existing:
        raise ApiError(f"Сервис {host} уже есть в списке")
    conn.execute(
        "INSERT INTO services(domain, name, site, manual, decision, status, decided_at, updated_at) "
        "VALUES (?, ?, ?, 1, ?, ?, ?, ?)",
        (host, name.strip()[:100], f"https://{host}", decision,
         "pending" if decision == "delete" else None, _now() if decision else None, _now()),
    )
    _recompute_xp(conn, host)
    _log(conn, "add", host, None)
    return _result(conn, host)


# Массовые действия: (решение, какие из ещё не разобранных сервисов затрагивает).
BULK_ACTIONS = {
    # «Все рассылки низкого риска → только отписаться».
    "unsub_low": ("unsubscribe", lambda s: s["risk"]["level"] == risk.LOW
                  and (s["has_unsub"] or s["confidence"] == NEWSLETTER)),
    # «Все оставшиеся низкого риска → пропустить».
    "skip_low": ("skip", lambda s: s["risk"]["level"] == risk.LOW),
}


def bulk_targets(services: list[dict], action: str) -> list[dict]:
    if action not in BULK_ACTIONS:
        raise ApiError(f"Неизвестное массовое действие: {action}")
    _, match = BULK_ACTIONS[action]
    return [s for s in services if is_tracked(s) and s["decision"] in OPEN and match(s)]


def bulk(conn: sqlite3.Connection, action: str) -> dict:
    """Одно решение для группы сервисов. Отменяется целиком одним «Отменить»."""
    targets = bulk_targets(list_services(conn), action)
    if not targets:
        raise ApiError("Нет подходящих сервисов")
    decision, _ = BULK_ACTIONS[action]
    before = {}
    now = _now()
    for s in targets:
        before[s["domain"]] = _snapshot(conn, s["domain"])
        conn.execute(
            "UPDATE services SET decision = ?, status = NULL, unsub_done = 0, decided_at = ?, finished_at = NULL, "
            "xp_decision = ?, xp_finish = 0, updated_at = ? WHERE domain = ?",
            (decision, now, game.decision_xp(decision, s["risk"]["level"]), now, s["domain"]),
        )
    _log(conn, "bulk", action, before)
    result = _result(conn, None)
    result["bulk"] = {"action": action, "decision": decision, "count": len(targets)}
    return result


def _last_action(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM actions WHERE undone = 0 ORDER BY id DESC LIMIT 1").fetchone()


def undo_target(conn: sqlite3.Connection) -> dict | None:
    """Что отменит следующее «Отменить»: интерфейс сразу возвращает карточку, не дожидаясь ответа."""
    action = _last_action(conn)
    if action is None:
        return None
    if action["kind"] not in ("decide", "update"):
        return {"kind": action["kind"], "domain": None, "before": None}
    before = json.loads(action["before"])
    return {
        "kind": action["kind"],
        "domain": action["domain"],
        "before": {"decision": before["decision"], "status": before["status"],
                   "unsub_done": bool(before["unsub_done"])},
    }


def undo(conn: sqlite3.Connection) -> dict:
    action = _last_action(conn)
    if action is None:
        raise ApiError("Нечего отменять")
    domain = action["domain"]
    before = json.loads(action["before"])
    if action["kind"] == "add":
        conn.execute("DELETE FROM services WHERE domain = ? AND manual = 1", (domain,))
    elif action["kind"] == "bulk":
        for dom, snapshot in before.items():
            assignments = ", ".join(f"{k} = ?" for k in snapshot)
            conn.execute(f"UPDATE services SET {assignments} WHERE domain = ?", (*snapshot.values(), dom))
    else:
        assignments = ", ".join(f"{k} = ?" for k in before)
        conn.execute(f"UPDATE services SET {assignments} WHERE domain = ?", (*before.values(), domain))
    conn.execute("UPDATE actions SET undone = 1 WHERE id = ?", (action["id"],))
    conn.execute("UPDATE activity SET count = MAX(count - 1, 0) WHERE day = ?", (action["day"],))
    result = _result(conn, domain if action["kind"] not in ("add", "bulk") else None)
    result["undone"] = {"kind": action["kind"], "domain": domain,
                        "count": len(before) if action["kind"] == "bulk" else 1}
    return result


# --- Экспорт / импорт ----------------------------------------------------------

CONFIDENCE_RU = {"sure": "точно аккаунт", "likely": "вероятно", "newsletter": "только рассылка",
                 "personal": "переписка"}
DECISION_RU = {"delete": "удалить", "keep": "оставить", "unsubscribe": "отписаться", "later": "отложено",
               "skip": "пропущено", None: "не разобрано"}
RISK_RU = {"high": "высокий", "medium": "средний", "low": "низкий"}
STATUS_RU = {"pending": "в очереди", "deleted": "удалено", "failed": "не получилось", "later": "позже",
             None: ""}


def export_csv(conn: sqlite3.Connection) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow([
        "Домен", "Название", "Риск", "Балл риска", "Категория", "Покупки", "Утечки", "Уверенность", "Писем", "Первое письмо", "Последнее письмо", "Рассылка",
        "Решение", "Статус удаления", "Отписка выполнена", "Сложность удаления", "Ссылка на удаление",
        "Заметка", "Добавлен вручную",
    ])
    services = list_services(conn)
    services.sort(key=risk.sort_key)
    for s in services:
        r = s["risk"]
        writer.writerow([
            s["domain"], s["name"], RISK_RU[r["level"]], r["score"], r["category_label"],
            "да" if r["purchases"] else "", ", ".join(f'{b["title"]} ({b["date"][:4]})' for b in r["breaches"]),
            CONFIDENCE_RU.get(s["confidence"], s["confidence"]), s["count"],
            s["first"] or "", s["last"] or "", "да" if s["has_unsub"] else "нет",
            DECISION_RU.get(s["decision"], s["decision"]), STATUS_RU.get(s["status"], s["status"]),
            "да" if s["unsub_done"] else "", s["difficulty"], s["links"]["delete"] or "",
            s["note"], "да" if s["manual"] else "",
        ])
    return "﻿" + buf.getvalue()


PROGRESS_FIELDS = ("name", "site", "manual", "decision", "status", "unsub_done", "note", "decided_at", "finished_at")


def export_progress(conn: sqlite3.Connection) -> dict:
    services = [
        dict(r) for r in conn.execute(
            f"SELECT domain, {', '.join(PROGRESS_FIELDS)} FROM services "
            "WHERE decision IS NOT NULL OR manual = 1 OR note != '' OR name != ''"
        )
    ]
    return {
        "app": "vanish",
        "version": 1,
        "exported_at": _now(),
        "services": services,
        "achievements": [dict(r) for r in conn.execute("SELECT id, unlocked_at FROM achievements")],
        "activity": [dict(r) for r in conn.execute("SELECT day, count FROM activity")],
    }


def import_progress(conn: sqlite3.Connection, data: dict) -> dict:
    if not isinstance(data, dict) or data.get("app") != "vanish":
        raise ApiError("Это не файл прогресса Vanish")
    imported = 0
    for item in data.get("services") or []:
        host = normalize_host(str(item.get("domain", "")))
        if not host:
            continue
        decision = item.get("decision") if item.get("decision") in DECISIONS else None
        status = item.get("status") if item.get("status") in DELETE_STATUSES else None
        conn.execute("INSERT OR IGNORE INTO services(domain, manual) VALUES (?, ?)",
                     (host, 1 if item.get("manual") else 0))
        conn.execute(
            "UPDATE services SET name = ?, site = ?, decision = ?, status = ?, unsub_done = ?, note = ?, "
            "decided_at = ?, finished_at = ?, updated_at = ? WHERE domain = ?",
            (
                str(item.get("name") or "")[:100], str(item.get("site") or ""), decision, status,
                1 if item.get("unsub_done") else 0, str(item.get("note") or "")[:2000],
                item.get("decided_at"), item.get("finished_at"), _now(), host,
            ),
        )
        _recompute_xp(conn, host)
        imported += 1
    known = {a.id for a in game.ACHIEVEMENTS}
    for a in data.get("achievements") or []:
        if a.get("id") in known:
            conn.execute("INSERT OR IGNORE INTO achievements(id, unlocked_at) VALUES (?, ?)",
                         (a["id"], a.get("unlocked_at") or _now()))
    for a in data.get("activity") or []:
        try:
            day = date.fromisoformat(str(a.get("day"))).isoformat()
            count = max(int(a.get("count", 0)), 0)
        except (TypeError, ValueError):
            continue
        conn.execute(
            "INSERT INTO activity(day, count) VALUES (?, ?) "
            "ON CONFLICT(day) DO UPDATE SET count = MAX(count, excluded.count)",
            (day, count),
        )
    # Импорт нельзя отменить по Z: история действий относится к старому состоянию.
    conn.execute("UPDATE actions SET undone = 1")
    conn.commit()
    return {"imported": imported}
