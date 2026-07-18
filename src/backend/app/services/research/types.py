"""Value objects shared by the AI strategy research workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schemas.strategy import AIStrategyDraft


@dataclass(frozen=True)
class StrategyImprovement:
    """A candidate strategy plus the notes that explain the change."""

    draft: AIStrategyDraft
    notes: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OutOfSampleWindow:
    """The train and validation time windows for a research run."""

    train_start: str
    train_end: str
    validation_start: str
    validation_end: str

    def as_dict(self) -> dict[str, str]:
        """Return a serializable representation used by research metadata."""

        return {
            "train_start": self.train_start,
            "train_end": self.train_end,
            "validation_start": self.validation_start,
            "validation_end": self.validation_end,
        }
