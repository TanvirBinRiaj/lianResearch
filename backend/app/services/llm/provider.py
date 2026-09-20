import httpx
import json
import asyncio

# OpenAI-compatible adapter: works with OpenAI, OpenRouter, Gemini openai-compat, Ollama, LM Studio
async def chat_completion(provider_cfg, messages, stream=False, temperature=0.7, max_tokens=4096):
    """
    provider_cfg: {base_url, api_key, model}
    """
    if not provider_cfg:
        raise ValueError("No LLM provider configured. Go to Settings -> Models.")
    base = provider_cfg.get("base_url", "").rstrip("/")
    if not base:
        raise ValueError("Provider base_url missing")
    # normalize /v1
    if not base.endswith("/v1"):
        if "/v1" not in base:
            base = base + "/v1"
    url = base + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    key = provider_cfg.get("api_key", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    payload = {
        "model": provider_cfg.get("model"),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream
    }
    # Ollama via openai compat may not support stream flag same way
    async with httpx.AsyncClient(timeout=180) as client:
        if stream:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line: continue
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data == "[DONE]": break
                        try:
                            j = json.loads(data)
                            delta = j["choices"][0].get("delta", {}).get("content", "")
                            if delta:
                                yield delta
                        except: continue
        else:
            r = await client.post(url, json=payload, headers=headers)
            # don't raise immediately - capture body for diagnostics
            if r.status_code != 200:
                body = r.text[:4000]
                raise RuntimeError(f"LLM HTTP {r.status_code}: {body}")
            j = r.json()
            if "choices" not in j:
                raise RuntimeError(f"LLM response missing 'choices': {json.dumps(j)[:3000]}")
            if not j["choices"]:
                raise RuntimeError(f"LLM empty choices: {json.dumps(j)[:3000]}")
            # handle reasoning models that put content in different field
            msg = j["choices"][0].get("message", {})
            text = msg.get("content")
            if text is None:
                text = j["choices"][0].get("text", "") or msg.get("reasoning_content", "") or ""
            if not text:
                raise RuntimeError(f"LLM empty content: {json.dumps(j)[:3000]}")
            yield text

async def chat_once(provider_cfg, messages, **kw):
    # retry on transient network errors (VPN ReadError/Timeout/service_unavailable)
    last_exc=None
    for attempt in range(3):
        try:
            out = ""
            async for chunk in chat_completion(provider_cfg, messages, stream=False, **kw):
                out += chunk
            return out
        except Exception as e:
            last_exc=e
            msg = str(e)
            transient = any(k in msg for k in ["Timeout","ReadTimeout","ReadError","ConnectError","service_unavailable","temporarily unavailable","502","503","504"]) or "ReadError" in type(e).__name__ or "ConnectError" in type(e).__name__
            if transient and attempt < 2:
                wait = 2 * (attempt + 1)
                print(f"[llm] transient error attempt {attempt+1}/3: {type(e).__name__}: {msg[:300]} -> retry in {wait}s")
                await asyncio.sleep(wait)
                continue
            raise
    raise last_exc

async def list_models(provider_cfg):
    base = provider_cfg.get("base_url","").rstrip("/")
    if not base.endswith("/v1"):
        if "/v1" not in base: base += "/v1"
    headers={}
    if provider_cfg.get("api_key"):
        headers["Authorization"]=f"Bearer {provider_cfg['api_key']}"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(base+"/models", headers=headers)
        r.raise_for_status()
        return r.json()
