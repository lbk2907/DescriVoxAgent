"""Fix source_path -> video_path in player_window.py and add AIEngine.ask."""
import io

# ── Fix 1: player_window source_path ──────────────────────────
path = r"src\omni_describer_custom\ui\player_window.py"
with io.open(path, encoding="utf-8") as f:
    data = f.read()

old = (
    '        video_path = ""\n'
    "        if self.store.current and self.store.current.source_path:\n"
    "            video_path = self.store.current.source_path\n"
)
new = (
    '        video_path = ""\n'
    "        if self.store.current:\n"
    "            video_path = self.store.current.video_path\n"
)
assert data.count(old) == 1, repr(data.count(old))
data = data.replace(old, new, 1)
with io.open(path, "w", encoding="utf-8", newline="") as f:
    f.write(data)
print("player_window: OK")

# ── Fix 2: AIEngine.ask missing ───────────────────────────────
path = r"src\omni_describer_custom\core\ai_engine.py"
with io.open(path, encoding="utf-8") as f:
    data = f.read()

needle = "    async def ask_about_scene(\n"
assert data.count(needle) == 1, data.count(needle)

add = '''    async def ask(
        self,
        question: str,
        history: list[dict] | None = None,
        provider: str = "",
        model: str = "",
    ) -> str:
        """Free-form text question to the current provider (no image)."""
        provider_name = provider or self._default_provider
        if not provider_name or provider_name not in self._providers:
            raise ValueError("No AI provider configured. Call set_provider() first.")
        prov = self._providers[provider_name]
        ask_fn = getattr(prov, "ask_text", None)
        if ask_fn is None:
            raise ValueError(f"Provider '{provider_name}' does not support text questions.")
        return await ask_fn(question, history, model)

'''
data = data.replace(needle, add + needle, 1)
with io.open(path, "w", encoding="utf-8", newline="") as f:
    f.write(data)
print("ai_engine ask: OK")
