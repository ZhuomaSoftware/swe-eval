from __future__ import annotations

import json
import logging
import re


class Redactor:
    def __init__(self, secrets=()):
        self.secrets = sorted({s for s in secrets if s}, key=len, reverse=True)

    def add(self, secret):
        if secret:self.secrets = sorted(set(self.secrets) | {secret}, key=len, reverse=True)

    def __call__(self, value: str) -> str:
        for secret in self.secrets:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?i)(bearer\s+)[^\s\"']+", r"\1[REDACTED]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", value)
        return value

    def contains_secret(self, value: str) -> bool:
        return self(value) != value

    def data(self, value):
        if isinstance(value, str):
            return self(value)
        if isinstance(value, dict):
            return {key: self.data(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.data(item) for item in value]
        return value


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {"level": record.levelname, "logger": record.name, "message": record.getMessage()}
        for name in ("run_id", "event"):
            if hasattr(record, name):
                payload[name] = getattr(record, name)
        return json.dumps(payload, ensure_ascii=True)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    # Never enable transport or upstream trajectory debug logs in the service.
    for name in ("httpx", "httpcore", "minisweagent", "agent", "urllib3", "LiteLLM"):
        logging.getLogger(name).disabled = True
