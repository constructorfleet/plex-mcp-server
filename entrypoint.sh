#!/bin/bash
export PATH="$PATH;/usr/loca/bin"

if [[ -z "$@" ]]; then
  exec "$@"
  exit 0
fi

if [[ -z "$PLEX_URL" ]]; then
  echo "ENV Missing: PLEX_URL"
  exit 1
fi

if [[ -z "$PLEX_TOKEN" ]]; then
  echo "ENV Missing: PLEX_TOKEN"
  exit 2
fi

if [[ -z "$PLEX_USERNAME" ]]; then
  echo "ENV Missing: PLEX_USERNAME"
  exit 3
fi

export PLEX_URL=$PLEX_URL
export PLEX_TOKEN=$PLEX_TOKEN
export PLEX_USERNAME=$PLEX_USERNAME

server_cmd=(uvx mcpo --host "$HOST" --port "$MCPO_PORT" --)

# Build the actual inner command string
inner_cmd=("uv" "run" "plex_mcp_server.py")

# Build transport flags
transport_args=()
if [[ "${SSE}" =~ ^(1|true|yes)$ ]]; then
    if [[ "${STDIO}" =~ ^(1|true|yes)$ ]]; then
        echo "TRANSPORT: Only one may be active"
        exit 4
    fi
    PORT="${PORT:-3000}"
    HOST="${HOST:-0.0.0.0}"
    transport_args+=(--transport sse --port "$PORT" --host "$HOST")
elif [[ "${STDIO}" =~ ^(1|true|yes)$ ]]; then
    transport_args+=(--transport stdio)
fi

if [[ "${DEBUG}" =~ ^(1|true|yes)$ ]]; then
    transport_args+=(--debug)
fi

# Combine everything into one final command
exec "${server_cmd[@]}" "${inner_cmd[@]}" "${transport_args[@]}"
