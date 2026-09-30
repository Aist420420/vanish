"""Игровые механики: очки опыта, уровни, достижения, серии дней, прогресс."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

# Решение по сервису: чем выше риск, тем больше очков.
XP_DECISION = {"high": 15, "medium": 10, "low": 5}
XP_LATER = 2
XP_SKIP = 1  # «пропустить» (обычно массово) — почти без очков, чтобы не фармить
XP_UNSUB_DONE = 15
XP_DELETE_FAILED = 5
XP_DELETE = {
    "easy": 50,
    "medium": 80,
    "hard": 150,
    "limited": 120,
    "impossible": 200,
    "": 70,
}
# Подтверждённое удаление умножается на риск: закрыть рискованный аккаунт выгоднее.
RISK_MULTIPLIER = {"high": 2.0, "medium": 1.5, "low": 1.0}
XP_ACHIEVEMENT = 25

LEVELS = [
    (0, "Оставляю следы везде"),
    (50, "Беспечный регистратор"),
    (150, "Чистильщик кукис"),
    (300, "Охотник за рассылками"),
    (500, "Мастер отписки"),
    (800, "Тень в интернете"),
    (1200, "Цифровой ниндзя"),
    (1700, "Призрак сети"),
    (2300, "Человек-невидимка"),
    (3000, "Тебя не находит Google"),
    (4000, "Легенда офлайна"),
    (5500, "Абсолютный Vanish"),
]


def level_for(xp: int) -> dict:
    idx = 0
    for i, (threshold, _) in enumerate(LEVELS):
        if xp >= threshold:
            idx = i
    start, name = LEVELS[idx]
    nxt = LEVELS[idx + 1][0] if idx + 1 < len(LEVELS) else None
    return {
        "level": idx + 1,
        "name": name,
        "xp_start": start,
        "xp_next": nxt,
        "next_name": LEVELS[idx + 1][1] if nxt is not None else None,
    }


def decision_xp(decision: str | None, risk: str = "medium") -> int:
    if decision in ("delete", "keep", "unsubscribe"):
        return XP_DECISION.get(risk, XP_DECISION["medium"])
    if decision == "later":
        return XP_LATER
    if decision == "skip":
        return XP_SKIP
    return 0


def finish_xp(decision: str | None, status: str | None, unsub_done: bool, difficulty: str,
              risk: str = "medium") -> int:
    if decision == "delete":
        if status == "deleted":
            base = XP_DELETE.get(difficulty or "", XP_DELETE[""])
            return round(base * RISK_MULTIPLIER.get(risk, 1.0))
        if status == "failed":
            return XP_DELETE_FAILED
    if decision == "unsubscribe" and unsub_done:
        return XP_UNSUB_DONE
    return 0


def service_progress(s: dict) -> float:
    """Вклад сервиса в «цифровой след очищен»: 0..1."""
    decision = s.get("decision")
    if decision in ("keep", "skip"):
        return 1.0
    if decision == "delete":
        return {"deleted": 1.0, "failed": 0.75}.get(s.get("status") or "", 0.5)
    if decision == "unsubscribe":
        return 1.0 if s.get("unsub_done") else 0.5
    return 0.0


def streak(days_with_activity: set[str], today: date) -> int:
    """Число дней подряд с активностью, заканчивая сегодня (или вчера, если сегодня ещё пусто)."""
    day = today if today.isoformat() in days_with_activity else today - timedelta(days=1)
    n = 0
    while day.isoformat() in days_with_activity:
        n += 1
        day -= timedelta(days=1)
    return n


@dataclass(frozen=True)
class Achievement:
    id: str
    title: str
    description: str
    icon: str
    check: Callable[[dict], bool]


def _year_cleared(ctx: dict) -> bool:
    by_year: dict[int, list[dict]] = {}
    for s in ctx["services"]:
        if s["first_year"]:
            by_year.setdefault(s["first_year"], []).append(s)
    return any(
        len(items) >= 3 and all(i["decision"] in ("delete", "keep", "unsubscribe", "skip") for i in items)
        for items in by_year.values()
    )


def _archaeologist(ctx: dict) -> bool:
    year = ctx["today"].year
    return any(
        s["status"] == "deleted" and s["first_year"] and s["first_year"] <= year - 10
        for s in ctx["services"]
    )


ACHIEVEMENTS: list[Achievement] = [
    Achievement("first_decision", "Первый шаг", "Принять первое решение", "👣",
                lambda c: c["decided"] >= 1),
    Achievement("decisions_10", "Разогрев", "Принять 10 решений", "🔥",
                lambda c: c["decided"] >= 10),
    Achievement("decisions_100", "Конвейер", "Принять 100 решений", "⚙️",
                lambda c: c["decided"] >= 100),
    Achievement("decisions_500", "Сортировочный центр", "Принять 500 решений", "🏭",
                lambda c: c["decided"] >= 500),
    Achievement("first_delete", "Первое исчезновение", "Подтвердить первое удаление аккаунта", "💨",
                lambda c: c["deleted"] >= 1),
    Achievement("deletes_10", "Десять шагов в тень", "Удалить 10 аккаунтов", "🌒",
                lambda c: c["deleted"] >= 10),
    Achievement("deletes_50", "Полсотни в минус", "Удалить 50 аккаунтов", "🕳️",
                lambda c: c["deleted"] >= 50),
    Achievement("hard_delete", "Крепкий орешек", "Удалить аккаунт со сложностью «hard»", "🥜",
                lambda c: any(s["status"] == "deleted" and s["difficulty"] == "hard" for s in c["services"])),
    Achievement("impossible_delete", "Невозможное возможно", "Удалить «невозможный» аккаунт", "🦄",
                lambda c: any(s["status"] == "deleted" and s["difficulty"] in ("impossible", "limited")
                              for s in c["services"])),
    Achievement("breach_closed", "Заделал брешь", "Удалить аккаунт в сервисе, который был в утечке", "🩹",
                lambda c: any(s["status"] == "deleted" and s["risk"]["breached"] for s in c["services"])),
    Achievement("high_risk_10", "Минус десять рисков", "Удалить 10 аккаунтов с высоким риском", "🎯",
                lambda c: sum(1 for s in c["services"]
                              if s["status"] == "deleted" and s["risk"]["level"] == "high") >= 10),
    Achievement("top_done", "Главное сделано", "Принять решения по всем сервисам из «Главного за 30 минут»", "⏱️",
                lambda c: c["top_total"] > 0 and c["top_open"] == 0),
    Achievement("no_high_risk", "Ноль высокого риска", "Не оставить ни одного открытого аккаунта с высоким риском",
                "🛡️", lambda c: c["high_total"] > 0 and c["high_open"] == 0),
    Achievement("archaeologist", "Археолог", "Удалить аккаунт, которому больше 10 лет", "🦴",
                _archaeologist),
    Achievement("year_cleared", "Год под ключ", "Разобрать все сервисы одного года", "📅",
                _year_cleared),
    Achievement("unsub_10", "Тишина в ящике", "Отписаться от 10 рассылок", "🔕",
                lambda c: c["unsub_done"] >= 10),
    Achievement("queue_empty", "Чистый стол", "Разобрать всю очередь сортировки", "🧹",
                lambda c: c["total"] > 0 and c["undecided"] == 0),
    Achievement("delete_queue_empty", "Без хвостов", "Пройти всю очередь удаления", "✂️",
                lambda c: c["to_delete"] > 0 and c["delete_open"] == 0),
    Achievement("manual_add", "Вспомнил всё", "Добавить сервис вручную", "🧠",
                lambda c: c["manual"] >= 1),
    Achievement("streak_3", "Привычка", "3 дня подряд", "📆",
                lambda c: c["streak"] >= 3),
    Achievement("streak_7", "Неделя тишины", "7 дней подряд", "🗓️",
                lambda c: c["streak"] >= 7),
    Achievement("today_50", "Марафон", "50 действий за один день", "🏃",
                lambda c: c["today_count"] >= 50),
    Achievement("vanish", "Vanish", "Очистить цифровой след на 100%", "👻",
                lambda c: c["total"] > 0 and c["progress"] >= 100),
]

ACHIEVEMENTS_BY_ID = {a.id: a for a in ACHIEVEMENTS}
