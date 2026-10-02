"""Karta nomzodlarini topish, rolini baholash va tekshirish."""

from __future__ import annotations

import re
import unicodedata

from bankxat.models import (
    Evidence,
    ExtractedPage,
    Finding,
    FindingType,
    Role,
    ValidationResult,
)
from bankxat.security import mask_card
from bankxat.validate.card import normalize_card, passes_luhn

CARD_PATTERN = re.compile(r"(?<![0-9])(?:[0-9][\s.\-]*){15}[0-9](?![0-9])")
RECIPIENT_AFTER = (
    "kartasiga",
    "kartaga",
    "hisobiga",
    "hisob raqamiga",
    "картасига",
    "на карту",
    "на счёт",
    "на счет",
)
SENDER_AFTER = (
    "kartasidan",
    "kartadan",
    "hisobidan",
    "hisob raqamidan",
    "картасидан",
    "с карты",
    "со счёта",
    "со счета",
)
RECIPIENT_LABELS = (
    "qabul qiluvchi",
    "mablag' oluvchi",
    "pul oluvchi",
    "oluvchining",
    "oluvchiga",
    "kartaga",
    "kimga",
    "beneficiary",
    "recipient",
    "получатель",
    "получателя",
    "карта получателя",
    "на карту",
    "кому",
)
SENDER_LABELS = (
    "jo'natuvchi",
    "yuboruvchi",
    "to'lovchi",
    "mablag' jo'natuvchi",
    "kartadan",
    "kimdan",
    "sender",
    "payer",
    "from card",
    "отправитель",
    "карта отправителя",
    "плательщик",
    "с карты",
    "со счёта",
    "со счета",
    "от кого",
)
RECIPIENT_ACTIONS = (
    "kelib tushdi",
    "kirim qilindi",
    "o'tkazib berildi",
    "o'tkazildi",
    "yuborildi",
    "yo'naltirildi",
    "зачислен",
    "зачислено",
    "переведен",
    "переведено",
    "поступил",
    "поступило",
)
SENDER_ACTIONS = (
    "yechib olindi",
    "yechildi",
    "chiqim qilindi",
    "hisobdan chiqarildi",
    "списан",
    "списано",
    "снято",
)


def normalize_text(text: str) -> str:
    """Matnni qidiruv uchun normallashtiradi, raqamlar tartibini saqlaydi."""

    normalized = unicodedata.normalize("NFKC", text)
    for apostrophe in ("ʻ", "’", "‘", "ʼ", "`"):
        normalized = normalized.replace(apostrophe, "'")
    return normalized


def _classify_role(text: str, start: int, end: int) -> tuple[Role, float]:
    """Karta atrofidagi yaqin va yo'nalish bildiruvchi iboralarni baholaydi."""

    spans = [(match.start(), match.end()) for match in CARD_PATTERN.finditer(text)]
    previous_end = max((span_end for _, span_end in spans if span_end <= start), default=0)
    next_start = min(
        (span_start for span_start, _ in spans if span_start >= end), default=len(text)
    )
    before = text[max(previous_end, start - 180) : start].lower()
    after = text[end : min(next_start, end + 180)].lower()
    immediate_before = before[-90:]
    immediate_after = after[:90]
    recipient_score = 0
    sender_score = 0
    if any(keyword in immediate_after for keyword in RECIPIENT_AFTER):
        recipient_score += 7
    if any(keyword in immediate_after for keyword in SENDER_AFTER):
        sender_score += 7
    if any(label in immediate_before for label in RECIPIENT_LABELS):
        recipient_score += 10
    if any(label in immediate_before for label in SENDER_LABELS):
        sender_score += 10
    if any(action in immediate_after for action in RECIPIENT_ACTIONS):
        recipient_score += 3
    if any(action in immediate_after for action in SENDER_ACTIONS):
        sender_score += 3
    if any(label in before for label in RECIPIENT_LABELS):
        recipient_score += 2
    if any(label in before for label in SENDER_LABELS):
        sender_score += 2
    difference = abs(recipient_score - sender_score)
    if recipient_score >= 5 and recipient_score > sender_score and difference >= 3:
        return Role.RECIPIENT, min(0.98, 0.80 + recipient_score * 0.02)
    if sender_score >= 5 and sender_score > recipient_score and difference >= 3:
        return Role.SENDER, min(0.98, 0.80 + sender_score * 0.02)
    return Role.UNKNOWN, 0.45


def find_card_candidates(page: ExtractedPage) -> list[Finding]:
    """Sahifadagi barcha to'liq karta nomzodlarini dalili bilan qaytaradi."""

    text = normalize_text(page.text)
    findings: list[Finding] = []
    for match in CARD_PATTERN.finditer(text):
        value = normalize_card(match.group(0))
        role, role_confidence = _classify_role(text, match.start(), match.end())
        luhn = passes_luhn(value)
        snippet_start = max(0, match.start() - 90)
        snippet_end = min(len(text), match.end() + 90)
        matching_engines = [
            engine
            for engine, engine_text in page.ocr_variants.items()
            if value in normalize_card(engine_text)
        ]
        ocr_consensus = len(matching_engines) >= 2 if page.ocr_variants else None
        auto_acceptable = luhn and role is not Role.UNKNOWN and not page.source.startswith("ocr")
        confidence = 0.94 if ocr_consensus else 0.95 if auto_acceptable else 0.65
        warnings: list[str] = []
        if not luhn:
            warnings.append("Luhn tekshiruvidan o'tmadi")
        if role is Role.UNKNOWN:
            warnings.append("Karta rolini aniq belgilab bo'lmadi")
        if page.source.startswith("ocr") and not ocr_consensus:
            warnings.append("Ikkinchi OCR bilan konsensus hali tasdiqlanmagan")
        findings.append(
            Finding(
                type=FindingType.CARD,
                value=value,
                value_masked=mask_card(value),
                role=role,
                role_confidence=role_confidence,
                role_source="context_rules" if role is not Role.UNKNOWN else "unresolved",
                confidence=confidence,
                validation=ValidationResult(
                    luhn=luhn,
                    verified_in_source=True,
                    ocr_engines_agree=ocr_consensus,
                    format_valid=len(value) == 16 and value.isdigit(),
                ),
                evidence=Evidence(
                    page=page.page,
                    snippet=text[snippet_start:snippet_end].strip(),
                    source=page.source,
                    ocr_engines=matching_engines,
                    consensus_count=len(matching_engines),
                ),
                warnings=warnings,
            )
        )
    return findings


def apply_pair_order_roles(candidates: list[Finding]) -> list[Finding]:
    """Faqat roli noma'lum kartalarga past ishonchli tartib taxminini beradi."""

    for position, candidate in enumerate(candidates, start=1):
        candidate.position = position
        if candidate.role is not Role.UNKNOWN:
            continue
        candidate.role = Role.RECIPIENT if position % 2 == 0 else Role.SENDER
        candidate.role_confidence = 0.58
        candidate.role_source = "pair_order_fallback"
        candidate.warnings.append("Rol faqat hujjatdagi tartib bo'yicha taxmin qilindi")
    return candidates
