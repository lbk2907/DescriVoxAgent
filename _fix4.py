"""Add text-only ask_text to all AI providers."""
import io

path = r"src\omni_describer_custom\core\ai_engine.py"
with io.open(path, encoding="utf-8") as f:
    data = f.read()

# 1. Base class default: after _load_image_b64
base_needle = '''        data = base64.b64encode(path.read_bytes()).decode()
        return data, mime
'''
base_add = base_needle + '''
    async def ask_text(
        self, question: str, history: list[dict] | None = None, model: str = ""
    ) -> str:
        """Text-only question. Default: not supported."""
        raise NotImplementedError(f"Provider '{self.name}' does not support text questions.")
'''
assert data.count(base_needle) == 1, ("base", data.count(base_needle))
data = data.replace(base_needle, base_add, 1)

# 2. Gemini ask_text — after describe_frames_batch of GeminiProvider
gem_needle = '''                results.append(desc)
        return results


class OpenAIProvider(AIProvider):'''
gem_add = '''                results.append(desc)
        return results

    async def ask_text(
        self, question: str, history: list[dict] | None = None, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("Gemini API key not configured")
        model = model or self.models[0]
        contents: list[dict] = []
        for msg in (history or []):
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
        contents.append({"role": "user", "parts": [{"text": question}]})

        url = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        payload = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": 1024},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"Gemini error: {data['error']}")
                candidates = data.get("candidates", [])
                if not candidates:
                    return "(no response from Gemini)"
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return text or "(empty response)"


class OpenAIProvider(AIProvider):'''
assert data.count(gem_needle) == 1, ("gemini", data.count(gem_needle))
data = data.replace(gem_needle, gem_add, 1)

# 3. OpenAI ask_text — after its describe_frames_batch
oai_needle = '''                results.append(desc)
        return results


class OpusProvider(AIProvider):'''
oai_add = '''                results.append(desc)
        return results

    async def ask_text(
        self, question: str, history: list[dict] | None = None, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")
        model = model or self.models[0]
        messages: list[dict] = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in (history or [])
        ]
        messages.append({"role": "user", "content": question})
        url = f"{self.base_url}/chat/completions"
        payload = {"model": model, "max_tokens": 1024, "messages": messages}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    raise RuntimeError(f"OpenAI error: {data['error']}")
                choices = data.get("choices", [])
                if not choices:
                    return "(no response from OpenAI)"
                return choices[0]["message"]["content"]


class OpusProvider(AIProvider):'''
assert data.count(oai_needle) == 1, ("openai", data.count(oai_needle))
data = data.replace(oai_needle, oai_add, 1)

# 4. Opus ask_text — after its describe_frames_batch
opus_needle = '''                results.append(desc)
        return results


# Custom provider API format constants'''
opus_add = '''                results.append(desc)
        return results

    async def ask_text(
        self, question: str, history: list[dict] | None = None, model: str = ""
    ) -> str:
        if not self.api_key:
            raise ValueError("Opus Proxy API key not configured")
        model = model or self.models[0]
        messages: list[dict] = [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in (history or [])
        ]
        messages.append({"role": "user", "content": question})
        url = f"{self.base_url}/messages"
        payload = {"model": model, "max_tokens": 1024, "messages": messages}
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"Opus Proxy HTTP {resp.status}: {body[:200]}")
                data = await resp.json()
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        return block["text"]
                return "(no text in Opus response)"


# Custom provider API format constants'''
assert data.count(opus_needle) == 1, ("opus", data.count(opus_needle))
data = data.replace(opus_needle, opus_add, 1)

with io.open(path, "w", encoding="utf-8", newline="") as f:
    f.write(data)
print("ask_text INSERTED for base+gemini+openai+opus")
