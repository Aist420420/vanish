"""Анализ mbox: группировка писем по сервисам и слияние с существующей базой."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import breaches, jdm, risk
from .mbox import MessageHeaders, iter_messages
from .psl import normalize_host
from .signals import classify, is_personal_sender, mail_providers, service_domain, subject_signal
from .store import set_meta

SENT_LABELS = {"sent", "отправленные", "sent mail", "sent messages"}
SPAM_LABELS = {"spam", "спам"}
# Черновики — мои незаконченные письма, а не признак отношений с сервисом.
SKIP_LABELS = SPAM_LABELS | {"chat", "чаты", "чат", "draft", "drafts", "черновики", "черновик"}
GOOGLE_ACCESS_RE = re.compile(
    r"(access|доступ|signed in|sign in with|вошли|вход .* аккаунт google|connected|подключ)",
    re.IGNORECASE,
)
# Отбойники почтовых серверов («Delivery Status Notification»): это не сервис, а сбой доставки моего письма.
BOUNCE_LOCAL_RE = re.compile(r"^(?:mailer-daemon|postmaster)$", re.IGNORECASE)
MAX_SAMPLES = 5
BATCH = 5000


@dataclass
class ImportReport:
    total: int = 0
    service_messages: int = 0
    new_messages: int = 0
    personal: int = 0
    own: int = 0
    spam: int = 0
    no_sender: int = 0
    sent: int = 0
    domains: int = 0
    confidence: Counter = field(default_factory=Counter)
    jdm_matched: int = 0
    risk: Counter = field(default_factory=Counter)
    breached: int = 0
    seconds: float = 0.0


def message_hash(msg: MessageHeaders, extra: str = "") -> str:
    if msg.message_id:
        key = msg.message_id.lower()
    else:
        ts = msg.date.isoformat() if msg.date else ""
        key = f"{msg.from_addr}|{ts}|{msg.subject}"
    return hashlib.sha1(f"{key}|{extra}".encode("utf-8", "replace")).hexdigest()


class ConsoleProgress:
    def __init__(self, stream=sys.stdout):
        self.stream = stream
        self.started = time.monotonic()
        self.last = 0.0
        try:
            "█░".encode(stream.encoding or "ascii")
            self.full, self.empty = "█", "░"
        except (UnicodeEncodeError, LookupError):
            self.full, self.empty = "#", "-"

    def __call__(self, pos: int, size: int, count: int) -> None:
        now = time.monotonic()
        if now - self.last < 0.25 and pos < size:
            return
        self.last = now
        pct = 100.0 * pos / size if size else 100.0
        mb = pos / 1_048_576
        speed = mb / max(now - self.started, 1e-6)
        bar = self.full * int(pct / 4) + self.empty * (25 - int(pct / 4))
        self.stream.write(
            f"\r  {bar} {pct:5.1f}%  писем: {count:>8,}  {mb:,.0f} МБ  ({speed:,.0f} МБ/с)".replace(",", " ")
        )
        self.stream.flush()
        if pos >= size:
            self.stream.write("\n")


def analyze(
    conn: sqlite3.Connection,
    mbox_path: Path,
    my_addresses: list[str] | None = None,
    progress=None,
) -> ImportReport:
    started = time.monotonic()
    report = ImportReport()

    mine = {a.lower() for a in (my_addresses or [])}
    mine |= {r["address"] for r in conn.execute("SELECT address FROM my_addresses")}
    providers = mail_providers()

    rows: list[tuple] = []
    samples: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    names: dict[str, Counter] = defaultdict(Counter)
    google_subjects: set[str] = set()
    # Домен → (дата, https-ссылка отписки, отправитель) из самого свежего письма со ссылкой.
    unsub_links: dict[str, tuple[int, str, str]] = {}
    before = conn.execute("SELECT COUNT(*) FROM messages WHERE kind = 0").fetchone()[0]

    def flush() -> None:
        if rows:
            # Повторный импорт того же письма обновляет только признаки из темы
            # (правила могли улучшиться), остальное уже есть в базе.
            conn.executemany(
                "INSERT INTO messages(hash, domain, kind, ts, unsub, signal, sender, topic, purchase) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(hash) DO UPDATE SET signal = excluded.signal, topic = excluded.topic, "
                "purchase = excluded.purchase",
                rows,
            )
            rows.clear()

    for msg in iter_messages(Path(mbox_path), progress):
        report.total += 1
        labels = {label.lower() for label in msg.labels}
        if msg.delivered_to:
            mine.add(msg.delivered_to)
        ts = int(msg.date.timestamp()) if msg.date else None
        if labels & SKIP_LABELS:
            report.spam += 1
            # Письмо сервиса в «Спаме» — признак спамера: запоминаю только факт, сервисом оно не считается.
            host = normalize_host(msg.domain)
            if labels & SPAM_LABELS and host and not is_personal_sender(msg.from_addr, host):
                dom = service_domain(host)
                if dom:
                    rows.append((message_hash(msg, "spam"), dom, 2, ts, 0, 0, msg.from_addr, "", 0))
            continue

        # Мои отправленные письма: запоминаю свой адрес и домены получателей.
        if labels & SENT_LABELS or (msg.from_addr and msg.from_addr in mine):
            report.sent += 1
            if msg.from_addr:
                mine.add(msg.from_addr)
            for addr in msg.to_addrs:
                host = normalize_host(addr.rpartition("@")[2])
                if not host or host in providers or addr in mine:
                    continue
                dom = service_domain(host)
                if dom:
                    rows.append((message_hash(msg, "sent:" + dom), dom, 1, ts, 0, 0, "", "", 0))
            if len(rows) >= BATCH:
                flush()
            continue

        host = normalize_host(msg.domain)
        if not host:
            report.no_sender += 1
            continue
        if BOUNCE_LOCAL_RE.match(msg.from_addr.partition("@")[0]):
            report.no_sender += 1
            continue
        if is_personal_sender(msg.from_addr, host):
            report.personal += 1
            continue
        dom = service_domain(host)
        if not dom:
            report.no_sender += 1
            continue

        signal = subject_signal(msg.subject)
        topic, purchase = risk.subject_topics(msg.subject)
        rows.append((
            message_hash(msg), dom, 0, ts, int(msg.list_unsubscribe), signal, msg.from_addr, topic, int(purchase),
        ))
        report.service_messages += 1

        if msg.unsubscribe_url:
            current = unsub_links.get(dom)
            if current is None or (ts or 0) >= current[0]:
                unsub_links[dom] = (ts or 0, msg.unsubscribe_url, msg.from_addr)

        if msg.subject:
            bucket = samples[dom]
            bucket.append((signal, ts or 0, msg.subject[:200]))
            if len(bucket) > MAX_SAMPLES * 4:
                _trim(bucket)
        if msg.from_name:
            names[dom][msg.from_name[:60]] += 1
        if dom == "google.com" and msg.subject and GOOGLE_ACCESS_RE.search(msg.subject):
            google_subjects.add(msg.subject[:300])

        if len(rows) >= BATCH:
            flush()

    flush()

    # Письма, которые на самом деле отправил я сам, сервисами не считаются.
    conn.executemany("INSERT OR IGNORE INTO my_addresses(address) VALUES (?)", [(a,) for a in mine if a])
    own = conn.execute(
        "DELETE FROM messages WHERE kind IN (0, 2) AND sender IN (SELECT address FROM my_addresses)"
    ).rowcount
    report.own = own
    report.service_messages -= own
    conn.executemany("INSERT OR IGNORE INTO google_access(subject) VALUES (?)", [(s,) for s in google_subjects])

    _merge_display_info(conn, samples, names)
    _merge_unsub_links(conn, {d: v for d, v in unsub_links.items() if v[2] not in mine})
    rebuild_stats(conn)

    report.new_messages = conn.execute("SELECT COUNT(*) FROM messages WHERE kind = 0").fetchone()[0] - before
    for row in conn.execute("SELECT confidence, COUNT(*) AS n FROM domain_stats GROUP BY confidence"):
        report.confidence[row["confidence"]] = row["n"]
    report.domains = sum(report.confidence.values())
    index = jdm.default_index()
    leaks = breaches.default_index()
    for r in conn.execute("SELECT * FROM domain_stats WHERE confidence != 'personal'"):
        if index.match(r["domain"]):
            report.jdm_matched += 1
        first = datetime.fromtimestamp(r["first_ts"], timezone.utc).date().isoformat() if r["first_ts"] else None
        a = risk.assess(r["domain"], topic=r["topic"], purchases=r["purchases"], confidence=r["confidence"],
                        first_day=first, index=leaks)
        report.risk[a["level"]] += 1
        report.breached += a["breached"]
    report.seconds = time.monotonic() - started

    set_meta(conn, "last_import", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    set_meta(conn, "last_import_file", Path(mbox_path).name)
    conn.commit()
    return report


def _trim(bucket: list[tuple[int, int, str]]) -> None:
    """Оставляет лучшие примеры: сначала с сигналом аккаунта, затем самые свежие, без повторов."""
    seen: set[str] = set()
    result = []
    for item in sorted(bucket, key=lambda x: (-x[0], -x[1])):
        key = item[2].lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= MAX_SAMPLES:
            break
    bucket[:] = result


def _merge_unsub_links(conn, links: dict[str, tuple[int, str, str]]) -> None:
    """Ссылка из более свежего письма заменяет старую — в том числе при повторном импорте."""
    conn.executemany(
        "INSERT INTO domain_info(domain, unsub_url, unsub_ts) VALUES (?, ?, ?) "
        "ON CONFLICT(domain) DO UPDATE SET unsub_url = excluded.unsub_url, unsub_ts = excluded.unsub_ts "
        "WHERE excluded.unsub_ts >= domain_info.unsub_ts OR domain_info.unsub_url = ''",
        [(dom, url, ts) for dom, (ts, url, _) in links.items()],
    )


def _merge_display_info(conn, samples, names) -> None:
    for dom in set(samples) | set(names):
        row = conn.execute("SELECT samples, display_name FROM domain_info WHERE domain = ?", (dom,)).fetchone()
        bucket = list(samples.get(dom, []))
        if row:
            bucket += [(s.get("g", 0), s.get("t", 0), s.get("s", "")) for s in json.loads(row["samples"])]
        _trim(bucket)
        data = json.dumps([{"s": s, "t": t, "g": g} for g, t, s in bucket], ensure_ascii=False)
        display = names[dom].most_common(1)[0][0] if names.get(dom) else (row["display_name"] if row else "")
        conn.execute(
            "INSERT INTO domain_info(domain, samples, display_name) VALUES (?, ?, ?) "
            "ON CONFLICT(domain) DO UPDATE SET samples = excluded.samples, display_name = excluded.display_name",
            (dom, data, display),
        )


def rebuild_stats(conn: sqlite3.Connection) -> None:
    """Пересчитывает сводку по доменам из таблицы писем и добавляет новые сервисы."""
    conn.execute("DELETE FROM domain_stats")
    agg = conn.execute(
        """
        SELECT domain,
               SUM(kind = 0)                    AS count,
               MIN(CASE WHEN kind = 0 THEN ts END) AS first_ts,
               MAX(CASE WHEN kind = 0 THEN ts END) AS last_ts,
               SUM(kind = 0 AND unsub = 1)      AS unsub,
               SUM(kind = 0 AND signal = 2)     AS strong,
               SUM(kind = 0 AND signal = 1)     AS weak,
               SUM(kind = 1)                    AS sent_to,
               SUM(kind = 0 AND purchase = 1)   AS purchases,
               SUM(kind = 2)                    AS spam
        FROM messages
        GROUP BY domain
        HAVING SUM(kind = 0) > 0
        """
    ).fetchall()
    topics: dict[str, dict[str, int]] = defaultdict(dict)
    for r in conn.execute(
        "SELECT domain, topic, COUNT(*) AS n FROM messages WHERE kind = 0 AND topic != '' GROUP BY domain, topic"
    ):
        topics[r["domain"]][r["topic"]] = r["n"]
    conn.executemany(
        "INSERT INTO domain_stats(domain, count, first_ts, last_ts, unsub, strong, weak, sent_to, confidence, "
        "purchases, topic, spam) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                r["domain"], r["count"], r["first_ts"], r["last_ts"], r["unsub"],
                r["strong"], r["weak"], r["sent_to"],
                classify(r["strong"], r["weak"], r["sent_to"]),
                r["purchases"], risk.dominant_topic(topics.get(r["domain"], {})), r["spam"],
            )
            for r in agg
        ],
    )
    conn.execute("INSERT OR IGNORE INTO services(domain) SELECT domain FROM domain_stats")
    _mark_google_linked(conn)


def _mark_google_linked(conn: sqlite3.Connection) -> None:
    subjects = [r["subject"].lower() for r in conn.execute("SELECT subject FROM google_access")]
    conn.execute("UPDATE domain_info SET google_linked = 0")
    if not subjects:
        return
    blob = "\n".join(subjects)  # одна строка вместо перебора пар «домен × тема»
    index = jdm.default_index()
    linked = []
    for r in conn.execute("SELECT domain FROM domain_stats WHERE domain != 'google.com'"):
        dom = r["domain"]
        label = dom.split(".")[0]
        entry = index.match(dom)
        needles = [n for n in (label, entry.name.lower() if entry else "") if len(n) >= 4]
        if any(n in blob for n in needles):
            linked.append((dom,))
    conn.executemany(
        "INSERT INTO domain_info(domain, google_linked) VALUES (?, 1) "
        "ON CONFLICT(domain) DO UPDATE SET google_linked = 1",
        linked,
    )
