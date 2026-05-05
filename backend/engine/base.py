from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class WordTranslation:
    source: str
    translated: str
    found: bool = True


@dataclass
class TranslationResult:
    source_text: str
    translated_text: str
    source_language: str
    confidence: float = 0.0
    word_translations: list[WordTranslation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    engine: str = ""


class TranslationEngine(ABC):
    @abstractmethod
    def translate(self, text: str, source_language: str) -> TranslationResult:
        ...

    @abstractmethod
    def reload(self) -> None:
        """Reload internal data (e.g. dictionary cache) without restart."""
        ...
