#!/bin/bash
export PATH="$PATH;/usr/loca/bin"

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

PORT="${PORT:-3000}"
HOST="${HOST:-0.0.0.0}"

export PLEX_URL=$PLEX_URL
export PLEX_TOKEN=$PLEX_TOKEN
export PLEX_USERNAME=$PLEX_USERNAME

server_cmd=''
shopt -s nocasematch
if [[ "${DEBUG}" =~ ^(1|true|yes)$ ]]; then
    server_cmd="${server_cmd} --debug"
fi

if [[ "${SSE}" =~ ^(1|true|yes)$ ]]; then
    server_cmd="${server_cmd} --transport sse"
fi
shopt -u nocasematch
server_cmd="$server_cmd --port $PORT --host $HOST"


# Run the main container command
args=("$@")
args+=($server_cmd)
exec "${args[@]}"
