"""Audit-only loopback-network model stub. Never a live-model score."""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        mode = self.path.strip("/").split("/")[0]
        if mode.startswith("status"):
            self.respond(int(mode[6:]), {"error": {"message": "audit-canary-token-for-redaction-only"}})
            return
        if mode == "timeout":
            time.sleep(4)
        if mode == "malformed":
            self.respond(200, b"not-json")
            return
        if mode == "empty-body":
            self.respond(200, b"")
            return
        assistants = sum(message.get("role") == "assistant" for message in body.get("messages", []))
        commands = [
            "cat intervals.py && python3 -m unittest -v test_public",
            "python3 - <<'PY'\nfrom pathlib import Path\np = Path('intervals.py')\np.write_text(p.read_text().replace('start < merged[-1][1]', 'start <= merged[-1][1]'))\nPY\npython3 -m unittest -v test_public",
        ]
        if mode == "sleep":
            command = "sleep 20"
        else:
            command = commands[assistants] if assistants < len(commands) else None
        if mode == "submit-only":
            command = None
        if body.get("tools"):
            name = "bash" if command else "submit"
            arguments = {"command": command} if command else {}
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "audit-call-" + str(assistants), "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]}
        else:
            message = {"role": "assistant", "content": "```bash\n" + command + "\n```" if command else "SUBMIT"}
        if mode == "empty-content":
            message = {"role": "assistant", "content": ""}
        value = {"choices": [{"message": message}]}
        if mode != "missing-usage":
            value["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "completion_tokens_details": {"reasoning_tokens": 2}}
        self.respond(200, value)

    def respond(self, status, value):
        payload = value if isinstance(value, bytes) else json.dumps(value).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
