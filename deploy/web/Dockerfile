ARG PYTHON_BASE=python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
ARG POSTGRES_BASE=postgres:16.15-bookworm@sha256:efedf3595f1d6f415c08568ba171029bf54052e754cc9f030e3f2412b21f3d67
ARG CADDY_BASE=caddy:2.11.4-alpine@sha256:6aeddd44c3078b0f9a35206472a11420648a79c184603ef95957d0a20044cb2b
ARG RCLONE_VERSION=1.75.2
ARG RCLONE_SHA256=349ac8fba6ff65d6247043f1750cdcb518ec5d500ef91463a10d37c0ccdf3702

FROM ${PYTHON_BASE} AS python-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /opt/facediff
RUN groupadd --gid 10001 facediff \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin facediff \
    && install -d -o 10001 -g 10001 /var/lib/facediff/references \
       /var/lib/facediff/exclusions /var/lib/facediff/backup/encrypted \
       /var/lib/facediff/backup-state

FROM python-base AS web-base
COPY requirements-web.txt ./requirements-web.txt
RUN python -m pip install --no-cache-dir -r requirements-web.txt
RUN python -m pip check
COPY src ./src
COPY scripts ./scripts
COPY models/face_landmarker.task ./src/presentation/web/static/models/face_landmarker.task
COPY deploy/web/entrypoint.py ./entrypoint.py
ENTRYPOINT ["python", "/opt/facediff/entrypoint.py"]

FROM web-base AS app
USER 10001:10001
EXPOSE 8000/tcp
CMD ["uvicorn", "src.web_main:create_web_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM python-base AS worker
RUN apt-get update \
    && apt-get install --no-install-recommends -y \
       libgl1 libglib2.0-0 libxcb1 libxkbcommon0 libxkbcommon-x11-0 \
       libxcb-cursor0 libxcb-xinerama0 libegl1 libgles2 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-web.txt requirements-landmarks-linux.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt -r requirements-web.txt \
    && python -m venv /opt/facediff/landmarks-venv \
    && /opt/facediff/landmarks-venv/bin/python -m pip install --no-cache-dir \
       -r requirements-landmarks-linux.txt \
    && python -m pip check \
    && /opt/facediff/landmarks-venv/bin/python -m pip check
COPY src ./src
COPY scripts ./scripts
COPY deploy/web/entrypoint.py ./entrypoint.py
ENV DEEPFACE_HOME=/var/lib/facediff/models/home
USER 10001:10001
ENTRYPOINT ["python", "/opt/facediff/entrypoint.py"]
CMD ["sh", "-ec", "python -m scripts.web_worker_preflight && exec python -m src.face_worker_main"]

FROM web-base AS migrate
RUN python -m pip install --no-cache-dir alembic==1.19.2 \
    && python -m pip check
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
USER 10001:10001
CMD ["alembic", "upgrade", "head"]

FROM python-base AS rclone-download
ARG RCLONE_VERSION
ARG RCLONE_SHA256
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/* \
    && curl --fail --location --silent --show-error \
       "https://downloads.rclone.org/v${RCLONE_VERSION}/rclone-v${RCLONE_VERSION}-linux-amd64.zip" \
       --output /tmp/rclone.zip \
    && echo "${RCLONE_SHA256}  /tmp/rclone.zip" | sha256sum --check --status \
    && unzip -q /tmp/rclone.zip -d /tmp/rclone \
    && install -o root -g root -m 0755 \
       "/tmp/rclone/rclone-v${RCLONE_VERSION}-linux-amd64/rclone" /usr/local/bin/rclone \
    && rm -rf /tmp/rclone /tmp/rclone.zip

FROM ${POSTGRES_BASE} AS postgres-client-tools

FROM web-base AS backup
COPY --from=rclone-download /usr/local/bin/rclone /usr/local/bin/rclone
COPY --from=postgres-client-tools /usr/local/share/keyrings/postgres.gpg.asc \
    /usr/local/share/keyrings/postgres.gpg.asc
RUN echo "deb [signed-by=/usr/local/share/keyrings/postgres.gpg.asc] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main 16" \
       > /etc/apt/sources.list.d/postgresql-pgdg.list \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
       postgresql-client-16=16.15-1.pgdg12+2 \
    && rm -rf /var/lib/apt/lists/* /etc/apt/sources.list.d/postgresql-pgdg.list
USER 10001:10001
CMD ["python", "-m", "scripts.web_backup", "--mode", "diario"]

FROM ${POSTGRES_BASE} AS postgres
COPY --chmod=0755 deploy/web/postgres-entrypoint.sh /usr/local/bin/facediff-postgres-entrypoint
COPY --chmod=0755 deploy/web/postgres-init/001-web-roles.sh /docker-entrypoint-initdb.d/001-web-roles.sh
ENTRYPOINT ["/usr/local/bin/facediff-postgres-entrypoint"]
CMD ["postgres"]

FROM ${CADDY_BASE} AS caddy
RUN setcap -r /usr/bin/caddy \
    && addgroup -S -g 10001 facediff \
    && adduser -S -D -H -u 10001 -G facediff facediff \
    && mkdir -p /data /config \
    && chown -R 10001:10001 /data /config
USER 10001:10001
EXPOSE 8080/tcp 8443/tcp
