from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.llm_configuration import load_configuration, save_configuration, validate_configuration


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


if __name__ == "__main__":
    unittest.main()
