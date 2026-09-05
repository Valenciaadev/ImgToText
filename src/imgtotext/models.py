from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from uuid import uuid4


class DescriptionMode(StrEnum):
    GENERAL = "general"
    ACCESSIBILITY = "accessibility"
    CATALOG = "catalog"
    VISIBLE_TEXT = "visible_text"


class DescriptionLength(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class ImageStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class DescriptionResult:
    description: str
    visible_text: str = ""
    uncertainty: str = ""


@dataclass(slots=True)
class ImageItem:
    path: Path
    display_name: str
    source_name: str
    sha256: str
    width: int
    height: int
    id: str = field(default_factory=lambda: uuid4().hex)
    status: ImageStatus = ImageStatus.PENDING
    description: str = ""
    visible_text: str = ""
    uncertainty: str = ""
    error: str = ""

    def as_export_dict(self, position: int) -> dict[str, object]:
        data = asdict(self)
        data["path"] = str(self.path)
        data["status"] = self.status.value
        data["position"] = position
        return data


@dataclass(slots=True)
class GenerationOptions:
    mode: DescriptionMode = DescriptionMode.GENERAL
    length: DescriptionLength = DescriptionLength.MEDIUM
    language: str = "Espanol"
    context: str = ""
    model: str = "gemini-3.6-flash"
    thinking_level: str = "low"

