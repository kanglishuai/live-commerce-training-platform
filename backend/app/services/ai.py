"""LLM 访问适配层。

约束（AGENTS.md 第 5 节）：
- 外部调用必须有超时与失败降级；解析不信任裸输出（剥离 markdown 围栏、截取 JSON、字段校验、失败重试）。
- 未配置模型或调用失败时抛 AiUnavailable，由调用方降级为规则兜底，并在响应 source 字段标明，
  绝不把规则结果伪装成 AI 输出。
"""
import json
import logging
import re

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AiUnavailable(Exception):
    """模型服务不可用（未配置 / 超时 / 解析失败）。"""


def is_llm_configured() -> bool:
    s = get_settings()
    return bool(s.llm_base_url and s.llm_api_key and s.llm_model)


def _extract_json(text: str) -> dict:
    """从模型输出中提取 JSON 对象：剥离 ``` 围栏，截取首尾花括号。"""
    t = text.strip()
    t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("响应中未找到 JSON 对象")
    data = json.loads(t[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON 顶层必须是对象")
    return data


def chat(
    prompt: str,
    *,
    system: str = "",
    temperature: float = 0.7,
    retries: int = 1,
    timeout: float | None = None,
) -> tuple[str, str]:
    """调用 LLM，返回 (文本, "llm")。失败抛 AiUnavailable。timeout 为空时用全局配置。"""
    settings = get_settings()
    if not is_llm_configured():
        raise AiUnavailable("未配置 LLM（LLM_BASE_URL / LLM_API_KEY / LLM_MODEL）")
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    effective_timeout = timeout if timeout is not None else settings.llm_timeout_seconds
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = httpx.post(
                url,
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "temperature": temperature,
                },
                timeout=effective_timeout,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            return text, "llm"
        except Exception as exc:  # noqa: BLE001 —— 统一转 AiUnavailable，细节进日志
            last_error = exc
            logger.warning("LLM 调用失败（第 %s 次尝试）：%s", attempt + 1, exc)
    raise AiUnavailable(f"LLM 调用失败：{last_error}")


def chat_json(
    prompt: str, *, system: str = "", retries: int = 1, timeout: float | None = None
) -> tuple[dict, str]:
    """要求模型输出 JSON 并完成解析防御，返回 (dict, "llm")。"""
    text, _ = chat(prompt, system=system, retries=retries, timeout=timeout)
    try:
        return _extract_json(text), "llm"
    except (ValueError, json.JSONDecodeError) as exc:
        raise AiUnavailable(f"LLM 输出无法解析为 JSON：{exc}") from exc
