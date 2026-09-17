#!/bin/sh
# Usage: ./start.sh <username> [fansly|joystick]
if [ -z "$1" ]; then
  echo "[error] Uso: ./start.sh {username} [fansly|joystick]"
  exit 1
fi

# Get parameters
username=$1
platform=${2:-fansly}

# Find python binary (.venv or system)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
  PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"
elif [ -f "$SCRIPT_DIR/venv/bin/python3" ]; then
  PYTHON_BIN="$SCRIPT_DIR/venv/bin/python3"
else
  PYTHON_BIN="python3"
fi

if [ "$platform" = "joystick" ]; then
  script="$SCRIPT_DIR/joystick-recorder.py"
  session_name="$username-joystick"
else
  script="$SCRIPT_DIR/fansly-recorder.py"
  session_name="$username-fansly"
fi

# Check if tmux is installed
if command -v tmux >/dev/null 2>&1; then
  tmux new-session -d -s "$session_name" "$PYTHON_BIN -u $script $username"
  echo "[info] Iniciado $platform recorder para $username en sesión tmux: $session_name"
  echo "[info] Para ver el progreso: tmux attach -t $session_name"
else
  echo "[warning] 'tmux' no está instalado en el sistema."
  echo "[info] Para instalar tmux: sudo apt install tmux -y"
  echo "[info] Ejecutando en segundo plano con nohup..."
  nohup "$PYTHON_BIN" -u "$script" "$username" > "$SCRIPT_DIR/${session_name}.log" 2>&1 &
  echo "[info] Proceso iniciado con PID $! (Logs en tiempo real en: ${session_name}.log)"
fi
