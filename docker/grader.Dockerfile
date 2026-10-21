ARG SANDBOX_IMAGE=swe-eval-sandbox:phase1
FROM ${SANDBOX_IMAGE}
USER root
COPY --chown=0:0 src/swe_eval/benchmarks/data/intervals/hidden/ /opt/hidden/
RUN chmod -R a-w /opt/hidden && chmod 0555 /opt/hidden
USER 10001:10001
