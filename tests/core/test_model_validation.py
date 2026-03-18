import pytest
from pydantic import ValidationError

from omni_agent.core.config import Settings


class TestModelValidation:
    """Test LLM_MODEL validation and standardization."""

    def test_standard_format_with_slash(self):
        """Test standard provider/model format."""
        settings = Settings(LLM_MODEL="anthropic/claude-3-5-sonnet-20241022")
        assert settings.LLM_MODEL == "anthropic/claude-3-5-sonnet-20241022"

    def test_legacy_colon_format(self):
        """Test legacy provider:model format converts to provider/model."""
        settings = Settings(LLM_MODEL="openai:gpt-4o")
        assert settings.LLM_MODEL == "openai/gpt-4o"

    def test_auto_detect_claude(self):
        """Test auto-detection of Claude models."""
        test_cases = [
            ("claude-3-5-sonnet-20241022", "anthropic/claude-3-5-sonnet-20241022"),
            ("claude-3-opus-20240229", "anthropic/claude-3-opus-20240229"),
            ("Claude-3-5-Sonnet", "anthropic/Claude-3-5-Sonnet"),
        ]
        for input_model, expected in test_cases:
            settings = Settings(LLM_MODEL=input_model)
            assert expected == settings.LLM_MODEL, f"Failed for {input_model}"

    def test_auto_detect_gpt(self):
        """Test auto-detection of GPT models."""
        test_cases = [
            ("gpt-4o", "openai/gpt-4o"),
            ("gpt-4-turbo", "openai/gpt-4-turbo"),
            ("gpt-3.5-turbo", "openai/gpt-3.5-turbo"),
            ("o1-preview", "openai/o1-preview"),
            ("o3-mini", "openai/o3-mini"),
        ]
        for input_model, expected in test_cases:
            settings = Settings(LLM_MODEL=input_model)
            assert expected == settings.LLM_MODEL, f"Failed for {input_model}"

    def test_auto_detect_gemini(self):
        """Test auto-detection of Gemini models."""
        test_cases = [
            ("gemini-1.5-pro", "gemini/gemini-1.5-pro"),
            ("gemini-pro", "gemini/gemini-pro"),
        ]
        for input_model, expected in test_cases:
            settings = Settings(LLM_MODEL=input_model)
            assert expected == settings.LLM_MODEL, f"Failed for {input_model}"

    def test_auto_detect_mistral(self):
        """Test auto-detection of Mistral models."""
        settings = Settings(LLM_MODEL="mistral-large-latest")
        assert settings.LLM_MODEL == "mistral/mistral-large-latest"

    def test_auto_detect_chinese_models(self):
        """Test auto-detection of Chinese models (defaults to openai/ for custom endpoints)."""
        test_cases = [
            ("qwen-max", "openai/qwen-max"),
            ("deepseek-chat", "openai/deepseek-chat"),
        ]
        for input_model, expected in test_cases:
            settings = Settings(LLM_MODEL=input_model)
            assert expected == settings.LLM_MODEL, f"Failed for {input_model}"

    def test_unknown_model_defaults_to_openai(self):
        """Test unknown models default to openai/ prefix (for custom endpoints)."""
        settings = Settings(LLM_MODEL="custom-model-v1")
        assert settings.LLM_MODEL == "openai/custom-model-v1"

    def test_whitespace_handling(self):
        """Test that whitespace is trimmed."""
        settings = Settings(LLM_MODEL="  anthropic/claude-3-5-sonnet-20241022  ")
        assert settings.LLM_MODEL == "anthropic/claude-3-5-sonnet-20241022"

    def test_empty_model_raises_error(self):
        """Test that empty model name raises validation error."""
        with pytest.raises(ValidationError, match="LLM_MODEL cannot be empty"):
            Settings(LLM_MODEL="")

    def test_case_insensitive_detection(self):
        """Test that provider detection is case-insensitive."""
        test_cases = [
            ("CLAUDE-3-5-SONNET", "anthropic/CLAUDE-3-5-SONNET"),
            ("GPT-4O", "openai/GPT-4O"),
            ("Gemini-Pro", "gemini/Gemini-Pro"),
        ]
        for input_model, expected in test_cases:
            settings = Settings(LLM_MODEL=input_model)
            assert expected == settings.LLM_MODEL, f"Failed for {input_model}"

    def test_already_prefixed_models_unchanged(self):
        """Test that models with correct prefix are not modified."""
        test_cases = [
            "openai/gpt-4o",
            "anthropic/claude-3-5-sonnet-20241022",
            "gemini/gemini-1.5-pro",
            "azure/my-deployment",
            "custom_provider/custom-model",
        ]
        for model in test_cases:
            settings = Settings(LLM_MODEL=model)
            assert model == settings.LLM_MODEL, f"Failed for {model}"
