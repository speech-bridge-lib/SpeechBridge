"""
Главный оркестратор видео переводчика по принципам SOLID
SOLID: Dependency Inversion + Single Responsibility + Open/Closed
"""

import logging
import time
from typing import Optional, Dict, Any, List
from pathlib import Path
from dataclasses import dataclass

from interfaces.speech_recognition_interface import (
    ISpeechRecognitionStrategy, 
    ITextSegmenter,
    SpeechRecognitionResult
)
from interfaces.video_output_interface import (
    IVideoOutputStrategy,
    VideoOutputFormat,
    VideoOutputConfig,
    ProcessedVideo
)
from speech_engines.factory import SpeechEngineFactory, SpeechEngineSelector
from video_outputs.factory import VideoOutputFactory
from core.audio_processor import AudioProcessor
from core.speech_synthesizer import SpeechSynthesizer
from translator_compat import translate_text


@dataclass
class TranslationConfig:
    """Конфигурация для перевода видео"""
    # Speech Recognition
    preferred_sr_engine: Optional[str] = None
    source_language: str = "en"
    target_language: str = "ru"
    
    # Video Output
    output_format: VideoOutputFormat = VideoOutputFormat.TRANSLATION_ONLY
    preserve_original_audio: bool = False
    
    # Quality Settings
    prioritize_quality: bool = True
    prioritize_speed: bool = False
    offline_mode: bool = False
    
    # Advanced
    custom_segmentation: bool = True
    max_segment_length: int = 400


@dataclass
class TranslationResult:
    """Результат перевода видео"""
    success: bool
    output_video: Optional[ProcessedVideo]
    speech_result: Optional[SpeechRecognitionResult]
    error_message: Optional[str]
    processing_time: float
    stats: Dict[str, Any]


class VideoTranslatorSOLID:
    """
    Главный класс переводчика видео по принципам SOLID
    
    SOLID принципы:
    - Single Responsibility: Только координация процесса перевода
    - Open/Closed: Расширяется новыми движками через фабрики
    - Liskov Substitution: Все движки взаимозаменяемы через интерфейсы  
    - Interface Segregation: Четкие интерфейсы для каждой задачи
    - Dependency Inversion: Зависит от абстракций, не от конкретных классов
    """
    
    def __init__(self,
                 speech_factory: Optional[SpeechEngineFactory] = None,
                 video_factory: Optional[VideoOutputFactory] = None,
                 audio_processor: Optional[AudioProcessor] = None,
                 speech_synthesizer: Optional[SpeechSynthesizer] = None,
                 logger: Optional[logging.Logger] = None):
        """
        Dependency Injection - все зависимости передаются извне
        """
        self.speech_factory = speech_factory or SpeechEngineFactory()
        self.video_factory = video_factory or VideoOutputFactory()
        self.engine_selector = SpeechEngineSelector(self.speech_factory)
        self.audio_processor = audio_processor or AudioProcessor()
        self.speech_synthesizer = speech_synthesizer or SpeechSynthesizer()
        self.logger = logger or logging.getLogger(__name__)
        
        self.logger.info("VideoTranslatorSOLID инициализирован с модульной архитектурой")
    
    def get_available_engines(self) -> List[str]:
        """Возвращает доступные движки распознавания"""
        return self.speech_factory.get_available_engines()
    
    def get_available_output_formats(self) -> List[VideoOutputFormat]:
        """Возвращает доступные форматы вывода"""
        return self.video_factory.get_available_formats()
    
    def get_format_descriptions(self) -> Dict[VideoOutputFormat, str]:
        """Возвращает описания форматов для UI"""
        formats = self.get_available_output_formats()
        return {fmt: self.video_factory.get_format_description(fmt) for fmt in formats}
    
    def translate_video(self, 
                       input_video_path: str,
                       output_video_path: str, 
                       config: TranslationConfig) -> TranslationResult:
        """
        Главный метод перевода видео
        
        SOLID: Single Responsibility - только координирует процесс
        """
        start_time = time.time()
        
        try:
            self.logger.info(f"🎬 Начало перевода видео: {input_video_path}")
            self.logger.info(f"📋 Конфигурация: SR={config.preferred_sr_engine}, "
                           f"Формат={config.output_format}, Качество={config.prioritize_quality}")
            
            # 1. Извлекаем аудио
            audio_path = self._extract_audio(input_video_path)
            
            # 2. Выбираем оптимальный движок распознавания
            selected_engine = self._select_speech_engine(config, audio_path)
            
            # 3. Распознаем речь с сегментацией
            speech_result = self._recognize_speech(audio_path, selected_engine, config)
            
            # 4. Переводим и синтезируем речь
            translated_segments = self._translate_and_synthesize(speech_result, config)
            
            # 5. Создаем финальное видео в нужном формате
            output_video = self._create_output_video(
                input_video_path, translated_segments, output_video_path, config
            )
            
            processing_time = time.time() - start_time
            
            result = TranslationResult(
                success=True,
                output_video=output_video,
                speech_result=speech_result,
                error_message=None,
                processing_time=processing_time,
                stats={
                    "engine_used": selected_engine,
                    "segments_processed": len(translated_segments),
                    "output_format": config.output_format,
                    "has_subtitles": output_video.has_subtitles,
                    "file_size_mb": output_video.file_size_mb
                }
            )
            
            self.logger.info(f"✅ Перевод завершен успешно за {processing_time:.1f}s")
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = str(e)
            
            self.logger.error(f"❌ Ошибка перевода: {error_msg}")
            
            return TranslationResult(
                success=False,
                output_video=None,
                speech_result=None,
                error_message=error_msg,
                processing_time=processing_time,
                stats={"error": True}
            )
    
    def _extract_audio(self, video_path: str) -> str:
        """Извлекает аудио из видео"""
        self.logger.info("🎵 Извлечение аудио...")
        return self.audio_processor.extract_audio_from_video(video_path)
    
    def _select_speech_engine(self, config: TranslationConfig, audio_path: str) -> str:
        """
        Выбирает оптимальный движок распознавания
        
        SOLID: Dependency Inversion - использует абстракцию селектора
        """
        # Определяем длительность аудио для оптимизации
        from pydub import AudioSegment
        audio = AudioSegment.from_file(audio_path)
        duration = len(audio) / 1000.0
        
        selected = self.engine_selector.select_best_engine(
            user_preference=config.preferred_sr_engine,
            audio_duration=duration,
            quality_needed=config.prioritize_quality
        )
        
        self.logger.info(f"🎯 Выбран движок: {selected} (длительность: {duration:.1f}s)")
        return selected
    
    def _recognize_speech(self, 
                         audio_path: str, 
                         engine_name: str,
                         config: TranslationConfig) -> SpeechRecognitionResult:
        """
        Распознает речь с оптимальной сегментацией
        
        SOLID: Open/Closed - новые движки добавляются без изменения кода
        """
        self.logger.info(f"🎤 Распознавание речи через {engine_name}...")
        
        # Создаем стратегию распознавания
        strategy = self.speech_factory.create_strategy(engine_name)
        
        # Создаем сегментатор если нужна сегментация
        segmenter = None
        if config.custom_segmentation:
            segmenter = self.speech_factory.create_segmenter("auto")
        
        # Распознаем с сегментацией
        result = strategy.recognize_with_segmentation(
            audio_path, 
            config.source_language,
            segmenter
        )
        
        self.logger.info(f"✅ Распознано: {len(result.segments)} сегментов, "
                        f"'{result.full_text[:50]}...' за {result.processing_time:.1f}s")
        
        return result
    
    def _translate_and_synthesize(self, 
                                speech_result: SpeechRecognitionResult,
                                config: TranslationConfig) -> List[Dict[str, Any]]:
        """Переводит и синтезирует каждый сегмент"""
        self.logger.info(f"🌍 Перевод и синтез {len(speech_result.segments)} сегментов...")
        
        translated_segments = []
        
        for i, segment in enumerate(speech_result.segments):
            if not segment.text.strip():
                continue
            
            self.logger.debug(f"Сегмент {i+1}: '{segment.text[:30]}...'")
            
            # Переводим текст
            translated_text = translate_text(
                segment.text, 
                config.source_language, 
                config.target_language
            )
            
            # Синтезируем речь
            audio_path = None
            if config.output_format in [VideoOutputFormat.TRANSLATION_ONLY, 
                                      VideoOutputFormat.TRANSLATION_WITH_SUBTITLES]:
                audio_path = self.speech_synthesizer.synthesize_speech(
                    translated_text, 
                    config.target_language
                )
            
            segment_data = {
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "original_text": segment.text,
                "translated_text": translated_text,
                "translated_audio_path": audio_path,
                "confidence": segment.confidence,
                "language": segment.language,
                "metadata": segment.metadata
            }
            
            translated_segments.append(segment_data)
        
        self.logger.info(f"✅ Обработано {len(translated_segments)} сегментов")
        return translated_segments
    
    def _create_output_video(self,
                            input_video_path: str,
                            translated_segments: List[Dict[str, Any]], 
                            output_path: str,
                            config: TranslationConfig) -> ProcessedVideo:
        """
        Создает финальное видео в нужном формате
        
        SOLID: Strategy Pattern - формат определяет стратегию
        """
        self.logger.info(f"🎬 Создание видео в формате: {config.output_format}")
        
        # Создаем стратегию для нужного формата
        strategy = self.video_factory.create_strategy(config.output_format)
        
        # Создаем конфигурацию вывода
        output_config = VideoOutputConfig(
            output_format=config.output_format,
            subtitle_language=config.target_language,
            audio_language=config.target_language,
            preserve_original_audio=config.preserve_original_audio
        )
        
        # Создаем видео
        result = strategy.create_output(
            input_video_path,
            translated_segments, 
            output_path,
            output_config
        )
        
        return result
    
    def get_system_status(self) -> Dict[str, Any]:
        """Возвращает статус системы для диагностики"""
        available_engines = self.get_available_engines()
        available_formats = self.get_available_output_formats()
        
        return {
            "speech_engines": {
                "available": available_engines,
                "total": len(available_engines),
                "recommended": self.engine_selector.factory.get_recommended_engine(quality_priority=True)
            },
            "output_formats": {
                "available": [fmt.value for fmt in available_formats],
                "descriptions": {fmt.value: self.video_factory.get_format_description(fmt) 
                              for fmt in available_formats}
            },
            "components": {
                "audio_processor": self.audio_processor is not None,
                "speech_synthesizer": self.speech_synthesizer is not None,
                "speech_factory": len(available_engines) > 0,
                "video_factory": len(available_formats) > 0
            }
        }