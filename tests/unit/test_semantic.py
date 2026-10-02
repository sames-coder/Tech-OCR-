import json
from urllib.error import URLError

import pytest

from bankxat.config import AiConfig
from bankxat.extract.candidates import apply_pair_order_roles, find_card_candidates
from bankxat.models import ExtractedPage, Role
from bankxat.semantic import SemanticAssistant, apply_semantic_roles


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_ai_can_correct_pair_order_using_verified_text_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "Asosiy karta 4111 1111 1111 1111. Murojaat raqami 4012 8888 8888 1881."
    page = ExtractedPage(page=1, source="text_layer", text=text)
    candidates = apply_pair_order_roles(find_card_candidates(page))
    assert candidates[0].role is Role.SENDER

    ai_content = {
        "cards": [
            {
                "card": "4111111111111111",
                "role": "RECIPIENT",
                "confidence": 0.96,
                "evidence": "Asosiy karta 4111 1111 1111 1111.",
                "reason": "Pul shu kartaga yuborilishi aytilgan.",
            }
        ],
        "needs_review": False,
    }
    monkeypatch.setattr(
        "bankxat.semantic.urlopen",
        lambda *_args, **_kwargs: FakeResponse({"message": {"content": json.dumps(ai_content)}}),
    )

    assistant = SemanticAssistant(AiConfig(enabled=True))
    result = apply_semantic_roles(candidates, assistant.analyze([page], candidates))

    assert result[0].role is Role.RECIPIENT
    assert result[0].ai_assisted is True
    assert result[0].role_source == "ai_assistant"
    assert result[1].role is Role.RECIPIENT
    assert result[1].ai_assisted is False


def test_ai_failure_keeps_existing_pipeline_result(monkeypatch: pytest.MonkeyPatch) -> None:
    page = ExtractedPage(
        page=1,
        source="text_layer",
        text="4111111111111111 dan 4012888888881881 ga",
    )
    candidates = apply_pair_order_roles(find_card_candidates(page))
    original_roles = [item.role for item in candidates]

    def unavailable(*_args: object, **_kwargs: object) -> FakeResponse:
        raise URLError("Ollama ishlamayapti")

    monkeypatch.setattr("bankxat.semantic.urlopen", unavailable)
    assistant = SemanticAssistant(AiConfig(enabled=True))

    first_analysis = assistant.analyze([page], candidates)
    second_analysis = assistant.analyze([page], candidates)
    analysis = assistant.analyze([page], candidates)
    result = apply_semantic_roles(candidates, analysis)

    assert first_analysis is None
    assert second_analysis is None
    assert analysis is None
    assert assistant.available is False
    assert [item.role for item in result] == original_roles
    assert all(item.ai_assisted is False for item in result)


def test_ai_rejects_card_or_evidence_not_present_in_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = ExtractedPage(page=1, source="text_layer", text="4111111111111111 kartasiga")
    candidates = find_card_candidates(page)
    ai_content = {
        "cards": [
            {
                "card": "9999999999999999",
                "role": "RECIPIENT",
                "confidence": 0.99,
                "evidence": "matnda yo'q dalil",
                "reason": "Noto'g'ri javob",
            }
        ],
        "needs_review": False,
    }
    monkeypatch.setattr(
        "bankxat.semantic.urlopen",
        lambda *_args, **_kwargs: FakeResponse({"message": {"content": json.dumps(ai_content)}}),
    )

    analysis = SemanticAssistant(AiConfig(enabled=True)).analyze([page], candidates)

    assert analysis is not None
    assert analysis.cards == []


def test_rule_and_ai_disagreement_is_sent_to_review(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = "Jo'natuvchi karta: 4111 1111 1111 1111."
    page = ExtractedPage(page=1, source="text_layer", text=text)
    candidates = find_card_candidates(page)
    assert candidates[0].role is Role.SENDER

    ai_content = {
        "cards": [
            {
                "card": "4111111111111111",
                "role": "RECIPIENT",
                "confidence": 0.96,
                "evidence": "Jo'natuvchi karta: 4111 1111 1111 1111.",
            }
        ],
        "needs_review": False,
    }
    monkeypatch.setattr(
        "bankxat.semantic.urlopen",
        lambda *_args, **_kwargs: FakeResponse({"message": {"content": json.dumps(ai_content)}}),
    )

    result = apply_semantic_roles(
        candidates, SemanticAssistant(AiConfig(enabled=True)).analyze([page], candidates)
    )

    assert result[0].role is Role.UNKNOWN
    assert result[0].role_source == "semantic_conflict"
    assert result[0].confidence < 0.80
