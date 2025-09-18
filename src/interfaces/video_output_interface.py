"""
Интерфейсы для форматов вывода видео
SOLID: Interface Segregation + Strategy Pattern
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class VideoOutputFormat(Enum):
    """Форматы вывода видео"""
    TRANSLATION_ONLY = "translation_only"    # Только с переводом аудио
    SUBTITLES_ONLY = "subtitles_only"       # Только с субтитрами 
    TRANSLATION_WITH_SUBTITLES = "both"     # И перевод, и субтитры


@dataclass
class VideoOutputConfig:
    """Конфигурация для вывода видео"""
    output_format: VideoOutputFormat
    subtitle_language: str = "ru"
    subtitle_style: Dict[str, Any] = None
    audio_language: str = "ru"
    preserve_original_audio: bool = False
    
    def __post_init__(self):
        if self.subtitle_style is None:
            self.subtitle_style = {
                "font_family": "Arial",
                "font_size": 24,
                "font_color": "white",
                "background_color": "black",
                "position": "bottom"
            }


@dataclass
class ProcessedVideo:
    """Результат обработки видео"""
    output_path: str
    original_path: str
    output_format: VideoOutputFormat
    duration: float
    file_size_mb: float
    has_audio: bool
    has_subtitles: bool
    subtitle_files: List[str]
    processing_time: float
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class IVideoProcessor(ABC):
    """
    Интерфейс для обработки видео
    SOLID: Single Responsibility - только обработка видео
    """
    
    @abstractmethod
    def process_video(
        self,
        input_video_path: str,
        translated_segments: List[Dict[str, Any]],
        output_path: str,
        config: VideoOutputConfig
    ) -> ProcessedVideo:
        """
        Обрабатывает видео согласно конфигурации
        
        Args:
            input_video_path: Путь к исходному видео
            translated_segments: Переведенные сегменты с аудио
            output_path: Путь для сохранения результата
            config: Конфигурация обработки
            
        Returns:
            ProcessedVideo с информацией о результате
        """
        pass


class ISubtitleGenerator(ABC):
    """
    Интерфейс для генерации субтитров
    SOLID: Interface Segregation - только субтитры
    """
    
    @abstractmethod
    def generate_srt(
        self,
        segments: List[Dict[str, Any]],
        output_path: str,
        language: str = "ru"
    ) -> str:
        """Генерирует SRT файл"""
        pass
    
    @abstractmethod
    def generate_vtt(
        self,
        segments: List[Dict[str, Any]], 
        output_path: str,
        language: str = "ru"
    ) -> str:
        """Генерирует VTT файл"""
        pass


class IVideoOutputStrategy(ABC):
    """
    Стратегия для различных форматов вывода
    SOLID: Strategy Pattern + Open/Closed Principle
    """
    
    @abstractmethod
    def create_output(
        self,
        input_video_path: str,
        translated_segments: List[Dict[str, Any]],
        output_path: str,
        config: VideoOutputConfig
    ) -> ProcessedVideo:
        """Создает видео в определенном формате"""
        pass
    
    @abstractmethod
    def get_supported_format(self) -> VideoOutputFormat:
        """Возвращает поддерживаемый формат"""
        pass


class IVideoOutputFactory(ABC):
    """
    Фабрика для создания стратегий вывода
    SOLID: Factory Pattern + Dependency Inversion
    """
    
    @abstractmethod
    def create_strategy(self, output_format: VideoOutputFormat) -> IVideoOutputStrategy:
        """Создает стратегию по формату"""
        pass
    
    @abstractmethod
    def get_available_formats(self) -> List[VideoOutputFormat]:
        """Возвращает доступные форматы"""
        pass