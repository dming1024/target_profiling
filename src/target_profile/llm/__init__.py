"""Optional LLM polishing with strict numeric guard and template fallback."""
from __future__ import annotations

import logging
import os

from target_profile.config import Settings
from target_profile.llm.cache import NarrativeCache, cache_key
from target_profile.llm.client import LLMClient
from target_profile.llm.guard import validate_numbers
from target_profile.llm.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
    template_narrative,
)
from target_profile.models import ModuleResult

__all__ = ["build_narratives", "template_narrative", "validate_numbers"]


def build_narratives(
    gene: str,
    modules: list[ModuleResult],
    settings: Settings,
    *,
    enabled: bool = True,
    client=None,
) -> dict:
    info: dict = {
        "enabled": bool(enabled),
        "model": settings.llm.model,
        "used": 0,
        "cached": 0,
        "fallback": 0,
    }
    llm_client = None
    if enabled and settings.llm.enabled and settings.llm.model:
        api_key = os.environ.get(settings.llm.api_key_env, "")
        if api_key:
            llm_client = client or LLMClient(
                settings.llm.base_url, settings.llm.model, api_key
            )
        else:
            info["error"] = f"missing {settings.llm.api_key_env}"

    cache = NarrativeCache(settings.data_root / "cache" / "_llm")
    for module in modules:
        if module.status != "ok":
            continue
        draft = template_narrative(gene, module)
        if not draft:
            continue
        text: str | None = None
        if llm_client is not None:
            key = cache_key(gene, module.facts, settings.llm.model, PROMPT_VERSION)
            cached = cache.get(key)
            if cached:
                text = cached
                info["cached"] += 1
            else:
                for _attempt in range(2):
                    try:
                        candidate = llm_client.complete(
                            SYSTEM_PROMPT, build_user_prompt(gene, module, draft)
                        )
                    except Exception as exc:  # network / API failure
                        logging.warning("llm %s failed: %s", module.name, exc)
                        break
                    offenders = validate_numbers(candidate, module.facts, gene)
                    if offenders:
                        logging.warning(
                            "llm guard rejected %s: %s", module.name, offenders[:5]
                        )
                        continue
                    text = candidate
                    cache.put(key, text)
                    info["used"] += 1
                    break
        if text is None:
            module.narrative = draft
            if llm_client is not None:
                info["fallback"] += 1
        else:
            module.narrative = text
    return info
