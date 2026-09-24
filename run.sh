#!/usr/bin/env sh
# Запуск игры. Нужен только Python 3.11+, зависимостей нет.
set -e
PORT="${1:-8000}"
echo "Депеша: http://localhost:$PORT"
exec python3 api/server.py "$PORT"
