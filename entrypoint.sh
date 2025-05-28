#!/bin/sh

if [[ -n "${PLEX_URL}" ]]; then
  echo "ENV Missing: PLEX_URL";
  exit -1
fi

if [[ -n "${PLEX_TOKEN}" ]]; then
  echo "ENV Missing: PLEX_TOKEN";
  exit -2
fi

if [[ -n "${PLEX_USERNAME}" ]]; then
  echo "ENV Missing: PLEX_USERNAME";
  exit -3
fi

PORT="${PORT:-3000}"
HOST="${HOST:-0.0.0.0}"

export $PLEX_URL
export $PLEX_TOKEN
export $PLEX_USERNAME

server_cmd=''
shopt -s nocasematch
if [[ "${DEBUG}" =~ ^(1|true|yes)$ ]]; then
    server_cmd="${server_cmd}  --debug";
fi

if [[ "${SSE}" =~ ^(1|true|yes)$ ]]; then
    server_cmd="${server_cmd} --transport sse";
fi
shopt -u nocasematch
server_cmd="${server_cmd} --port $PORT --host $HOST"


# Run the main container command
echo "$@ $server_cmd"
