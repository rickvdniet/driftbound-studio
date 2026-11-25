"""Local LLM (Ollama) with strict schema validation, bounded retries and deterministic template fallback (spec 12)."""
import json
import logging

import httpx
from pydantic import BaseModel, ValidationError

from app.config.settings import get_settings

log = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    pass


class OllamaProvider:
    name, paid, local = "ollama", False, True

    def __init__(self, model: str, url: str | None = None, timeout=180):
        self.model, self.url, self.timeout = model, url or get_settings().ollama_url, timeout

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.url}/api/tags", timeout=2)
            return r.status_code == 200 and any(m["name"].startswith(self.model.split(":")[0]) for m in r.json().get("models", []))
        except Exception:
            return False

    def structured(self, system: str, prompt: str, schema: type[BaseModel], retries: int = 2) -> BaseModel:
        """Ollama /api/chat with `format` = JSON schema (structured outputs). Validate, re-ask with the error on failure."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        last_err = None
        for _ in range(retries + 1):
            try:
                r = httpx.post(f"{self.url}/api/chat", timeout=self.timeout, json={
                    "model": self.model, "messages": messages, "stream": False,
                    "format": schema.model_json_schema(), "options": {"temperature": 0.7}})
                r.raise_for_status()
                content = r.json()["message"]["content"]
                return schema.model_validate_json(content)
            except ValidationError as e:
                last_err = e
                messages += [{"role": "assistant", "content": content},
                             {"role": "user", "content": f"That JSON was invalid: {str(e)[:800]}. Return corrected JSON only."}]
            except (httpx.HTTPError, KeyError, json.JSONDecodeError) as e:
                raise LLMUnavailable(str(e)) from e
        raise LLMUnavailable(f"invalid output after retries: {last_err}")


def get_llm(provider_settings: dict):
    """Returns an available local provider or None (callers then use templates)."""
    choice = provider_settings.get("llm", "auto")
    if choice in ("template", "manual"):
        return None
    model = provider_settings.get("llm_model") or "qwen2.5:7b-instruct"
    p = OllamaProvider(model)
    return p if p.available() else None
