#!/usr/bin/env bash
# Собирает снимок инцидента из stream monitor + состояние FSM в один zip.
# Запускать на объекте (по AnyDesk), когда РШР не создаётся / дашборд молчит.
#
# Usage:
#   ./collect_incident.sh [BASE_URL]
#
# BASE_URL по умолчанию http://127.0.0.1:8000 (подставь свой host:port, как в nginx).

set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
API="${BASE_URL%/}/api/v1"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="incident_${TS}"

mkdir -p "${OUT}"

echo "Сбор инцидента из ${API} -> ${OUT}/"

# bundle: события pipeline + stats + groups + снимок FSM (одним файлом)
curl -fsS "${API}/stream-monitor/export?mode=incident&format=json" -o "${OUT}/incident.json" \
  || echo "WARN: не удалось получить incident bundle"

# полный pipeline отдельно (на случай если bundle обрезан)
curl -fsS "${API}/stream-monitor/export?mode=pipeline&format=jsonl" -o "${OUT}/pipeline.jsonl" \
  || echo "WARN: не удалось получить pipeline export"

# текущее состояние FSM (на момент сбора, может отличаться от bundle)
curl -fsS "${API}/sensor/debug/state" -o "${OUT}/sensor_state.json" \
  || echo "WARN: не удалось получить sensor debug state"

# статистика монитора
curl -fsS "${API}/stream-monitor/stats" -o "${OUT}/stats.json" \
  || echo "WARN: не удалось получить stats"

if command -v zip >/dev/null 2>&1; then
  zip -rq "${OUT}.zip" "${OUT}"
  echo "Готово: ${OUT}.zip"
else
  echo "Готово: каталог ${OUT}/ (zip не установлен — заархивируй вручную)"
fi
