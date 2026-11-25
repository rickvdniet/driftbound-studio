"""Structured JSON logging with secret redaction."""
import json
import logging
import re
import sys

SECRET = re.compile(r"(key=|token=|Bearer\s+|\"refresh_token\":\s*\"|client_secret\"?:\s*\"?)([A-Za-z0-9_\-./]{6,})")
STD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message"}


def redact(s: str) -> str:
    return SECRET.sub(lambda m: m.group(1) + "***", s)


class JsonFormatter(logging.Formatter):
    def format(self, r):
        d = {"ts": self.formatTime(r), "level": r.levelname, "logger": r.name, "msg": r.getMessage()}
        d.update({k: v for k, v in r.__dict__.items() if k not in STD})
        return redact(json.dumps(d, default=str))


def setup_logging(level=logging.INFO):
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [h]
    root.setLevel(level)
