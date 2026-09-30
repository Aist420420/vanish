"""Потоковое чтение mbox: только заголовки, без загрузки файла в память.

Файл отображается в память через mmap: поиск разделителей писем идёт на
уровне C, а в Python попадают только блоки заголовков. Тела писем никогда
не декодируются и не сохраняются.
"""

from __future__ import annotations

import mmap
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import urlsplit

# «From <что-угодно> Wed Mar 13 12:00:00 ...» — строка-разделитель mbox.
SEPARATOR_RE = re.compile(
    rb"^From \S+\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\w{3}\s+\d{1,2}\s+\d{1,2}:\d{2}"
)
MAX_HEADER_BYTES = 256 * 1024
MIN_DATE = datetime(1990, 1, 1, tzinfo=timezone.utc)
# Пустая строка между заголовками и телом: \n\n или \n\r\n.
HEADER_END_RE = re.compile(rb"\n\r?\n")
WANTED_HEADERS = {
    "from",
    "sender",
    "subject",
    "date",
    "list-unsubscribe",
    "list-id",
    "to",
    "delivered-to",
    "message-id",
    "x-gmail-labels",
}


@dataclass
class MessageHeaders:
    from_addr: str = ""
    from_name: str = ""
    subject: str = ""
    date: datetime | None = None
    list_unsubscribe: bool = False
    unsubscribe_url: str = ""  # первая https-ссылка из List-Unsubscribe (mailto: не берём)
    list_id: str = ""
    to_raw: str = ""  # разбирается только по запросу: адресаты нужны лишь для моих отправленных
    delivered_to: str = ""
    message_id: str = ""
    labels: list[str] = field(default_factory=list)

    @property
    def domain(self) -> str:
        return self.from_addr.rpartition("@")[2]

    @property
    def to_addrs(self) -> list[str]:
        return [a.lower() for _, a in getaddresses([self.to_raw]) if "@" in a]


ProgressFn = Callable[[int, int, int], None]


def iter_header_blocks(path: Path, progress: ProgressFn | None = None) -> Iterator[bytes]:
    """Отдаёт сырой блок заголовков каждого письма (переводы строк приведены к \\n).

    Переводы строк могут различаться даже внутри одного файла (CRLF и LF вперемешку),
    поэтому разделители и конец заголовков ищутся без предположений о формате.
    """
    size = path.stat().st_size
    if size == 0:
        return
    with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        # Первое письмо: файл должен начинаться с разделителя.
        pos = 0 if SEPARATOR_RE.match(mm[:200]) else _find_separator(mm, 0)
        count = 0
        next_report = 0
        while pos is not None:
            line_end = mm.find(b"\n", pos)
            if line_end == -1:
                break
            start = line_end + 1
            nxt = _find_separator(mm, start)
            limit = min(start + MAX_HEADER_BYTES, size if nxt is None else nxt)
            if mm[start : start + 1] == b"\n" or mm[start : start + 2] == b"\r\n":
                end = start  # письмо без заголовков
            else:
                m = HEADER_END_RE.search(mm, start, limit)
                end = m.start() + 1 if m else limit
            block = mm[start:end]
            if b"\r" in block:
                block = block.replace(b"\r\n", b"\n")
            count += 1
            yield block

            pos = nxt
            if progress and (pos is None or pos >= next_report):
                progress(size if pos is None else pos, size, count)
                next_report = (pos or size) + size // 200 + 1


def _find_separator(mm: mmap.mmap, start: int) -> int | None:
    while True:
        i = mm.find(b"\nFrom ", start)
        if i == -1:
            return None
        if SEPARATOR_RE.match(mm[i + 1 : i + 201]):
            return i + 1
        start = i + 1


def _decode_bytes(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # Заголовки без MIME-кодирования в старых русских письмах почти всегда в windows-1251.
        return raw.decode("cp1251", errors="replace")


def decode_mime(value: str) -> str:
    """Декодирует =?utf-8?B?...?= и подобные encoded-words."""
    if "=?" not in value:
        return " ".join(value.split())
    try:
        text = str(make_header(decode_header(value)))
    except Exception:
        text = value
    return " ".join(text.split())


def split_headers(block: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    current = None
    for raw_line in block.split(b"\n"):
        if not raw_line:
            continue
        if raw_line[:1] in (b" ", b"\t"):
            if current is not None:
                headers[current] += " " + _decode_bytes(raw_line).strip()
            continue
        name, sep, value = raw_line.partition(b":")
        if not sep:
            current = None
            continue
        key = name.decode("latin-1").strip().lower()
        if key in WANTED_HEADERS and key not in headers:
            headers[key] = _decode_bytes(value).strip()
            current = key
        else:
            current = None
    return headers


MAX_URL_LENGTH = 2048
_URL_BAD_CHARS = re.compile(r"[\s\"'<>\\^`{|}\x00-\x1f\x7f]")


def unsubscribe_https_url(value: str) -> str:
    """Первая https-ссылка из List-Unsubscribe: «<mailto:…>, <https://…>» → https://…

    mailto:, http: и всё подозрительное (пробелы, кавычки, логин в адресе) отбрасываются.
    """
    if not value:
        return ""
    candidates = re.findall(r"<([^<>]*)>", value) or value.split(",")
    for raw in candidates:
        url = "".join(raw.split())  # свёрнутые длинные ссылки склеиваются обратно
        if not url.lower().startswith("https://") or len(url) > MAX_URL_LENGTH or _URL_BAD_CHARS.search(url):
            continue
        parts = urlsplit(url)
        if parts.hostname and "." in parts.hostname and "@" not in parts.netloc:
            return url
    return ""


def parse_headers(block: bytes) -> MessageHeaders:
    h = split_headers(block)
    msg = MessageHeaders()

    from_raw = h.get("from") or h.get("sender") or ""
    name, addr = parseaddr(from_raw)
    if "@" not in addr:
        name, addr = parseaddr(decode_mime(from_raw))
    msg.from_addr = addr.strip().lower()
    msg.from_name = decode_mime(name)
    msg.subject = decode_mime(h.get("subject", ""))

    date_raw = h.get("date")
    if date_raw:
        try:
            dt = parsedate_to_datetime(date_raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            # Заведомо ложные даты (1970 год, далёкое будущее у спамеров) портят «с какого года».
            if MIN_DATE <= dt <= datetime.now(timezone.utc) + timedelta(days=2):
                msg.date = dt
        except (TypeError, ValueError, IndexError, OverflowError):
            msg.date = None

    msg.list_unsubscribe = bool(h.get("list-unsubscribe"))
    msg.unsubscribe_url = unsubscribe_https_url(h.get("list-unsubscribe", ""))
    msg.list_id = h.get("list-id", "")
    msg.to_raw = h.get("to", "")
    msg.delivered_to = parseaddr(h.get("delivered-to", ""))[1].lower()
    msg.message_id = h.get("message-id", "").strip()
    # Ярлыки декодируются целиком: одно encoded-word может содержать несколько ярлыков через запятую.
    labels = decode_mime(h.get("x-gmail-labels", ""))
    msg.labels = [x.strip().strip('"').strip() for x in labels.split(",") if x.strip()]
    return msg


def iter_messages(path: Path, progress: ProgressFn | None = None) -> Iterator[MessageHeaders]:
    for block in iter_header_blocks(path, progress):
        yield parse_headers(block)
