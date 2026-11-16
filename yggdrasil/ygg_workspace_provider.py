"""Bounded streaming transport for the Workspace's explicitly configured model."""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator


class ProviderError(RuntimeError):
    """Safe, user-facing provider failure (never includes response bodies or keys)."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward a configured provider's Authorization to another endpoint.
        return None


def stream_model(settings: dict, messages: list[dict], stop: threading.Event) -> Iterator[str]:
    provider = settings["provider"]
    base = settings["url"].rstrip("/")
    if provider == "openai":
        base = base if base.endswith("/v1") else base + "/v1"
        url = base + "/chat/completions"
        body = {"model": settings["model"], "messages": messages, "stream": True,
                "max_tokens": 2048}
    else:
        url = base + "/api/chat"
        body = {"model": settings["model"], "messages": messages, "stream": True,
                "options": {"num_ctx": 16384, "num_predict": 2048}}
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream" if provider == "openai" else "application/x-ndjson"}
    if settings.get("api_key"):
        headers["Authorization"] = "Bearer " + settings["api_key"]
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
    deadline = time.monotonic() + 120
    try:
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(request, timeout=10) as response:
            while not stop.is_set():
                if time.monotonic() > deadline:
                    raise ProviderError("Модель не завершила ответ за 120 секунд. Попробуйте ещё раз.")
                raw = response.readline(1_048_577)
                if len(raw) > 1_048_576:
                    raise ProviderError("Модель вернула слишком большой фрагмент ответа.")
                if not raw:
                    raise ProviderError("Соединение с моделью прервалось. Ответ не завершён.")
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                if provider == "openai":
                    if not line.startswith("data:"):
                        continue
                    line = line[5:].strip()
                    if line == "[DONE]":
                        return
                data = json.loads(line)
                if not isinstance(data, dict) or data.get("error"):
                    raise ProviderError("Модель не смогла выполнить запрос. Проверьте подключение и название модели.")
                if provider == "ollama":
                    content = data.get("message", {}).get("content", "")
                    if not isinstance(content, str):
                        raise ValueError("invalid content")
                    if content:
                        yield content
                    if data.get("done"):
                        return
                else:
                    choices = data.get("choices", [])
                    if not isinstance(choices, list):
                        raise ValueError("invalid choices")
                    if choices:
                        content = choices[0].get("delta", {}).get("content") or ""
                        if not isinstance(content, str):
                            raise ValueError("invalid content")
                        if content:
                            yield content
    except ProviderError:
        raise
    except urllib.error.HTTPError as exc:
        exc.close()
        if exc.code in (401, 403):
            raise ProviderError("Модель отклонила ключ доступа. Проверьте настройки подключения.") from None
        raise ProviderError("Модель недоступна или отклонила запрос. Проверьте адрес и название модели.") from None
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError):
        raise ProviderError("Не удалось получить полный ответ модели. Проверьте подключение и повторите запрос.") from None
