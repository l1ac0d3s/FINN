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
    """The first JSON list in a reply, or [] if there isn't one. Models often wrap JSON in prose."""
    match = re.search(r"\[.*\]", reply, re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [item for item in data if isinstance(item, dict)]
