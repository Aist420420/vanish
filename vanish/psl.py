"""Определение корневого домена по Public Suffix List (офлайн).

Используется только ICANN-часть списка: приватные суффиксы (blogspot.com,
github.io и т.п.) для адресов отправителей писем только мешают.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from . import RESOURCES_DIR

PSL_PATH = RESOURCES_DIR / "public_suffix_list.dat"


class PublicSuffixList:
    def __init__(self, path: Path = PSL_PATH):
        self.rules: set[str] = set()
        self.wildcards: set[str] = set()
        self.exceptions: set[str] = set()
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if line.startswith("// ===END ICANN DOMAINS==="):
                    break
                if not line or line.startswith("//"):
                    continue
                rule = line.split()[0].lower()
                rule = _to_ascii(rule)
                if rule.startswith("!"):
                    self.exceptions.add(rule[1:])
                elif rule.startswith("*."):
                    self.wildcards.add(rule[2:])
                else:
                    self.rules.add(rule)

    def public_suffix(self, host: str) -> str:
        labels = host.split(".")
        # Ищем самое длинное совпадающее правило.
        for i in range(len(labels)):
            candidate = ".".join(labels[i:])
            if candidate in self.exceptions:
                return ".".join(labels[i + 1 :])
            if candidate in self.rules:
                return candidate
            if i + 1 < len(labels) and ".".join(labels[i + 1 :]) in self.wildcards:
                return candidate
        # Неизвестная зона: по умолчанию суффикс — последняя метка.
        return labels[-1]

    def root_domain(self, host: str) -> str:
        host = normalize_host(host)
        if not host:
            return ""
        suffix = self.public_suffix(host)
        if host == suffix:
            return host
        rest = host[: -len(suffix) - 1]
        return rest.rsplit(".", 1)[-1] + "." + suffix


def _to_ascii(label: str) -> str:
    try:
        return label.encode("idna").decode("ascii")
    except UnicodeError:
        return label


def normalize_host(host: str) -> str:
    host = (host or "").strip().strip(".").lower()
    host = host.strip("<>[]() \"'")
    if not host or " " in host:
        return ""
    if not host.isascii():
        host = ".".join(_to_ascii(part) for part in host.split("."))
    return host


@lru_cache(maxsize=1)
def default_psl() -> PublicSuffixList:
    return PublicSuffixList()


def root_domain(host: str) -> str:
    return default_psl().root_domain(host)
