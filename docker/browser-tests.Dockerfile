FROM python:3.11.12-slim-bookworm AS certificates
FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392
COPY --from=certificates /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
WORKDIR /tests
COPY frontend/package.json frontend/package-lock.json ./
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80retries \
    && npm ci --no-audit --no-fund && npx playwright install --with-deps chromium
COPY frontend/playwright.config.ts ./
COPY frontend/e2e/ ./e2e/
CMD ["npm","run","test:e2e"]
