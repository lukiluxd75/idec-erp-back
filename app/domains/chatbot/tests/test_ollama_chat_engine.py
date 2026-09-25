"""The engine's answers are streamed so the digitization monitor can stop a PC
mid-call; these guard that the fragments are put back together unchanged."""
import json
import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from app.domains.chatbot.domain.exceptions import ChatEngineUnavailableException
from app.domains.chatbot.infrastructure.ollama.ollama_chat_engine import OllamaChatEngine


def _stream(*fragments):
    response = MagicMock(status_code=200)
    response.__enter__.return_value = response
    lines = [json.dumps({"message": {"content": f}}) for f in fragments]
    lines.append(json.dumps({"message": {"content": ""}, "done": True}))
    response.iter_lines.return_value = iter(lines)
    return response


def _engine(**kwargs):
    return OllamaChatEngine(base_url="http://pc1:11434", chat_model="m", vision_model="m",
                            embedding_model="m", chat_timeout=1, vision_timeout=1,
                            embedding_timeout=1, **kwargs)


class TestOllamaChatEngine(unittest.TestCase):
    @patch("app.domains.chatbot.infrastructure.ollama.ollama_chat_engine.requests.post")
    def test_chat_rebuilds_the_streamed_answer(self, post):
        post.return_value = _stream("Hola ", "arquitecto")
        self.assertEqual(_engine().chat("sistema", [{"role": "user", "content": "hola"}]), "Hola arquitecto")
        self.assertTrue(post.call_args.kwargs["json"]["stream"])
        self.assertTrue(post.call_args.kwargs["stream"])

    @patch("app.domains.chatbot.infrastructure.ollama.ollama_chat_engine.requests.post")
    def test_extract_json_reads_the_object_from_the_fragments(self, post):
        post.return_value = _stream('{"numero"', ': "123"}')
        self.assertEqual(_engine().extract_json("sistema", "texto"), {"numero": "123"})

    @patch("app.domains.chatbot.infrastructure.ollama.ollama_chat_engine.requests.post")
    def test_a_stop_from_the_monitor_ends_the_call(self, post):
        post.return_value = _stream("a medio ", "escribir")
        engine = _engine(borrow=lambda _host, _seconds: nullcontext(lambda: True))
        with self.assertRaises(ChatEngineUnavailableException):
            engine.chat("sistema", [{"role": "user", "content": "hola"}])

    @patch("app.domains.chatbot.infrastructure.ollama.ollama_chat_engine.requests.post")
    def test_embeddings_are_not_streamed(self, post):
        post.return_value = MagicMock(status_code=200, **{"json.return_value": {"embedding": [0.5]}})
        self.assertEqual(_engine().embed("texto"), [0.5])
        self.assertFalse(post.call_args.kwargs["stream"])


if __name__ == "__main__":
    unittest.main()
