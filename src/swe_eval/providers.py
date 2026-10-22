from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Callable, Protocol

from .schema import Metrics, ModelProfile


from .provider_errors import ProviderError, CompatibilityError, BudgetExceeded, ActionFormatError
from .retries import RequestRetryPolicy, classify_http, transport_failure
import time, random, socket, http.client, ssl


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
        try:
            payload = json.loads(error.read(65536))
        except (ValueError, OSError):
            payload = {}
        failure = classify_http(error.code, error.headers, payload)
        error.close()
        raise failure from None
    except ssl.SSLCertVerificationError:
        raise ProviderError("TLS verification failed", category="tls_verification") from None
    except (TimeoutError, socket.timeout):
        raise ProviderError("upstream request timed out", category="request_timeout", retryable=True, ambiguous=True) from None
    except (urllib.error.URLError, ConnectionError, OSError, http.client.HTTPException) as error:
        raise transport_failure(getattr(error,"reason",error)) from None
    except (ValueError, UnicodeError):
        raise CompatibilityError("upstream returned malformed JSON", category="malformed_response", ambiguous=True) from None


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
                 remaining: Callable[[], float], persist: Callable[[], None], transport=http_post,
                 retry_policy=None, runtime=None, sleep=time.sleep, clock=time.monotonic, jitter=random.random):
        self.profile, self._key, self.metrics = profile, key, metrics
        if profile.provider_id and transport is http_post:
            from .outbound import request_json
            transport = request_json
        self.remaining, self.persist, self.transport = remaining, persist, transport
        self.policy = RequestRetryPolicy.model_validate(retry_policy or {})
        self.runtime, self.sleep, self.clock, self.jitter = runtime, sleep, clock, jitter
        self._sums = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0}
        self._known = {name: True for name in self._sums}
        self._priced_samples = 0

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
        if values['input_tokens'] is not None and values['output_tokens'] is not None:
            self._priced_samples += 1
        self.metrics.known_input_tokens=self._sums['input_tokens']
        self.metrics.known_output_tokens=self._sums['output_tokens']
        self.metrics.known_total_tokens=self._sums['total_tokens']
        if pricing and self._priced_samples:
            self.metrics.known_cost_subtotal=(self._sums['input_tokens']*pricing.input_per_million+self._sums['output_tokens']*pricing.output_per_million)/1_000_000
            self.metrics.known_cost_currency=pricing.currency
        if pricing and self.metrics.usage_complete:
            # Reasoning tokens are a subset of completion tokens, not an extra charge.
            self.metrics.cost = (self.metrics.input_tokens * pricing.input_per_million +
                                 self.metrics.output_tokens * pricing.output_per_million) / 1_000_000
            self.metrics.currency = pricing.currency
        else:
            self.metrics.cost = None
            self.metrics.currency = None

    def complete(self, messages):
        if self.metrics.http_attempts >= self.profile.max_model_calls:
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
        policy = self.policy
        started = self.clock()
        maximum = policy.max_attempts if policy.enabled else 1
        response = None
        for attempt in range(1, maximum+1):
            dispatched=False
            try:
                if self.runtime:
                    self.runtime.available()
                    cooldown = self.runtime.cooldown()
                    if cooldown > 0:
                        if cooldown > min(policy.max_delay, policy.time_budget-(self.clock()-started), self.remaining()-0.05):
                            raise ProviderError("provider cooldown exceeds request wait allowance", category="capacity_unavailable", retryable=True, retry_after=cooldown)
                        self._wait(cooldown, started)
                if self.metrics.http_attempts >= self.profile.max_model_calls:
                    raise BudgetExceeded("physical HTTP request allowance exhausted", category="request_limit")
                if attempt>1 and self.clock()-started>=policy.time_budget:
                    raise ProviderError("request retry time budget exhausted",category="request_timeout",retryable=True)
                self.metrics.http_attempts += 1
                dispatched=True
                if attempt>1:self.metrics.http_retries += 1
                now=time.time()
                self.metrics.first_api_attempt_at = self.metrics.first_api_attempt_at or now
                self.metrics.last_api_attempt_at = now
                self.metrics.provider_outcome = "requesting"
                self.persist()
                timeout=min(self.profile.request_timeout, max(.01,self.remaining()))
                if policy.enabled:timeout=min(timeout,max(.01,policy.time_budget-(self.clock()-started)))
                response = self.transport(self.profile.base_url.rstrip("/")+"/chat/completions",self._key,body,timeout)
                if not isinstance(response,dict):raise CompatibilityError("expected JSON object",category="malformed_response",ambiguous=True)
                choices=response.get("choices")
                if not isinstance(choices,list) or len(choices)!=1 or not isinstance(choices[0],dict) or not isinstance(choices[0].get("message"),dict):
                    raise CompatibilityError("expected exactly one Chat Completions message",category="malformed_response",ambiguous=True)
                self._usage(response)
                self.metrics.provider_outcome="succeeded"
                self.metrics.retry_exhaustion_reason=None
                self.persist()
                self._event("api_response",attempt=attempt,outcome="succeeded")
                return {key:value for key,value in choices[0]["message"].items() if key in {"content","tool_calls"}} | {"role":"assistant"}
            except BudgetExceeded:
                self.metrics.retry_exhaustion_reason="request_limit"
                self.metrics.recovery_eligible=False
                self.persist()
                raise
            except ProviderError as error:
                if dispatched:self.metrics.api_errors += 1
                self._usage({})
                self.metrics.billing_uncertain |= error.ambiguous
                self.metrics.last_provider_error={"category":error.category,"http_status":error.status,"retryable":error.retryable,"provider_code":error.provider_code}
                delay=max(error.retry_after or 0,min(policy.max_delay,policy.initial_delay*policy.multiplier**(attempt-1))*(.5+.5*self.jitter()))
                reason=("permanent_or_unknown" if not error.retryable else "disabled" if not policy.enabled else
                        "attempts_exhausted" if attempt>=maximum else "request_limit" if self.metrics.http_attempts>=self.profile.max_model_calls else
                        "retry_time_budget" if delay+.05>=policy.time_budget-(self.clock()-started) else
                        "deadline_insufficient" if delay+.05>=self.remaining() else
                        "cooldown_deferred" if delay>policy.max_delay else None)
                if self.runtime and error.retryable:
                    # Durable endpoint cooldown affects other jobs and survives restart.
                    self.metrics.provider_cooldown_seconds=max(self.metrics.provider_cooldown_seconds,delay)
                    self.runtime.cooldown(delay,error.category)
                self.metrics.provider_outcome="failed" if reason else "rate_limit_wait" if error.status==429 else "retrying"
                self.metrics.retry_exhaustion_reason=reason
                # Only an actually exhausted transient request is recovery-eligible.
                self.metrics.recovery_eligible=bool(error.retryable and reason in ("attempts_exhausted","retry_time_budget","cooldown_deferred"))
                self.persist()
                self._event("api_retry_stopped" if reason else "api_retry_wait",attempt=attempt,category=error.category,http_status=error.status,delay_seconds=delay,reason=reason)
                if reason:raise
                self._wait(delay,started)
        raise ProviderError("request retry exhausted")

    def _event(self,event,**detail):
        if self.runtime:self.runtime.log(event,detail)

    def _wait(self,delay,started):
        self.metrics.retry_backoff_seconds += delay
        self.persist()
        until=self.clock()+delay
        while self.clock()<until:
            self.remaining()
            if self.runtime:
                try:self.runtime.available()
                except ProviderError as error:
                    self.metrics.provider_outcome='failed'
                    self.metrics.recovery_eligible=False
                    self.metrics.last_provider_error={'category':error.category,'http_status':error.status,'retryable':False}
                    self.metrics.retry_exhaustion_reason='provider_unavailable'
                    self.persist()
                    raise
            remaining_wait=until-self.clock()
            if remaining_wait>0:self.sleep(min(.2,remaining_wait))
