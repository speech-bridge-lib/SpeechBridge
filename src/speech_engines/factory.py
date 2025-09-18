"""
Фабрика для создания движков распознавания речи
SOLID: Factory Pattern + Dependency Inversion Principle
"""

import logging
from typing import Dict, List, Optional, Type

from ..interfaces.speech_recognition_interface import (
    ISpeechRecognitionEngine,
    ISpeechRecognitionStrategy, 
    ISpeechRecognitionFactory,
    ITextSegmenter
)

from .sphinx_engine import SphinxEngine, SphinxStrategy, SphinxTextSegmenter
from .google_engine import GoogleEngine, GoogleStrategy
from .whisper_engine import WhisperEngine, WhisperStrategy


class SpeechEngineFactory(ISpeechRecognitionFactory):
    """
    Фабрика для создания движков распознавания речи
    SOLID: Factory Pattern + Open/Closed (легко добавить новые движки)
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        self._engine_classes: Dict[str, Type[ISpeechRecognitionEngine]] = {
            "sphinx": SphinxEngine,
            "google": GoogleEngine, 
            "whisper_tiny": lambda: WhisperEngine("tiny"),
            "whisper_base": lambda: WhisperEngine("base"),
            "whisper_small": lambda: WhisperEngine("small"),
            "whisper_medium": lambda: WhisperEngine("medium"),
            "whisper_large": lambda: WhisperEngine("large")
        }
        
        self._strategy_classes: Dict[str, Type[ISpeechRecognitionStrategy]] = {
            "sphinx": SphinxStrategy,
            "google": GoogleStrategy,
            "whisper_tiny": lambda: WhisperStrategy(WhisperEngine("tiny")),
            "whisper_base": lambda: WhisperStrategy(WhisperEngine("base")),
            "whisper_small": lambda: WhisperStrategy(WhisperEngine("small")),
            "whisper_medium": lambda: WhisperStrategy(WhisperEngine("medium")),
            "whisper_large": lambda: WhisperStrategy(WhisperEngine("large"))
        }
    
    def create_engine(self, engine_type: str) -> ISpeechRecognitionEngine:
        """Создает движок по типу"""
        if engine_type not in self._engine_classes:
            available = list(self._engine_classes.keys())
            raise ValueError(f"Неизвестный тип движка: {engine_type}. Доступны: {available}")
        
        engine_class = self._engine_classes[engine_type]
        
        try:
            if callable(engine_class):
                engine = engine_class()
            else:
                engine = engine_class(logger=self.logger)
            
            self.logger.debug(f"Создан движок: {engine_type}")
            return engine
            
        except Exception as e:
            self.logger.error(f"Ошибка создания движка {engine_type}: {e}")
            raise
    
    def create_strategy(self, engine_type: str) -> ISpeechRecognitionStrategy:
        """Создает стратегию по типу движка"""
        if engine_type not in self._strategy_classes:
            available = list(self._strategy_classes.keys())
            raise ValueError(f"Неизвестная стратегия: {engine_type}. Доступны: {available}")
        
        strategy_class = self._strategy_classes[engine_type]
        
        try:
            if callable(strategy_class):
                strategy = strategy_class()
            else:
                strategy = strategy_class()
            
            self.logger.debug(f"Создана стратегия: {engine_type}")
            return strategy
            
        except Exception as e:
            self.logger.error(f"Ошибка создания стратегии {engine_type}: {e}")
            raise
    
    def get_available_engines(self) -> List[str]:
        """Возвращает список доступных движков"""
        available = []
        
        for engine_type in self._engine_classes:
            try:
                engine = self.create_engine(engine_type)
                if engine.is_available():
                    available.append(engine_type)
                    self.logger.debug(f"✅ Движок {engine_type} доступен")
                else:
                    self.logger.debug(f"❌ Движок {engine_type} недоступен")
            except Exception as e:
                self.logger.debug(f"❌ Движок {engine_type} ошибка: {e}")
        
        return available
    
    def create_segmenter(self, segmenter_type: str = "auto") -> ITextSegmenter:
        """Создает сегментатор текста"""
        if segmenter_type == "sphinx" or segmenter_type == "auto":
            return SphinxTextSegmenter(logger=self.logger)
        else:
            raise ValueError(f"Неизвестный тип сегментатора: {segmenter_type}")
    
    def get_recommended_engine(self, 
                             quality_priority: bool = True,
                             speed_priority: bool = False,
                             offline_priority: bool = False) -> Optional[str]:
        """
        Возвращает рекомендуемый движок на основе приоритетов
        
        Args:
            quality_priority: Приоритет качества
            speed_priority: Приоритет скорости  
            offline_priority: Приоритет работы без интернета
        """
        available = self.get_available_engines()
        
        if not available:
            return None
        
        # Рейтинги движков по критериям
        quality_rating = {
            "whisper_large": 10, "whisper_medium": 9, "whisper_small": 8,
            "whisper_base": 7, "whisper_tiny": 6, "google": 8, "sphinx": 4
        }
        
        speed_rating = {
            "sphinx": 10, "whisper_tiny": 9, "whisper_base": 8,
            "google": 7, "whisper_small": 6, "whisper_medium": 4, "whisper_large": 2
        }
        
        offline_rating = {
            "sphinx": 10, "whisper_tiny": 10, "whisper_base": 10,
            "whisper_small": 10, "whisper_medium": 10, "whisper_large": 10, "google": 0
        }
        
        # Вычисляем общий рейтинг
        scores = {}
        for engine in available:
            score = 0
            
            if quality_priority:
                score += quality_rating.get(engine, 0) * 3
            if speed_priority:
                score += speed_rating.get(engine, 0) * 2
            if offline_priority:
                score += offline_rating.get(engine, 0) * 2
            
            # Базовый рейтинг если нет приоритетов
            if not any([quality_priority, speed_priority, offline_priority]):
                score = quality_rating.get(engine, 0)
            
            scores[engine] = score
        
        # Возвращаем движок с наивысшим рейтингом
        best_engine = max(scores.keys(), key=lambda k: scores[k])
        
        self.logger.info(f"Рекомендуемый движок: {best_engine} (рейтинг: {scores[best_engine]})")
        return best_engine


class SpeechEngineSelector:
    """
    Селектор движков с умной логикой выбора
    SOLID: Single Responsibility - только выбор движков
    """
    
    def __init__(self, factory: SpeechEngineFactory = None):
        self.factory = factory or SpeechEngineFactory()
        self.logger = logging.getLogger(__name__)
    
    def select_best_engine(self, user_preference: Optional[str] = None,
                          audio_duration: Optional[float] = None,
                          quality_needed: bool = True) -> str:
        """
        Выбирает лучший движок на основе контекста
        
        Args:
            user_preference: Предпочтение пользователя
            audio_duration: Длительность аудио (для оптимизации)
            quality_needed: Нужно ли высокое качество
        """
        available = self.factory.get_available_engines()
        
        if not available:
            raise RuntimeError("Нет доступных движков распознавания речи")
        
        # Если пользователь указал предпочтение и оно доступно
        if user_preference and user_preference in available:
            self.logger.info(f"Используем предпочтение пользователя: {user_preference}")
            return user_preference
        
        # Умная логика выбора
        if audio_duration and audio_duration < 30:
            # Короткое аудио - приоритет скорости
            engine = self.factory.get_recommended_engine(
                speed_priority=True, 
                quality_priority=quality_needed
            )
        elif audio_duration and audio_duration > 300:
            # Длинное аудио - баланс скорости и качества
            engine = self.factory.get_recommended_engine(
                speed_priority=True, 
                quality_priority=quality_needed
            )
        else:
            # Средняя длительность - приоритет качества
            engine = self.factory.get_recommended_engine(
                quality_priority=quality_needed
            )
        
        if engine and engine in available:
            self.logger.info(f"Автоматически выбран движок: {engine}")
            return engine
        
        # Fallback - первый доступный
        fallback = available[0]
        self.logger.info(f"Fallback на первый доступный движок: {fallback}")
        return fallback