#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

PORT=8765
URL="http://localhost:$PORT"

echo "=================================================="
echo "⚡ SoGoal Link Recorder Starting..."
echo "📍 Dashboard: $URL"
echo "📁 Save Path: /home/pc-1/Desktop/video recordings"
echo "=================================================="

# Open browser in background after short delay
(sleep 1.2 && xdg-open "$URL" >/dev/null 2>&1 || true) &

# Run server
exec uvicorn server:app --host 0.0.0.0 --port "$PORT" --log-level info
