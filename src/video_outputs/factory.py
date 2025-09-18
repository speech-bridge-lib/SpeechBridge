"""
Фабрика для создания стратегий вывода видео
SOLID: Factory Pattern + Dependency Inversion Principle
"""

import logging
from typing import List, Dict

from ..interfaces.video_output_interface import (
    IVideoOutputStrategy,
    IVideoOutputFactory,
    VideoOutputFormat
)

from .strategies import (
    TranslationOnlyStrategy,
    SubtitlesOnlyStrategy, 
    TranslationWithSubtitlesStrategy,
    SubtitleGenerator
)


class VideoOutputFactory(IVideoOutputFactory):
    """
    Фабрика для создания стратегий вывода видео
    SOLID: Factory Pattern + Open/Closed (легко добавить новые форматы)
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        self.subtitle_generator = SubtitleGenerator(logger=self.logger)
        
        # Регистрируем доступные стратегии
        self._strategies = {
            VideoOutputFormat.TRANSLATION_ONLY: TranslationOnlyStrategy,
            VideoOutputFormat.SUBTITLES_ONLY: SubtitlesOnlyStrategy,
            VideoOutputFormat.TRANSLATION_WITH_SUBTITLES: TranslationWithSubtitlesStrategy
        }
    
    def create_strategy(self, output_format: VideoOutputFormat) -> IVideoOutputStrategy:
        """Создает стратегию по формату вывода"""
        if output_format not in self._strategies:
            available = list(self._strategies.keys())
            raise ValueError(f"Неподдерживаемый формат вывода: {output_format}. Доступны: {available}")
        
        strategy_class = self._strategies[output_format]
        
        try:
            if output_format == VideoOutputFormat.SUBTITLES_ONLY:
                strategy = strategy_class(
                    subtitle_generator=self.subtitle_generator,
                    logger=self.logger
                )
            elif output_format == VideoOutputFormat.TRANSLATION_WITH_SUBTITLES:
                translation_strategy = TranslationOnlyStrategy(logger=self.logger)
                subtitles_strategy = SubtitlesOnlyStrategy(
                    subtitle_generator=self.subtitle_generator,
                    logger=self.logger
                )
                strategy = strategy_class(
                    translation_strategy=translation_strategy,
                    subtitles_strategy=subtitles_strategy,
                    logger=self.logger
                )
            else:
                strategy = strategy_class(logger=self.logger)
            
            self.logger.debug(f"Создана стратегия вывода: {output_format}")
            return strategy
            
        except Exception as e:
            self.logger.error(f"Ошибка создания стратегии {output_format}: {e}")
            raise
    
    def get_available_formats(self) -> List[VideoOutputFormat]:
        """Возвращает список доступных форматов"""
        return list(self._strategies.keys())
    
    def get_format_description(self, output_format: VideoOutputFormat) -> str:
        """Возвращает описание формата для пользователя"""
        descriptions = {
            VideoOutputFormat.TRANSLATION_ONLY: "Только перевод аудио (без субтитров)",
            VideoOutputFormat.SUBTITLES_ONLY: "Оригинальное аудио + субтитры на русском и английском",
            VideoOutputFormat.TRANSLATION_WITH_SUBTITLES: "Перевод аудио + субтитры (полный пакет)"
        }
        return descriptions.get(output_format, "Неизвестный формат")
    
    def get_format_recommendations(self) -> Dict[str, VideoOutputFormat]:
        """Возвращает рекомендации по использованию форматов"""
        return {
            "learning": VideoOutputFormat.SUBTITLES_ONLY,  # Для изучения языка
            "accessibility": VideoOutputFormat.TRANSLATION_WITH_SUBTITLES,  # Максимальная доступность
            "clean": VideoOutputFormat.TRANSLATION_ONLY,  # Чистый просмотр
            "professional": VideoOutputFormat.TRANSLATION_WITH_SUBTITLES,  # Профессиональное использование
            "default": VideoOutputFormat.TRANSLATION_ONLY  # По умолчанию
        }