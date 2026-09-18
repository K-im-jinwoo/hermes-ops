FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app

RUN groupadd --gid 10001 hermes \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin hermes \
    && mkdir -p /var/lib/hermes/inbox_queue /var/lib/hermes/state \
    && chmod 0755 /app/deploy/entrypoint.sh \
    && chown -R hermes:hermes /app /var/lib/hermes

USER hermes:hermes
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
