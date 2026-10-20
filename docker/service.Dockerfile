FROM python:3.11.12-slim-bookworm AS api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements-core.lock ./
RUN pip install --no-cache-dir --no-deps -r requirements-core.lock
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps --no-build-isolation . \
    && groupadd --gid 10001 service && useradd --uid 10001 --gid 10001 --no-create-home service \
    && mkdir /data && chown 10001:10001 /data
COPY config/ /app/config/
USER 10001:10001
CMD ["swe-eval", "serve", "--host", "0.0.0.0"]

FROM api AS worker
USER root
RUN apt-get update && apt-get install -y --no-install-recommends docker.io \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-agent.lock ./
# Only DefaultAgent is used; do not install mini's unrelated dataset/provider/CLI stack.
RUN pip install --no-cache-dir --no-deps -r requirements-agent.lock
USER 10001:10001
CMD ["swe-eval", "worker"]
