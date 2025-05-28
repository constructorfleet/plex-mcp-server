FROM python:3.12

ENV PLEX_URL=""
ENV PLEX_TOKEN=""
ENV PLEX_USERNAME=""
ENV DEBUG="no"
ENV PORT=3000
ENV HOST=0.0.0.0
ENV SSE=true

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

ENTRYPOINT ["./entrypoint.sh"]

CMD ["/usr/local/bin/python3", "plex_mcp_server.py"]