FROM python:3.11.12-slim-bookworm
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements-swebench.lock /tmp/requirements.lock
RUN python -m venv /opt/swebench && /opt/swebench/bin/pip install --no-cache-dir --no-deps -r /tmp/requirements.lock && /opt/swebench/bin/pip install --no-cache-dir --no-deps 'git+https://github.com/SWE-bench/SWE-bench.git@02e7a74ffd0b707aab73d203fe87bdc7c76afc8e' && /opt/swebench/bin/pip check
