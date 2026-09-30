"""Командная строка Vanish.

    python -m vanish start              — проанализировать архив из data/ (если ещё не) и открыть интерфейс
    python -m vanish analyze [файлы]    — (повторно) импортировать mbox, решения сохраняются
    python -m vanish serve              — только открыть интерфейс
    python -m vanish update-jdm         — обновить базу JustDeleteMe
    python -m vanish update-breaches    — обновить список утечек Have I Been Pwned
    python -m vanish demo               — демо на синтетических письмах
    python -m vanish build              — пересобрать интерфейс (нужен Node.js)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from . import DEFAULT_DB, PROJECT_DIR, STATIC_DIR, breaches, jdm
from .analyzer import ConsoleProgress, ImportReport, analyze
from .signals import LIKELY, NEWSLETTER, PERSONAL, SURE
from .store import connect, get_meta, set_meta

DATA_DIR = PROJECT_DIR / "data"
DEMO_DB = PROJECT_DIR / "state" / "demo.db"
DEMO_MBOX = PROJECT_DIR / "state" / "demo.mbox"


def _setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def _find_mboxes() -> list[Path]:
    if not DATA_DIR.exists():
        return []
    return sorted(p for p in DATA_DIR.rglob("*.mbox") if p.is_file())


def _print_report(r: ImportReport) -> None:
    print()
    print(f"  Обработано писем:        {r.total:>8}")
    print(f"  Письма от сервисов:      {r.service_messages:>8}  (новых в базе: {r.new_messages})")
    print(f"  Личная переписка:        {r.personal:>8}  (не считается сервисами)")
    print(f"  Мои отправленные:        {r.sent:>8}")
    print(f"  Спам/чаты/черновики:     {r.spam:>8}  (пропущено)")
    print()
    print(f"  Найдено доменов:         {r.domains:>8}")
    print(f"    точно аккаунт:         {r.confidence.get(SURE, 0):>8}")
    print(f"    вероятно:              {r.confidence.get(LIKELY, 0):>8}")
    print(f"    только рассылка:       {r.confidence.get(NEWSLETTER, 0):>8}")
    print(f"    переписка (скрыто):    {r.confidence.get(PERSONAL, 0):>8}")
    print(f"  Есть в JustDeleteMe:     {r.jdm_matched:>8}")
    print(f"  Риск высокий:            {r.risk.get('high', 0):>8}")
    print(f"    средний:               {r.risk.get('medium', 0):>8}")
    print(f"    низкий:                {r.risk.get('low', 0):>8}")
    print(f"  Были в утечках (HIBP):   {r.breached:>8}")
    print(f"  Время: {r.seconds:.1f} с")
    print()


def _archive_hint() -> None:
    """Архив Takeout скачивается как .zip/.tgz — mbox внутри нужно распаковать."""
    if not DATA_DIR.exists():
        return
    packed = [p for p in DATA_DIR.rglob("*") if p.is_file() and p.name.lower().endswith((".zip", ".tgz", ".tar.gz"))]
    if packed:
        print(f"  В {DATA_DIR} лежит нераспакованный архив ({packed[0].name}) — распакуйте его, нужен файл .mbox.")


def cmd_analyze(args) -> int:
    files = [Path(f) for f in args.files] or _find_mboxes()
    if not files:
        print(f"Не найдено .mbox-файлов. Положите архив в {DATA_DIR} или укажите путь.")
        _archive_hint()
        return 1
    conn = connect(Path(args.db))
    try:
        for path in files:
            if not path.exists():
                print(f"Файл не найден: {path}")
                return 1
            size_mb = path.stat().st_size / 1_048_576
            size = f"{size_mb:,.0f}".replace(",", " ")
            print(f"\n  Анализ {path.name} ({size} МБ) — читаются только заголовки…")
            report = analyze(conn, path, my_addresses=args.me, progress=ConsoleProgress())
            _print_report(report)
    finally:
        conn.close()
    print("  Готово. Решения и прогресс сохранены — запустите: python -m vanish serve", flush=True)
    return 0


def cmd_serve(args) -> int:
    from .server import serve

    if not (STATIC_DIR / "index.html").exists():
        print("Интерфейс не собран. Выполните: python -m vanish build")
        return 1
    serve(Path(args.db), port=args.port, open_browser=not args.no_browser)
    return 0


def cmd_start(args) -> int:
    db = Path(args.db)
    conn = connect(db)
    imported = get_meta(conn, "last_import")
    conn.close()
    if not imported:
        if not _find_mboxes():
            print(f"\n  Архив не найден. Положите mbox из Google Takeout в {DATA_DIR}")
            _archive_hint()
            print("  или посмотрите демо: python -m vanish demo\n")
            return 1
        args.files = []
        if cmd_analyze(args):
            return 1
    return cmd_serve(args)


def cmd_update_jdm(args) -> int:
    print("  Скачиваю базу JustDeleteMe (github.com/jdm-contrib/jdm)…")
    try:
        n = jdm.update()
    except Exception as e:  # noqa: BLE001 — показать понятную ошибку
        print(f"  Не удалось обновить: {e}")
        return 1
    print(f"  Готово: {n} сервисов. Файл: {jdm.JDM_PATH}")
    return 0


def cmd_update_breaches(args) -> int:
    print("  Скачиваю публичный список утечек Have I Been Pwned (без ключа и без ваших данных)…")
    try:
        n = breaches.update()
    except Exception as e:  # noqa: BLE001 — показать понятную ошибку
        print(f"  Не удалось обновить: {e}")
        return 1
    print(f"  Готово: {n} утечек. Файл: {breaches.BREACHES_PATH}")
    return 0


def cmd_demo(args) -> int:
    from .synthetic import write_mbox

    if DEMO_DB.exists() and args.reset:
        for suffix in ("", "-wal", "-shm"):
            Path(str(DEMO_DB) + suffix).unlink(missing_ok=True)
    conn = connect(DEMO_DB)
    if not get_meta(conn, "last_import"):
        n = write_mbox(DEMO_MBOX)
        print(f"\n  Демо: {n} синтетических писем → {DEMO_MBOX.name}")
        report = analyze(conn, DEMO_MBOX, progress=ConsoleProgress())
        set_meta(conn, "demo", "1")
        conn.commit()
        _print_report(report)
    conn.close()
    args.db = str(DEMO_DB)
    return cmd_serve(args)


def cmd_build(args) -> int:
    web = PROJECT_DIR / "web"
    npm = shutil.which("npm")
    if not npm:
        print("Нужен Node.js (npm): https://nodejs.org")
        return 1
    subprocess.run([npm, "install"], cwd=web, check=True)
    subprocess.run([npm, "run", "build"], cwd=web, check=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    _setup_console()
    parser = argparse.ArgumentParser(prog="python -m vanish", description="Vanish — разбор цифрового следа")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="файл базы (по умолчанию state/vanish.db)")
    sub = parser.add_subparsers(dest="command")

    def add_serve_opts(p):
        p.add_argument("--port", type=int, default=8765)
        p.add_argument("--no-browser", action="store_true", help="не открывать браузер")

    p = sub.add_parser("analyze", help="импортировать mbox (можно повторно)")
    p.add_argument("files", nargs="*", help="mbox-файлы (по умолчанию все *.mbox в data/)")
    p.add_argument("--me", action="append", default=[], help="мой адрес (можно несколько раз)")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("serve", help="запустить интерфейс")
    add_serve_opts(p)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("start", help="анализ (если ещё не было) + интерфейс")
    p.add_argument("--me", action="append", default=[])
    add_serve_opts(p)
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("update-jdm", help="обновить базу JustDeleteMe")
    p.set_defaults(func=cmd_update_jdm)

    p = sub.add_parser("update-breaches", help="обновить список утечек Have I Been Pwned")
    p.set_defaults(func=cmd_update_breaches)

    p = sub.add_parser("demo", help="демо на синтетических данных")
    p.add_argument("--reset", action="store_true", help="начать демо заново")
    add_serve_opts(p)
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("build", help="собрать интерфейс (Node.js)")
    p.set_defaults(func=cmd_build)

    # Без подкоманды — это «start»: python -m vanish --no-browser --port 9000
    argv = list(sys.argv[1:] if argv is None else argv)
    if not any(a in sub.choices for a in argv) and not {"-h", "--help"} & set(argv):
        i = 0
        while i < len(argv) and argv[i].startswith("--db"):
            i += 2 if argv[i] == "--db" else 1
        argv[i:i] = ["start"]
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        # Незавершённый импорт не сохраняется: база остаётся как до запуска, его можно просто повторить.
        print("\n  Прервано. Незавершённый импорт не сохранён — запустите команду ещё раз.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
