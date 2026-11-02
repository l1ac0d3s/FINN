"""Free-tier language model via Hugging Face's OpenAI-compatible router.

Needs a free Hugging Face account and an access token in HF_TOKEN. The model
can be changed with FINN_LLM_MODEL. Free-tier availability and limits change,
so check them on huggingface.co before the demo.
"""

import json
import os
import re

import requests

ROUTER_URL = os.environ.get("FINN_LLM_URL", "https://router.huggingface.co/v1/chat/completions")
MODEL = os.environ.get("FINN_LLM_MODEL", "Qwen/Qwen2.5-7B-Instruct")


def complete(system, user, max_tokens=600):
    """One chat completion. Temperature 0, so repeated runs give the same answer.

    Any OpenAI-compatible endpoint works. The key comes from FINN_LLM_KEY, or HF_TOKEN.
    """
    token = os.environ.get("FINN_LLM_KEY") or os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("FINN_LLM_KEY (or HF_TOKEN) is not set")
    resp = requests.post(
        ROUTER_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0,
        },
        timeout=900,  # a local model on a laptop CPU can take several minutes per answer
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def parse_json_list(reply):
    """The claims in a model reply. Models often wrap JSON in prose, or stop mid-list when
    they run out of tokens, so any complete object is kept even if the list is cut short."""
    match = re.search(r"\[.*\]", reply, re.S)
    if match:
        try:
            return [item for item in json.loads(match.group(0)) if isinstance(item, dict)]
        except json.JSONDecodeError:
            pass
    objects = []
    for text in re.findall(r"\{[^{}]*\}", reply):
        try:
            objects.append(json.loads(text))
        except json.JSONDecodeError:
            continue
    return objects


def parse_tagged_claims(reply):
    """Claims written as tagged blocks, which smaller models often use instead of JSON:
    [quote]...[/quote] followed by [page]N, [metric]x, [period]y, [growth_pct]z lines."""
    claims = []
    for block in reply.split("[quote]")[1:]:
        quote = re.split(r"\[/quote\]|\[page\]", block)[0].strip()
        fields = {}
        for name, value in re.findall(r"\[(page|metric|period|growth_pct)\]\s*([^\[\n]*)", block):
            fields.setdefault(name, value.strip())
        growth = fields.get("growth_pct", "null")
        try:
            growth = float(growth)
        except ValueError:
            growth = None
        page = fields.get("page", "")
        claims.append({
            "quote": quote,
            "page": int(page) if page.isdigit() else None,
            "metric": fields.get("metric") if fields.get("metric") not in (None, "", "null") else None,
            "period": fields.get("period") if fields.get("period") not in (None, "", "null") else None,
            "growth_pct": growth,
        })
    return claims


def parse_claims(reply):
    """JSON list if the model gave one, otherwise the tagged format."""
    claims = parse_json_list(reply)
    return claims if claims else parse_tagged_claims(reply)
