"""
Адаптер для интеграции старого VideoTranslator с новой SOLID архитектурой
Позволяет постепенно перейти на модульную систему
"""

import logging
from typing import Callable, Optional
from pathlib import Path

from video_translator_solid import VideoTranslatorSOLID, TranslationConfig, TranslationResult
from interfaces.video_output_interface import VideoOutputFormat


class VideoTranslatorAdapter:
    """
    Адаптер для совместимости старого API с новой SOLID архитектурой
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        self.solid_translator = VideoTranslatorSOLID(logger=self.logger)
        
    def translate_video(self, 
                       video_path: str, 
                       output_path: str, 
                       progress_callback: Optional[Callable] = None,
                       speech_engine: str = 'auto',
                       output_format: str = 'TRANSLATION_ONLY') -> bool:
        """
        Старый API для обратной совместимости
        """
        try:
            self.logger.info(f"🔄 Адаптер: перевод {video_path} -> {output_path}")
            self.logger.info(f"📋 Настройки: engine={speech_engine}, format={output_format}")
            
            # Конвертируем параметры
            config = self._create_config(speech_engine, output_format)
            
            # Создаем callback-обертку
            def adapted_callback(stage: str, progress: int):
                if progress_callback:
                    progress_callback(stage, progress)
            
            # Имитируем прогресс для старого API
            if progress_callback:
                adapted_callback("Инициализация SOLID архитектуры", 5)
            
            # Вызываем новый SOLID переводчик
            result = self.solid_translator.translate_video(
                video_path, output_path, config
            )
            
            # Имитируем финальный прогресс
            if progress_callback:
                if result.success:
                    adapted_callback("Перевод завершен успешно", 100)
                else:
                    adapted_callback(f"Ошибка: {result.error_message}", 0)
            
            return result.success
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка в адаптере: {e}")
            if progress_callback:
                progress_callback(f"Критическая ошибка: {str(e)}", 0)
            return False
    
    def _create_config(self, speech_engine: str, output_format: str) -> TranslationConfig:
        """Создает конфигурацию для SOLID архитектуры"""
        
        # Конвертируем строковый формат в enum
        format_mapping = {
            'TRANSLATION_ONLY': VideoOutputFormat.TRANSLATION_ONLY,
            'SUBTITLES_ONLY': VideoOutputFormat.SUBTITLES_ONLY,
            'TRANSLATION_WITH_SUBTITLES': VideoOutputFormat.TRANSLATION_WITH_SUBTITLES
        }
        
        solid_format = format_mapping.get(output_format, VideoOutputFormat.TRANSLATION_ONLY)
        
        # Определяем предпочтения по движку
        preferred_engine = None if speech_engine == 'auto' else speech_engine
        
        config = TranslationConfig(
            preferred_sr_engine=preferred_engine,
            source_language="en",
            target_language="ru",
            output_format=solid_format,
            preserve_original_audio=False,
            prioritize_quality=True,
            prioritize_speed=False,
            offline_mode=False,
            custom_segmentation=True,
            max_segment_length=400
        )
        
        self.logger.info(f"📋 Создана SOLID конфигурация: {config}")
        return config
    
    def validate_video_file(self, video_path: str) -> dict:
        """Валидация видеофайла"""
        try:
            from moviepy.editor import VideoFileClip
            
            video_file = Path(video_path)
            if not video_file.exists():
                return {
                    'valid': False,
                    'errors': ['Файл не найден'],
                    'info': {}
                }
            
            # Проверяем видео
            try:
                with VideoFileClip(video_path) as clip:
                    duration = clip.duration
                    fps = clip.fps
                    size = clip.size
                    has_audio = clip.audio is not None
                
                info = {
                    'duration': duration,
                    'fps': fps,
                    'resolution': f"{size[0]}x{size[1]}",
                    'has_audio': has_audio,
                    'file_size_mb': video_file.stat().st_size / (1024 * 1024)
                }
                
                errors = []
                if duration > 3600:  # > 1 час
                    errors.append('Видео слишком длинное (>1 часа)')
                
                if not has_audio:
                    errors.append('Видео не содержит аудиодорожку')
                
                return {
                    'valid': len(errors) == 0,
                    'errors': errors,
                    'info': info
                }
                
            except Exception as e:
                return {
                    'valid': False,
                    'errors': [f'Ошибка чтения видео: {str(e)}'],
                    'info': {}
                }
                
        except Exception as e:
            self.logger.error(f"Ошибка валидации: {e}")
            return {
                'valid': False,
                'errors': [f'Критическая ошибка валидации: {str(e)}'],
                'info': {}
            }
    
    def get_available_engines(self) -> list:
        """Получение доступных движков распознавания"""
        return self.solid_translator.get_available_engines()
    
    def get_available_output_formats(self) -> list:
        """Получение доступных форматов вывода"""
        formats = self.solid_translator.get_available_output_formats()
        return [fmt.value for fmt in formats]
    
    def get_translator_status(self) -> dict:
        """Получение статуса переводчика"""
        status = self.solid_translator.get_system_status()
        
        return {
            'type': 'SOLID Modular Architecture',
            'version': '2.0',
            'engines': status['speech_engines'],
            'formats': status['output_formats'],
            'components': status['components']
        }