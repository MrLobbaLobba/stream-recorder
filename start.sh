#!/bin/bash

# Usage: ./start.sh <username> [fansly|joystick]
if [ -z "$1" ]; then
  echo "[error] usage: ./start.sh {username} [fansly|joystick]"
  exit 1
fi

# Get parameters
username=$1
platform=${2:-fansly}

if [ "$platform" == "joystick" ]; then
  script="joystick-recorder.py"
  session_name="$username-joystick"
else
  script="fansly-recorder.py"
  session_name="$username-fansly"
fi

# Start a new tmux session and run the script
tmux new-session -d -s "$session_name"
tmux send-keys "python3 $script $username" C-m
echo "[info] Started $platform recorder for $username in tmux session $session_name"
