"""Публичный список утечек Have I Been Pwned: локальная копия, обновление, сопоставление доменов.

Скачивается только общий каталог утечек (https://haveibeenpwned.com/api/v3/breaches) —
без ключа и без адресов почты. Данные HIBP распространяются по лицензии CC BY 4.0.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import RESOURCES_DIR
from .signals import service_domain

BREACHES_PATH = RESOURCES_DIR / "hibp_breaches.json"
BREACHES_URL = "https://haveibeenpwned.com/api/v3/breaches"
# Поля, которые сохраняются локально (описания с HTML и логотипы не нужны).
KEEP_FIELDS = ("Name", "Title", "Domain", "BreachDate", "PwnCount", "DataClasses",
               "IsVerified", "IsSensitive", "IsSpamList", "IsMalware", "IsStealerLog")


@dataclass(frozen=True)
class Breach:
    name: str
    title: str
    domain: str
    date: str          # YYYY-MM-DD
    pwn_count: int
    data_classes: tuple[str, ...]
    verified: bool

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "date": self.date,
            "pwn_count": self.pwn_count,
            "data": list(self.data_classes),
            "verified": self.verified,
        }


class BreachIndex:
    def __init__(self, items: list[dict]):
        self.by_domain: dict[str, list[Breach]] = {}
        self.count = 0
        for item in items:
            if item.get("IsFabricated") or item.get("IsSpamList") or item.get("IsMalware") or item.get("IsStealerLog"):
                continue  # не утечка базы конкретного сервиса
            dom = service_domain(str(item.get("Domain") or ""))
            if not dom:
                continue
            breach = Breach(
                name=str(item.get("Name", "")),
                title=str(item.get("Title") or item.get("Name") or ""),
                domain=dom,
                date=str(item.get("BreachDate") or "")[:10],
                pwn_count=int(item.get("PwnCount") or 0),
                data_classes=tuple(str(c) for c in item.get("DataClasses") or []),
                verified=bool(item.get("IsVerified", True)),
            )
            self.by_domain.setdefault(dom, []).append(breach)
            self.count += 1
        for items_ in self.by_domain.values():
            items_.sort(key=lambda b: b.date, reverse=True)

    def __len__(self) -> int:
        return self.count

    def match(self, domain: str) -> list[Breach]:
        return self.by_domain.get(domain, [])


def load_items(path: Path = BREACHES_PATH) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


@lru_cache(maxsize=1)
def default_index() -> BreachIndex:
    return BreachIndex(load_items())


def update(path: Path = BREACHES_PATH, url: str = BREACHES_URL, timeout: int = 60) -> int:
    """Скачивает свежий каталог утечек. Запрос не содержит никаких моих данных."""
    req = urllib.request.Request(url, headers={"User-Agent": "Vanish/1.0 (local account cleanup)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list) or not data or not isinstance(data[0], dict) or "Domain" not in data[0]:
        raise ValueError("Неожиданный формат списка утечек HIBP")
    slim = [{k: item.get(k) for k in KEEP_FIELDS} for item in data if not item.get("IsFabricated")]
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(slim, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(path)
    default_index.cache_clear()
    return len(slim)
