FROM python:3.12

ENV PLEX_URL
ENV PLEX_TOKEN
ENV PLEX_USERNAME
ENV DEBUG
ENV PORT=3000
ENV HOST=0.0.0.0
ENV SSE=true

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

ENTRYPOINT /app/entrypoint.sh

CMD ['python3', 'plex_mcp_server.py']



