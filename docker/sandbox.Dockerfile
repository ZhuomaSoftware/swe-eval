FROM python:3.11.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends git bash coreutils tar \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 sandbox \
    && useradd --uid 10001 --gid 10001 --no-create-home sandbox \
    && mkdir -p /workspace && chown 10001:10001 /workspace
ENV PYTHONDONTWRITEBYTECODE=1
COPY --chown=0:0 src/swe_eval/candidate_runner.py /opt/swe-candidate.py
RUN chmod 0444 /opt/swe-candidate.py
USER 10001:10001
WORKDIR /workspace
CMD ["/bin/sleep", "infinity"]
