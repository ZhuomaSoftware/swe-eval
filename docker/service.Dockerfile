ARG SWEBENCH_TOOLS_IMAGE=swe-eval-swebench-tools:5.0.2-02e7a74
FROM ${SWEBENCH_TOOLS_IMAGE} AS official-tools

FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS dashboard
WORKDIR /ui/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11.12-slim-bookworm AS api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements-core.lock ./
RUN pip install --no-cache-dir --no-deps -r requirements-core.lock
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY --from=dashboard /ui/src/swe_eval/static/ ./src/swe_eval/static/
# pip's explicit bytecode compilation ignores PYTHONDONTWRITEBYTECODE and would
# add __pycache__ files to the pinned benchmark snapshot installed as package data.
RUN pip install --no-cache-dir --no-deps --no-compile --no-build-isolation . \
    && groupadd --gid 10001 service && useradd --uid 10001 --gid 10001 --no-create-home service \
    && mkdir /data && chown 10001:10001 /data
COPY config/ /app/config/
USER 10001:10001
CMD ["swe-eval", "serve", "--host", "0.0.0.0"]

FROM api AS worker
USER root
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends docker.io \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-agent.lock ./
# Only DefaultAgent is used; do not install mini's unrelated dataset/provider/CLI stack.
RUN pip install --no-cache-dir --no-deps -r requirements-agent.lock \
    && python -m swe_eval.dependency_check --lean-agent
USER 10001:10001
CMD ["swe-eval", "worker"]

FROM worker AS development
USER root
RUN apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-test.lock ./
RUN pip install --no-cache-dir --no-deps -r requirements-test.lock
USER 10001:10001

# Official dependencies stay outside the accepted mini-agent site-packages.
FROM worker AS official-worker
COPY --from=official-tools /opt/swebench /opt/swebench
ENV SWE_SWEBENCH_PYTHON=/opt/swebench/bin/python

FROM development AS official-development
COPY --from=official-tools /opt/swebench /opt/swebench
ENV SWE_SWEBENCH_PYTHON=/opt/swebench/bin/python
