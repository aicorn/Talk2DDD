from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Language(str, Enum):
    ZH_CN = "zh-CN"
    ZH_TW = "zh-TW"
    EN = "en"
    JA = "ja"
    KO = "ko"


class Theme(str, Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


@dataclass
class UserSettings:
    """Value object representing user preferences."""

    preferred_language: Language = Language.ZH_CN
    theme: Theme = Theme.LIGHT
    notifications_enabled: bool = True
    ai_suggestions_enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "preferred_language": self.preferred_language.value,
            "theme": self.theme.value,
            "notifications_enabled": self.notifications_enabled,
            "ai_suggestions_enabled": self.ai_suggestions_enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserSettings":
        return cls(
            preferred_language=Language(data.get("preferred_language", Language.ZH_CN.value)),
            theme=Theme(data.get("theme", Theme.LIGHT.value)),
            notifications_enabled=data.get("notifications_enabled", True),
            ai_suggestions_enabled=data.get("ai_suggestions_enabled", True),
        )
