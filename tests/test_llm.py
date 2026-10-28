import unittest
import os
from unittest.mock import MagicMock, Mock, patch

from rag.llm import AnthropicClient, GeminiClient, OpenAICompatibleClient


class LLMAdapterTests(unittest.TestCase):
    @staticmethod
    def response(payload: dict) -> Mock:
        response = Mock(ok=True)
        response.json.return_value = payload
        return response

    @patch("rag.llm.requests.post")
    def test_openai_compatible_response(self, post: Mock) -> None:
        post.return_value = self.response({"choices": [{"message": {"content": "answer"}}]})
        client = OpenAICompatibleClient("key", "model", "https://example.test/v1", 10)
        self.assertEqual(client.generate([{"role": "user", "content": "hello"}]), "answer")
        self.assertEqual(post.call_args.args[0], "https://example.test/v1/chat/completions")

    @patch("rag.llm.requests.post")
    def test_anthropic_response(self, post: Mock) -> None:
        post.return_value = self.response({"content": [{"type": "text", "text": "answer"}]})
        client = AnthropicClient("key", "model", "https://api.anthropic.test/v1", 10)
        self.assertEqual(client.generate([{"role": "user", "content": "hello"}]), "answer")

    @patch("rag.llm.requests.post")
    def test_gemini_response(self, post: Mock) -> None:
        post.return_value = self.response(
            {"candidates": [{"content": {"parts": [{"text": "answer"}]}}]}
        )
        with patch.dict(os.environ, {"LLM_THINKING_LEVEL": ""}):
            client = GeminiClient("key", "model", "https://gemini.test/v1beta", 10)
        self.assertEqual(client.generate([{"role": "user", "content": "hello"}]), "answer")
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "key")
        self.assertNotIn("generationConfig", post.call_args.kwargs["json"])
        self.assertEqual(post.call_args.kwargs["timeout"], (10, 10))

    @patch("rag.llm.requests.post")
    def test_gemini_thinking_level(self, post: Mock) -> None:
        post.return_value = self.response(
            {"candidates": [{"content": {"parts": [{"text": "answer"}]}}]}
        )
        with patch.dict(os.environ, {"LLM_THINKING_LEVEL": "low"}):
            client = GeminiClient("key", "model", "https://gemini.test/v1beta", 30)
        client.generate([{"role": "user", "content": "hello"}])
        self.assertEqual(
            post.call_args.kwargs["json"]["generationConfig"],
            {"thinkingConfig": {"thinkingLevel": "low"}},
        )
        self.assertEqual(post.call_args.kwargs["timeout"], (10, 30))

    @patch("rag.llm.time.sleep")
    @patch("rag.llm.requests.post")
    def test_gemini_retries_then_uses_fallback(self, post: Mock, sleep: Mock) -> None:
        unavailable = Mock(ok=False, status_code=503, text="busy", headers={})
        success = self.response({"candidates": [{"content": {"parts": [{"text": "fallback"}]}}]})
        success.status_code = 200
        post.side_effect = [unavailable, unavailable, unavailable, success]
        with patch.dict(os.environ, {"LLM_MAX_RETRIES": "2", "LLM_FALLBACK_MODELS": "backup"}):
            client = GeminiClient("key", "primary", "https://gemini.test/v1beta", 10)
            self.assertEqual(client.generate([{"role": "user", "content": "hello"}]), "fallback")
        self.assertEqual(post.call_count, 4)
        self.assertIn("/models/backup:generateContent", post.call_args.args[0])
        self.assertEqual(sleep.call_count, 2)

    @staticmethod
    def sse(*events: str) -> MagicMock:
        response = MagicMock(ok=True, status_code=200)
        response.iter_lines.return_value = [line.encode() for event in events for line in (f"data: {event}", "")]
        response.__enter__.return_value = response
        return response

    @patch("rag.llm.requests.post")
    def test_openai_compatible_stream(self, post: Mock) -> None:
        post.return_value = self.sse(
            '{"choices": [{"delta": {"content": "Hel"}}]}', '{"choices": [{"delta": {"content": "lo"}}]}', "[DONE]"
        )
        client = OpenAICompatibleClient("key", "model", "https://example.test/v1", 10)
        self.assertEqual("".join(client.stream([{"role": "user", "content": "hi"}])), "Hello")
        self.assertTrue(post.call_args.kwargs["json"]["stream"])

    @patch("rag.llm.requests.post")
    def test_gemini_stream_skips_thoughts(self, post: Mock) -> None:
        post.return_value = self.sse(
            '{"candidates": [{"content": {"parts": [{"text": "thinking", "thought": true}]}}]}',
            '{"candidates": [{"content": {"parts": [{"text": "Answer"}]}}]}',
        )
        with patch.dict(os.environ, {"LLM_THINKING_LEVEL": ""}):
            client = GeminiClient("key", "model", "https://gemini.test/v1beta", 10)
        self.assertEqual("".join(client.stream([{"role": "user", "content": "hi"}])), "Answer")
        self.assertIn(":streamGenerateContent?alt=sse", post.call_args.args[0])

    @patch("rag.llm.requests.post")
    def test_anthropic_stream(self, post: Mock) -> None:
        post.return_value = self.sse(
            '{"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi"}}',
            '{"type": "message_stop"}',
        )
        client = AnthropicClient("key", "model", "https://api.anthropic.test/v1", 10)
        self.assertEqual("".join(client.stream([{"role": "user", "content": "hi"}])), "Hi")


if __name__ == "__main__":
    unittest.main()
