#!/bin/bash
# loop_chat.sh — operator REPL for Loop, via the OpenClaw gateway.
# One line = one agent turn. Reply is extracted from --json output.
# Session is pinned for the life of the script so multi-turn context is shared.
# Overrides: LOOP_CHAT_AGENT (default: main), LOOP_CHAT_SESSION (default: timestamped).
set -u
AGENT="${LOOP_CHAT_AGENT:-main}"
SESSION_ID="${LOOP_CHAT_SESSION:-loop-chat-$(date +%s)}"
TIMEOUT="${LOOP_CHAT_TIMEOUT:-90}"
echo "=== Loop chat (Ctrl+D to exit) ==="
echo "agent: $AGENT  session: $SESSION_ID  timeout: ${TIMEOUT}s"
while IFS= read -r -p $'\n> ' msg; do
    [[ -z "$msg" ]] && continue
    raw=$(openclaw agent --agent "$AGENT" --session-id "$SESSION_ID" --message "$msg" --json --timeout "$TIMEOUT" 2>&1)
    reply=$(printf '%s' "$raw" | jq -r '.. | objects | select(has("text")) | .text' 2>/dev/null)
    if [[ -n "$reply" ]]; then
        printf '%s\n' "$reply"
    else
        printf '%s\n' "$raw"
    fi
done
echo "bye."
