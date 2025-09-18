"""
Интерфейсы для модулей распознавания речи
SOLID: Interface Segregation Principle
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SpeechSegment:
    """Результат распознавания сегмента речи"""
    start_time: float
    end_time: float
    text: str
    confidence: float
    language: str = "en"
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass  
class SpeechRecognitionResult:
    """Результат распознавания всего аудио"""
    segments: List[SpeechSegment]
    full_text: str
    total_duration: float
    engine_used: str
    processing_time: float
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ISpeechRecognitionEngine(ABC):
    """
    Интерфейс для движков распознавания речи
    SOLID: Interface Segregation - четко определенная ответственность
    """
    
    @abstractmethod
    def get_engine_name(self) -> str:
        """Возвращает имя движка"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Проверяет доступность движка"""
        pass
    
    @abstractmethod
    def recognize_audio(self, audio_path: str, language: str = "en") -> SpeechRecognitionResult:
        """
        Распознает речь из аудио файла
        
        Args:
            audio_path: Путь к аудио файлу
            language: Код языка (en, ru, etc.)
            
        Returns:
            SpeechRecognitionResult с результатами распознавания
        """
        pass
    
    @abstractmethod
    def get_supported_languages(self) -> List[str]:
        """Возвращает список поддерживаемых языков"""
        pass


class ITextSegmenter(ABC):
    """
    Интерфейс для сегментации текста для перевода
    SOLID: Single Responsibility - только сегментация текста
    """
    
    @abstractmethod
    def segment_text(self, text: str, max_segment_length: int = 400) -> List[str]:
        """
        Разбивает текст на сегменты оптимальной длины для перевода
        
        Args:
            text: Исходный текст
            max_segment_length: Максимальная длина сегмента
            
        Returns:
            Список текстовых сегментов
        """
        pass


class ISpeechRecognitionStrategy(ABC):
    """
    Интерфейс для стратегии распознавания речи
    SOLID: Strategy Pattern + Open/Closed Principle
    """
    
    @abstractmethod
    def recognize_with_segmentation(
        self, 
        audio_path: str, 
        language: str = "en",
        segmenter: Optional[ITextSegmenter] = None
    ) -> SpeechRecognitionResult:
        """
        Распознает речь с возможной сегментацией для улучшения качества перевода
        
        Args:
            audio_path: Путь к аудио файлу
            language: Код языка
            segmenter: Опциональный сегментатор текста
            
        Returns:
            SpeechRecognitionResult с оптимизированной сегментацией
        """
        pass


class ISpeechRecognitionFactory(ABC):
    """
    Фабрика для создания движков распознавания речи
    SOLID: Factory Pattern + Dependency Inversion
    """
    
    @abstractmethod
    def create_engine(self, engine_type: str) -> ISpeechRecognitionEngine:
        """Создает движок по типу"""
        pass
    
    @abstractmethod
    def get_available_engines(self) -> List[str]:
        """Возвращает список доступных движков"""
        pass