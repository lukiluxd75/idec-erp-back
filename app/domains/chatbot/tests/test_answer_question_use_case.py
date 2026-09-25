"""Transaction boundaries around the slow model call."""
import unittest
from unittest.mock import MagicMock

from app.domains.chatbot.application.use_cases.answer_question_use_case import AnswerQuestionUseCase


class TestAnswerQuestionReleasesTheDatabase(unittest.TestCase):
    def test_lets_go_of_the_database_before_the_model_runs(self):
        """The reads that build the prompt open a transaction, and `chat` can take
        a couple of minutes. Held together they keep that transaction -- and this
        request's pooled connection -- open for the whole wait, which is how this
        database once stopped answering."""
        order = []
        procedures, history, engine = MagicMock(), MagicMock(), MagicMock()
        history.end_read.side_effect = lambda: order.append("end_read")
        engine.chat.side_effect = lambda *a, **k: order.append("chat") or "respuesta"
        engine.embed.return_value = [0.0]
        procedures.list_all_embeddings.return_value = []
        history.get_last_detected_procedure_id.return_value = None
        history.list_messages.return_value = []

        AnswerQuestionUseCase(
            procedure_repository=procedures,
            chat_history_repository=history,
            chat_engine=engine,
            match_threshold=0.5,
        ).execute(None, "hola", "user-a")

        self.assertEqual(order, ["end_read", "chat"])


if __name__ == "__main__":
    unittest.main()
