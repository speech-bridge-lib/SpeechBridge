"""
Google Speech API движок
SOLID: Single Responsibility + Open/Closed Principle
"""

import logging
import time
from typing import List, Dict, Any
from pathlib import Path

from ..interfaces.speech_recognition_interface import (
    ISpeechRecognitionEngine, 
    SpeechSegment, 
    SpeechRecognitionResult,
    ISpeechRecognitionStrategy,
    ITextSegmenter
)


class GoogleEngine(ISpeechRecognitionEngine):
    """
    Google Speech API движок
    SOLID: Single Responsibility - только Google API распознавание
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        self._available = None
    
    def get_engine_name(self) -> str:
        return "google"
    
    def is_available(self) -> bool:
        if self._available is None:
            try:
                import speech_recognition as sr
                import os
                
                # Проверяем наличие API ключа
                api_key = os.getenv('GOOGLE_SPEECH_API_KEY')
                if not api_key:
                    self._available = False
                    return False
                
                # Тестовый запрос
                r = sr.Recognizer()
                test_audio_path = Path(__file__).parent.parent.parent / "test_audio.wav"
                if test_audio_path.exists():
                    with sr.AudioFile(str(test_audio_path)) as source:
                        audio = r.record(source, duration=1)
                    r.recognize_google(audio, key=api_key)
                
                self._available = True
            except Exception as e:
                self.logger.debug(f"Google API недоступен: {e}")
                self._available = False
        
        return self._available
    
    def get_supported_languages(self) -> List[str]:
        return ["en-US", "ru-RU", "de-DE", "fr-FR", "es-ES", "it-IT", "ja-JP", "ko-KR", "zh-CN"]
    
    def recognize_audio(self, audio_path: str, language: str = "en") -> SpeechRecognitionResult:
        """Распознает аудио через Google Speech API"""
        start_time = time.time()
        
        try:
            import speech_recognition as sr
            import os
            
            api_key = os.getenv('GOOGLE_SPEECH_API_KEY')
            if not api_key:
                raise ValueError("GOOGLE_SPEECH_API_KEY не найден")
            
            recognizer = sr.Recognizer()
            
            # Оптимизированные настройки для Google API
            recognizer.energy_threshold = 300
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold = 0.8
            recognizer.operation_timeout = 10
            
            with sr.AudioFile(audio_path) as source:
                self.logger.debug("Подстройка под фоновый шум...")
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = recognizer.record(source)
            
            # Конвертируем код языка для Google API
            google_lang = self._convert_language_code(language)
            
            self.logger.debug(f"Запуск Google API распознавания (язык: {google_lang})...")
            text = recognizer.recognize_google(
                audio_data, 
                key=api_key, 
                language=google_lang,
                show_all=False  # Можно установить True для получения альтернатив
            )
            
            if not text:
                text = ""
            
            # Получаем длительность аудио
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            duration = len(audio) / 1000.0
            
            # Google API не дает временные метки в базовой версии
            segment = SpeechSegment(
                start_time=0.0,
                end_time=duration,
                text=text,
                confidence=0.95,  # Google API обычно дает высокую точность
                language=language,
                metadata={
                    "engine": "google",
                    "google_language": google_lang,
                    "api_used": True
                }
            )
            
            processing_time = time.time() - start_time
            
            result = SpeechRecognitionResult(
                segments=[segment],
                full_text=text,
                total_duration=duration,
                engine_used="google",
                processing_time=processing_time,
                metadata={
                    "api_language": google_lang,
                    "energy_threshold": recognizer.energy_threshold
                }
            )
            
            self.logger.info(f"Google API успешно: '{text[:50]}...' за {processing_time:.1f}s")
            return result
            
        except Exception as e:
            self.logger.error(f"Ошибка Google API: {e}")
            raise
    
    def _convert_language_code(self, lang: str) -> str:
        """Конвертирует коды языков для Google API"""
        mapping = {
            "en": "en-US",
            "ru": "ru-RU", 
            "de": "de-DE",
            "fr": "fr-FR",
            "es": "es-ES",
            "it": "it-IT",
            "ja": "ja-JP",
            "ko": "ko-KR",
            "zh": "zh-CN"
        }
        return mapping.get(lang, lang)


class GoogleStrategy(ISpeechRecognitionStrategy):
    """
    Стратегия распознавания через Google API
    SOLID: Strategy Pattern + Dependency Injection
    """
    
    def __init__(self, engine: GoogleEngine = None):
        self.engine = engine or GoogleEngine()
        self.logger = logging.getLogger(__name__)
    
    def recognize_with_segmentation(
        self, 
        audio_path: str, 
        language: str = "en",
        segmenter: ITextSegmenter = None
    ) -> SpeechRecognitionResult:
        """
        Распознает через Google API
        Google дает качественный текст, дополнительная сегментация обычно не нужна
        """
        # Google API обычно дает хорошо структурированный текст
        result = self.engine.recognize_audio(audio_path, language)
        
        # Если передан сегментатор и текст длинный, можем применить сегментацию
        if (segmenter and result.full_text and 
            len(result.full_text) > 400):
            
            self.logger.debug("Применение дополнительной сегментации к Google результату")
            
            optimized_segments = segmenter.segment_text(result.full_text)
            
            if len(optimized_segments) > 1:
                # Создаем новые сегменты с распределенным временем
                new_segments = []
                segment_duration = result.total_duration / len(optimized_segments)
                
                for i, segment_text in enumerate(optimized_segments):
                    start_time = i * segment_duration
                    end_time = min((i + 1) * segment_duration, result.total_duration)
                    
                    segment = SpeechSegment(
                        start_time=start_time,
                        end_time=end_time,
                        text=segment_text,
                        confidence=0.95,
                        language=language,
                        metadata={
                            "engine": "google_segmented",
                            "original_segment": i,
                            "segmented_for_translation": True
                        }
                    )
                    new_segments.append(segment)
                
                result.segments = new_segments
                result.metadata["segmentation_applied"] = True
                
                self.logger.info(f"Google сегментация: {len(optimized_segments)} сегментов")
        
        return result