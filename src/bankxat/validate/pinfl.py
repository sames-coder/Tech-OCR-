"""PINFL/JShShIR formatini rasmiy checksum'siz tekshirish."""

from __future__ import annotations

from datetime import datetime


def is_valid_pinfl_format(value: str) -> bool:
    """PINFL uzunligi, jins/asr kodi va sana qismini tekshiradi."""

    if len(value) != 14 or not value.isdigit() or value[0] not in "123456":
        return False
    try:
        datetime.strptime(value[1:7], "%d%m%y")
    except ValueError:
        return False
    return True
