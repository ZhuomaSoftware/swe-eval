from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Callable, Protocol

from .schema import Metrics, ModelProfile


class ProviderError(RuntimeError):
    pass


class CompatibilityError(ProviderError):
    pass


class BudgetExceeded(ProviderError):
    pass


class ActionFormatError(ProviderError):
    pass


class LLMProvider(Protocol):
    def complete(self, messages: list[dict]) -> dict: ...


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not forward a bearer credential to a redirect destination.


def http_post(url: str, key: str, body: dict, timeout: float) -> dict:
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise CompatibilityError("upstream response exceeds 2 MiB")
            result = json.loads(data)
            if not isinstance(result, dict):
                raise CompatibilityError("upstream response must be a JSON object")
            return result
    except urllib.error.HTTPError as error:
        # Never include upstream response bodies, headers, request objects, or keys.
        status = error.code
        error.close()
        if status in {400, 404, 405, 422}:
            raise CompatibilityError(
                f"upstream HTTP {status}: verify Chat Completions URL, model ID, reasoning capability, "
                "output_token_parameter, and action_format; no automatic capability fallback") from None
        raise ProviderError(f"upstream HTTP {status}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProviderError("upstream connection failed or request timed out") from None
    except (ValueError, UnicodeError):
        raise CompatibilityError("upstream returned malformed JSON") from None


TOOLS = [
    {"type": "function", "function": {"name": "bash", "description": "Execute one bash command in /workspace.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}},
                       "required": ["command"], "additionalProperties": False}}},
    {"type": "function", "function": {"name": "submit", "description": "Finish the repair; changes are on disk.",
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}},
]


def parse_action(message: dict, action_format: str) -> dict:
    if action_format == "native_tools":
        calls = message.get("tool_calls") or []
        if len(calls) != 1:
            raise ActionFormatError("Return exactly one bash or submit function call")
        try:
            function = calls[0]["function"]
            args = json.loads(function["arguments"])
            name = function["name"]
            call_id = calls[0]["id"]
            if not isinstance(call_id, str) or not isinstance(args, dict):
                raise ValueError
            if name == "submit" and not args:
                return {"submit": True, "tool_call_id": call_id}
            if name == "bash" and set(args) == {"command"} and isinstance(args["command"], str) and args["command"].strip():
                return {"command": args["command"], "tool_call_id": call_id}
        except (KeyError, TypeError, ValueError):
            pass
        raise ActionFormatError("Invalid bash/submit function arguments")
    content = message.get("content")
    if not isinstance(content, str):
        raise ActionFormatError("Text actions require a string response")
    if content.strip() == "SUBMIT":
        return {"submit": True}
    matches = re.findall(r"```bash\s*\n(.*?)\n```", content, flags=re.DOTALL)
    if len(matches) != 1 or not matches[0].strip() or message.get("tool_calls"):
        raise ActionFormatError("Return exactly one ```bash command block, or SUBMIT")
    return {"command": matches[0]}


def count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class OpenAICompatibleProvider:
    def __init__(self, profile: ModelProfile, key: str, metrics: Metrics, *,
                 remaining: Callable[[], float], persist: Callable[[], None], transport=http_post):
        self.profile, self._key, self.metrics = profile, key, metrics
        self.remaining, self.persist, self.transport = remaining, persist, transport
        self._sums = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0}
        self._known = {name: True for name in self._sums}

    def body(self, messages):
        serialized = [{k: value for k, value in m.items() if k in {"role", "content", "tool_calls", "tool_call_id"}}
                      for m in messages if m.get("role") != "exit"]
        if len(json.dumps(serialized)) > self.profile.max_context_chars:
            raise BudgetExceeded("context character budget exceeded")
        output_limit = self.profile.max_output_tokens
        if self.profile.max_total_tokens is not None and self.metrics.model_requests:
            if self.metrics.total_tokens is None:
                raise BudgetExceeded("total-token budget requires upstream usage; stopping because usage is unknown")
            remaining = self.profile.max_total_tokens - self.metrics.total_tokens
            if remaining <= 0:
                raise BudgetExceeded("reported total-token budget reached")
            output_limit = min(output_limit, remaining)
        body = {"model": self.profile.model_id, "messages": serialized, "stream": False,
                self.profile.capabilities.output_token_parameter: output_limit}
        if self.profile.reasoning_effort:
            body["reasoning_effort"] = self.profile.reasoning_effort
        if self.profile.capabilities.action_format == "native_tools":
            body.update(tools=TOOLS, tool_choice="required", parallel_tool_calls=False)
        return body

    def _usage(self, response):
        usage = response.get("usage") or {}
        if not isinstance(usage, dict):
            usage = {}
        details = usage.get("completion_tokens_details") or {}
        if not isinstance(details, dict):
            details = {}
        values = {"input_tokens": count(usage.get("prompt_tokens")),
                  "output_tokens": count(usage.get("completion_tokens")),
                  "total_tokens": count(usage.get("total_tokens")),
                  "reasoning_tokens": count(details.get("reasoning_tokens"))}
        if values["total_tokens"] is None and values["input_tokens"] is not None and values["output_tokens"] is not None:
            values["total_tokens"] = values["input_tokens"] + values["output_tokens"]
        for name, value in values.items():
            self._known[name] &= value is not None
            self._sums[name] += value or 0
            setattr(self.metrics, name, self._sums[name] if self._known[name] else None)
        self.metrics.usage_complete = all(self._known[name] for name in ("input_tokens", "output_tokens", "total_tokens"))
        pricing = self.profile.pricing
        if pricing and self.metrics.usage_complete:
            # Reasoning tokens are a subset of completion tokens, not an extra charge.
            self.metrics.cost = (self.metrics.input_tokens * pricing.input_per_million +
                                 self.metrics.output_tokens * pricing.output_per_million) / 1_000_000
            self.metrics.currency = pricing.currency
        else:
            self.metrics.cost = None
            self.metrics.currency = None

    def complete(self, messages):
        if self.metrics.model_requests >= self.profile.max_model_calls:
            raise BudgetExceeded("model request limit reached")
        body = self.body(messages)
        self.metrics.model_requests += 1
        # A request may be billed even if the worker is killed before its response.
        # Persist unknown usage while it is in flight; internal sums are restored
        # only when a valid usage-bearing response arrives.
        for name in self._sums:
            setattr(self.metrics, name, None)
        self.metrics.usage_complete = False
        self.metrics.cost = None
        self.metrics.currency = None
        self.persist()
        try:
            response = self.transport(self.profile.base_url.rstrip("/") + "/chat/completions", self._key,
                                      body, min(self.profile.request_timeout, max(0.01, self.remaining())))
            self._usage(response)
            self.persist()
            choices = response.get("choices")
            if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                raise CompatibilityError("expected exactly one Chat Completions choice")
            message = choices[0].get("message")
            if not isinstance(message, dict):
                raise CompatibilityError("upstream choice is missing a message")
            # Only known fields enter the agent trajectory; response metadata is discarded.
            return {key: value for key, value in message.items() if key in {"content", "tool_calls"}} | {"role": "assistant"}
        except ProviderError:
            self.metrics.api_errors += 1
            self._usage({})  # Billing/usage on an errored response is unknown.
            self.metrics.cost = None
            self.persist()
            raise
