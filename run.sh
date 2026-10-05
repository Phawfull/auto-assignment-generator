#!/usr/bin/env bash
# Linux launcher. Runs the app inside a nested Xephyr X server because
# java.awt.Robot screenshots are unreliable under XWayland; Xephyr gives
# Java a real X11 screen to capture.
set -euo pipefail

cd "$(dirname "$0")"

SIZE="${XEPHYR_SIZE:-1366x768}"

if ! command -v Xephyr >/dev/null 2>&1; then
    echo "Xephyr is not installed (Arch: xorg-server-xephyr, Debian/Ubuntu: xserver-xephyr)." >&2
    exit 1
fi

n="${XEPHYR_DISPLAY:-2}"
while [ -e "/tmp/.X${n}-lock" ] || [ -e "/tmp/.X11-unix/X${n}" ]; do
    n=$((n + 1))
done
display=":${n}"

Xephyr "$display" -screen "$SIZE" -ac -br -noreset -title "Tutorial Maker ($display)" >/dev/null 2>&1 &
xephyr_pid=$!
trap 'kill "$xephyr_pid" 2>/dev/null || true' EXIT
trap 'exit 130' INT TERM

for _ in $(seq 50); do
    [ -e "/tmp/.X11-unix/X${n}" ] && break
    if ! kill -0 "$xephyr_pid" 2>/dev/null; then
        echo "Xephyr failed to start on $display." >&2
        exit 1
    fi
    sleep 0.1
done

if [ -x .venv/bin/python ]; then
    python=.venv/bin/python
else
    python=python3
fi

DISPLAY="$display" WAYLAND_DISPLAY= "$python" tutorial_maker.py "$@"
