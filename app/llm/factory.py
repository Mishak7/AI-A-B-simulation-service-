import logging

from app.config import get_settings
from app.llm.base import LLMClient
from app.llm.mock_client import MockLLMClient
from app.llm.real_client import RealLLMClient

logger = logging.getLogger(__name__)


def get_llm_client() -> LLMClient:
    settings = get_settings()
    provider = settings.llm_provider.lower()
    logger.info("Selecting LLM client provider=%s", provider)
    if provider == "mock":
        logger.warning("Using MockLLMClient. Set SAB_LLM_PROVIDER=real in .env to call the real API.")
        return MockLLMClient()
    if provider == "real":
        logger.info("Using RealLLMClient base_url=%s model=%s", settings.real_base_url, settings.real_model)
        return RealLLMClient()
    raise ValueError(f"Unsupported LLM provider: {provider}")
