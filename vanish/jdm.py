"""База JustDeleteMe: локальная копия, обновление и сопоставление доменов."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from . import RESOURCES_DIR
from .psl import normalize_host, root_domain

JDM_PATH = RESOURCES_DIR / "jdm_sites.json"
JDM_URL = "https://raw.githubusercontent.com/jdm-contrib/jdm/master/_data/sites.json"

DIFFICULTIES = ("easy", "medium", "hard", "limited", "impossible")


@dataclass(frozen=True)
class JdmEntry:
    name: str
    url: str
    difficulty: str
    notes: str
    email: str
    popular: bool


def _entry_from_json(item: dict) -> JdmEntry:
    difficulty = str(item.get("difficulty", "")).lower()
    if difficulty not in DIFFICULTIES:
        difficulty = ""
    return JdmEntry(
        name=str(item.get("name", "")).strip(),
        url=str(item.get("url_ru") or item.get("url") or "").strip(),
        difficulty=difficulty,
        notes=str(item.get("notes_ru") or item.get("notes") or "").strip(),
        email=str(item.get("email", "")).strip(),
        popular=item.get("meta") == "popular",
    )


@dataclass(frozen=True)
class _Candidate:
    entry: JdmEntry
    listed: bool  # домен указан в поле domains (а не только в URL страницы удаления)
    exact: bool   # хост совпадает с корневым доменом


class JdmIndex:
    def __init__(self, items: list[dict]):
        self.by_host: dict[str, list[_Candidate]] = {}
        self.by_root: dict[str, list[_Candidate]] = {}
        self.count = 0
        for item in items:
            entry = _entry_from_json(item)
            if not entry.name:
                continue
            self.count += 1
            hosts = {normalize_host(d).removeprefix("www.") for d in item.get("domains") or []}
            if not hosts:
                # Хост страницы удаления — только если домены не указаны (часто это чужой хостинг).
                hosts = {normalize_host(urlparse(entry.url).hostname or "").removeprefix("www.")}
            for host in hosts:
                if not host:
                    continue
                root = root_domain(host)
                cand = _Candidate(entry, bool(item.get("domains")), host == root)
                self.by_host.setdefault(host, []).append(cand)
                self.by_root.setdefault(root, []).append(cand)

    def __len__(self) -> int:
        return self.count

    def match(self, domain: str) -> JdmEntry | None:
        domain = normalize_host(domain)
        candidates = self.by_host.get(domain) or self.by_root.get(root_domain(domain))
        if not candidates:
            return None
        label = domain.split(".")[0]

        def score(c: _Candidate) -> tuple:
            name = c.entry.name.lower().replace(" ", "")
            return (not c.listed, not c.exact, label not in name, not c.entry.popular, len(c.entry.name))

        return min(candidates, key=score).entry


def load_items(path: Path = JDM_PATH) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


@lru_cache(maxsize=1)
def default_index() -> JdmIndex:
    return JdmIndex(load_items())


def update(path: Path = JDM_PATH, url: str = JDM_URL, timeout: int = 60) -> int:
    """Скачивает свежую базу JustDeleteMe. Единственный сетевой запрос приложения."""
    req = urllib.request.Request(url, headers={"User-Agent": "Vanish/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("Неожиданный формат базы JustDeleteMe")
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)
    default_index.cache_clear()
    return len(data)
