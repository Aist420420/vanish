#!/bin/bash
# Vanish: двойной щелчок в Finder — анализ архива из data/ (при первом запуске) и интерфейс в браузере.
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null 2>&1; then
    echo "Нужен Python 3.10+: https://www.python.org/downloads/"
    read -r -p "Нажмите Enter, чтобы закрыть окно"
    exit 1
fi
python3 -m vanish "$@"
