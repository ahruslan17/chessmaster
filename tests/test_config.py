from app.core.config import Settings
from app.services.llm_coach import LLMCoachService


def test_comparison_model_is_explicit_not_an_automatic_fallback(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "openai/gpt-6.1-sol")
    monkeypatch.setenv("LLM_ALTERNATIVE_MODEL", "openai/gpt-5.6-terra")
    settings = Settings(_env_file=None)
    assert settings.llm_model == "openai/gpt-6.1-sol"
    assert settings.llm_alternative_model == "openai/gpt-5.6-terra"
    service = LLMCoachService(
        model=settings.llm_model, api_key="test", api_base="https://example.test/v1",
    )
    assert service._model == settings.llm_model
    assert not hasattr(service, "_alternative_model")
