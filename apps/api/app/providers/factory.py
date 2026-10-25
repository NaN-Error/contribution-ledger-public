from app.providers.contracts import ProviderError
from app.providers.mock import MockProvider
from app.providers.openai import OpenAIProvider
from app.providers.anthropic import AnthropicProvider
from app.providers.gemini import GeminiProvider
class ProviderFactory:
    def __init__(self,settings,transport=None):self.settings=settings;self.transport=transport
    def get(self,provider):
        if provider=='mock':return MockProvider()
        if not self.settings.ai_live_enabled or self.settings.ai_deployment_mode!='customer_controlled':raise ProviderError('disabled')
        if provider not in self.settings.ai_permitted_providers:raise ProviderError('disabled')
        cls={'openai':OpenAIProvider,'anthropic':AnthropicProvider,'gemini':GeminiProvider}.get(provider)
        if cls is None:raise ProviderError('disabled')
        return cls(self.transport)
