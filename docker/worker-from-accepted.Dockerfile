# Offline staging path: pre-existing accepted runtimes, newly built API package,
# and independently commit-pinned official tools. Does not mutate base images.
ARG ACCEPTED_WORKER_IMAGE=swe-p25-remediation-worker:20261021t114531
ARG ACCEPTED_DEVELOPMENT_IMAGE=swe-p25-remediation-development:20261021t114531
ARG PHASE26_API_IMAGE=swe-p26-api:20261021
ARG SWEBENCH_TOOLS_IMAGE=swe-eval-swebench-tools:5.0.2-02e7a74
FROM ${PHASE26_API_IMAGE} AS package
FROM ${SWEBENCH_TOOLS_IMAGE} AS official-tools
FROM ${ACCEPTED_WORKER_IMAGE} AS worker
USER root
RUN rm -rf /usr/local/lib/python3.11/site-packages/swe_eval /usr/local/lib/python3.11/site-packages/independent_swe_eval-0.2.0.dist-info
COPY --from=package /usr/local/lib/python3.11/site-packages/swe_eval /usr/local/lib/python3.11/site-packages/swe_eval
COPY --from=package /usr/local/lib/python3.11/site-packages/independent_swe_eval-0.2.0.dist-info /usr/local/lib/python3.11/site-packages/independent_swe_eval-0.2.0.dist-info
COPY --from=package /app/config /app/config
COPY --from=official-tools /opt/swebench /opt/swebench
ENV SWE_SWEBENCH_PYTHON=/opt/swebench/bin/python
RUN python -m swe_eval.dependency_check --lean-agent && /opt/swebench/bin/pip check
USER 10001:10001
CMD ["swe-eval","worker"]
FROM ${ACCEPTED_DEVELOPMENT_IMAGE} AS development
USER root
RUN rm -rf /usr/local/lib/python3.11/site-packages/swe_eval /usr/local/lib/python3.11/site-packages/independent_swe_eval-0.2.0.dist-info
COPY --from=package /usr/local/lib/python3.11/site-packages/swe_eval /usr/local/lib/python3.11/site-packages/swe_eval
COPY --from=package /usr/local/lib/python3.11/site-packages/independent_swe_eval-0.2.0.dist-info /usr/local/lib/python3.11/site-packages/independent_swe_eval-0.2.0.dist-info
COPY --from=package /app/config /app/config
COPY --from=official-tools /opt/swebench /opt/swebench
ENV SWE_SWEBENCH_PYTHON=/opt/swebench/bin/python
RUN python -m swe_eval.dependency_check --lean-agent && /opt/swebench/bin/pip check
USER 10001:10001
CMD ["swe-eval","worker"]
