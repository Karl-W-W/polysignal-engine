#!/usr/bin/env bash
# polysignal-seats.sh
# -------------------
# Opens six Ghostty windows on macOS. Each window SSHes to the DGX and
# runs one seat from lab/SEATS.md (Fire / Scanner / Truth Board / Brain /
# Loop / Vitals). Mac-side only — meant to be bound to a macOS keyboard
# shortcut (see INSTALL.md).
#
# Works with macOS default /bin/bash (3.2+). No bashisms past 3.2.

set -e

# ── SSH target ───────────────────────────────────────────────────────────────
# Default is the LAN alias `spark` (192.168.2.144). When Karl is off home
# network (hotspot, travel), the LAN IP won't route — change SSH_HOST to
# "dgx-remote" (Cloudflare Tunnel path) in that case.
SSH_HOST="spark"

# ── Seat commands ────────────────────────────────────────────────────────────
# Each SEAT_* string is the command that runs on the DGX inside the window.
# Keep them single-line so ssh -t quoting stays sane. If you need something
# bigger, write a script under lab/ghostty-shortcut/ and call it from here.

SEAT1="cd /opt/loop && watch -n 10 'cat lab/.watchdog-alerts 2>/dev/null; echo ---; tail -5 lab/.events.jsonl 2>/dev/null'"

SEAT2="journalctl --user -u polysignal-scanner.service -f --since '20 min ago'"

# TODO(session-42): replace the fallback once lab/truth_board.py is written.
# Intended final form: cd /opt/loop && watch -n 60 .venv/bin/python3 lab/truth_board.py
SEAT3="cd /opt/loop && watch -n 60 'if [ -f lab/truth_board.py ]; then .venv/bin/python3 lab/truth_board.py; else echo \"truth board — write lab/truth_board.py\"; fi'"

SEAT4="cd /opt/loop && \${EDITOR:-nano} brain/memory.md"

SEAT5="watch -n 60 'head -c 1500 /home/cube/.openclaw/agents/main/sessions/sessions.json 2>/dev/null; echo'"

SEAT6="watch -n 10 'nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used --format=csv,noheader; echo ---; df -h / /opt/loop | tail -2; echo ---; systemctl --user is-active polysignal-scanner.service openclaw-gateway.service'"

# ── Launcher ─────────────────────────────────────────────────────────────────
open_seat() {
  local title="$1"
  local cmd="$2"
  open -na Ghostty --args --title="polysignal/${title}" --command="ssh ${SSH_HOST} -t \"${cmd}\""
}

open_seat "1-fire"    "$SEAT1"; sleep 0.4
open_seat "2-scanner" "$SEAT2"; sleep 0.4
open_seat "3-truth"   "$SEAT3"; sleep 0.4
open_seat "4-brain"   "$SEAT4"; sleep 0.4
open_seat "5-loop"    "$SEAT5"; sleep 0.4
open_seat "6-vitals"  "$SEAT6"

echo "Opened six Ghostty windows on ${SSH_HOST}."
echo
echo "If a window exits immediately with 'Operation timed out' or"
echo "'No route to host': you're off home network. Edit this script,"
echo "set SSH_HOST=\"dgx-remote\", save, and run again."
