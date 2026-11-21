from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from core.llm_configuration import configuration_from_environment, load_configuration, save_configuration, validate_configuration


class LLMConfigurationTests(unittest.TestCase):
    def test_round_trip_and_validation(self) -> None:
        configuration = validate_configuration(
            {
                "service": "custom",
                "model": "local-model",
                "api_key": "local-key",
                "base_url": "http://localhost:11434/v1/",
            }
        )
        self.assertEqual(configuration["provider"], "openai-compatible")
        self.assertEqual(configuration["base_url"], "http://localhost:11434/v1")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "llm_config.json"
            save_configuration(path, configuration)
            self.assertEqual(load_configuration(path), configuration)

    def test_key_is_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "API key"):
            validate_configuration({"service": "openai", "model": "gpt-6.1-sol", "api_key": ""})

    def test_openai_compatible_environment_keeps_the_openai_default_url(self) -> None:
        with patch.dict(
            "os.environ",
            {"LLM_PROVIDER": "openai-compatible", "LLM_MODEL": "test-model", "LLM_API_KEY": "test-key", "LLM_BASE_URL": ""},
        ):
            configuration = configuration_from_environment()
        self.assertEqual(configuration["service"], "openai")
        self.assertEqual(configuration["base_url"], "https://api.openai.com/v1")


if __name__ == "__main__":
    unittest.main()
