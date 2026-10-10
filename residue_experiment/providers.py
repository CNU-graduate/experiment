"""Official SDK adapters. Mock/dry-run never instantiate SDK clients."""
import hashlib
import os
from .prompt import SYSTEM

KEYS = {'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY', 'gemini': 'GEMINI_API_KEY'}


class Provider:
    def __init__(self, provider, model, config):
        self.provider, self.model, self.config = provider, model, config
        key = os.environ.get(KEYS[provider])
        if not key or not model:
            raise ValueError(f'{provider}: API key and explicit model ID required')
        timeout = config['timeout_seconds']
        if provider == 'openai':
            from openai import OpenAI
            self.client = OpenAI(api_key=key, timeout=timeout, max_retries=0)
        elif provider == 'anthropic':
            from anthropic import Anthropic
            self.client = Anthropic(api_key=key, timeout=timeout, max_retries=0)
        else:
            from google import genai
            from google.genai import types
            self.client = genai.Client(api_key=key, http_options=types.HttpOptions(
                timeout=int(timeout * 1000), retry_options=types.HttpRetryOptions(attempts=1)))

    def call(self, prompt):
        tokens = self.config['max_output_tokens']
        if self.provider == 'openai':
            r = self.client.responses.create(model=self.model, instructions=SYSTEM,
                                              input=prompt, max_output_tokens=tokens)
            return r.output_text, r.usage.model_dump() if r.usage else {}, r.id
        if self.provider == 'anthropic':
            r = self.client.messages.create(model=self.model, system=SYSTEM, max_tokens=tokens,
                                            messages=[{'role': 'user', 'content': prompt}])
            return ''.join(b.text for b in r.content if b.type == 'text'), r.usage.model_dump(), r.id
        from google.genai import types
        r = self.client.models.generate_content(model=self.model, contents=prompt,
            config=types.GenerateContentConfig(system_instruction=SYSTEM, max_output_tokens=tokens))
        return r.text or '', r.usage_metadata.model_dump(mode='json') if r.usage_metadata else {}, getattr(r, 'response_id', '')


def mock_call(provider, prompt):
    # Deliberately arbitrary: exercises infrastructure, never measures LLM quality.
    bit = hashlib.sha256((provider + prompt).encode()).digest()[0] % 2
    return ('Yes' if bit else 'No'), {}, 'mock'
