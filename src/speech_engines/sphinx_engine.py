"""
Sphinx движок распознавания речи с оптимизированной сегментацией для DeepL
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


class SphinxTextSegmenter(ITextSegmenter):
    """
    Специализированный сегментатор для текстов Sphinx
    SOLID: Single Responsibility - только сегментация Sphinx-текстов
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def segment_text(self, text: str, max_segment_length: int = 400) -> List[str]:
        """
        Разбивает текст Sphinx на оптимальные сегменты для DeepL
        
        Sphinx особенности:
        - Мало пунктуации
        - Длинные предложения
        - Нужна принудительная сегментация по словам
        """
        if len(text) <= max_segment_length:
            return [text]
        
        self.logger.debug(f"Сегментация Sphinx текста: {len(text)} символов -> макс {max_segment_length}")
        
        # 1. Пробуем разбить по редким знакам препинания
        segments = self._split_by_punctuation(text)
        
        # 2. Если сегменты все еще слишком длинные, разбиваем по союзам
        segments = self._split_by_conjunctions(segments, max_segment_length)
        
        # 3. Принудительная разбивка по словам для оставшихся длинных сегментов
        segments = self._force_split_by_words(segments, max_segment_length)
        
        self.logger.debug(f"Результат сегментации Sphinx: {len(segments)} сегментов")
        return segments
    
    def _split_by_punctuation(self, text: str) -> List[str]:
        """Разбивает по доступным знакам препинания"""
        import re
        
        # Sphinx редко использует точки, но может быть несколько предложений
        sentences = re.split(r'[.!?]+\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _split_by_conjunctions(self, segments: List[str], max_length: int) -> List[str]:
        """Разбивает длинные сегменты по союзам и связкам"""
        import re
        
        result = []
        conjunction_pattern = r'\s+(and|but|or|so|because|when|while|if|since|although|however|therefore)\s+'
        
        for segment in segments:
            if len(segment) <= max_length:
                result.append(segment)
                continue
            
            # Разбиваем по союзам
            parts = re.split(conjunction_pattern, segment, flags=re.IGNORECASE)
            
            current_part = ""
            i = 0
            while i < len(parts):
                part = parts[i].strip()
                conjunction = parts[i + 1].strip() if i + 1 < len(parts) else ""
                
                # Проверяем, поместится ли часть с союзом
                test_part = current_part + " " + part if current_part else part
                if conjunction:
                    test_part += " " + conjunction
                
                if len(test_part) <= max_length:
                    current_part = test_part
                    i += 2 if conjunction else 1
                else:
                    if current_part:
                        result.append(current_part.strip())
                    current_part = part
                    i += 1
            
            if current_part:
                result.append(current_part.strip())
        
        return result
    
    def _force_split_by_words(self, segments: List[str], max_length: int) -> List[str]:
        """Принудительно разбивает оставшиеся длинные сегменты по словам"""
        result = []
        
        for segment in segments:
            if len(segment) <= max_length:
                result.append(segment)
                continue
            
            words = segment.split()
            current_segment = ""
            
            for word in words:
                test_segment = current_segment + " " + word if current_segment else word
                
                if len(test_segment) <= max_length:
                    current_segment = test_segment
                else:
                    if current_segment:
                        result.append(current_segment.strip())
                    current_segment = word
            
            if current_segment:
                result.append(current_segment.strip())
        
        return result


class SphinxEngine(ISpeechRecognitionEngine):
    """
    PocketSphinx движок распознавания речи
    SOLID: Single Responsibility - только Sphinx распознавание
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
        self._available = None
    
    def get_engine_name(self) -> str:
        return "sphinx"
    
    def is_available(self) -> bool:
        if self._available is None:
            try:
                import speech_recognition as sr
                r = sr.Recognizer()
                # Проверяем доступность Sphinx
                test_audio_path = Path(__file__).parent.parent.parent / "test_audio.wav"
                if test_audio_path.exists():
                    with sr.AudioFile(str(test_audio_path)) as source:
                        audio = r.record(source, duration=1)
                    r.recognize_sphinx(audio)
                self._available = True
            except Exception as e:
                self.logger.debug(f"Sphinx недоступен: {e}")
                self._available = False
        
        return self._available
    
    def get_supported_languages(self) -> List[str]:
        return ["en"]  # Sphinx в основном поддерживает английский
    
    def recognize_audio(self, audio_path: str, language: str = "en") -> SpeechRecognitionResult:
        """Распознает аудио через PocketSphinx"""
        start_time = time.time()
        
        try:
            import speech_recognition as sr
            
            recognizer = sr.Recognizer()
            
            # Оптимизированные настройки для Sphinx
            recognizer.energy_threshold = 4000
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold = 0.8
            recognizer.operation_timeout = 30
            
            with sr.AudioFile(audio_path) as source:
                self.logger.debug("Подстройка под фоновый шум...")
                recognizer.adjust_for_ambient_noise(source, duration=1)
                audio_data = recognizer.record(source)
            
            self.logger.debug("Запуск Sphinx распознавания...")
            text = recognizer.recognize_sphinx(
                audio_data, 
                language=language,
                keyword_entries=None,  # Можно добавить ключевые слова
                grammar=None
            )
            
            if not text:
                text = ""
            
            # Получаем длительность аудио
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            duration = len(audio) / 1000.0
            
            # Создаем один сегмент (Sphinx не дает временные метки)
            segment = SpeechSegment(
                start_time=0.0,
                end_time=duration,
                text=text,
                confidence=0.8,  # Sphinx не дает confidence, ставим средний
                language=language,
                metadata={
                    "engine": "sphinx",
                    "energy_threshold": recognizer.energy_threshold
                }
            )
            
            processing_time = time.time() - start_time
            
            result = SpeechRecognitionResult(
                segments=[segment],
                full_text=text,
                total_duration=duration,
                engine_used="sphinx",
                processing_time=processing_time,
                metadata={
                    "energy_threshold": recognizer.energy_threshold,
                    "pause_threshold": recognizer.pause_threshold
                }
            )
            
            self.logger.info(f"Sphinx успешно: '{text[:50]}...' за {processing_time:.1f}s")
            return result
            
        except Exception as e:
            self.logger.error(f"Ошибка Sphinx распознавания: {e}")
            raise


class SphinxStrategy(ISpeechRecognitionStrategy):
    """
    Стратегия распознавания через Sphinx с оптимизированной сегментацией
    SOLID: Strategy Pattern + Dependency Injection
    """
    
    def __init__(self, engine: SphinxEngine = None, segmenter: SphinxTextSegmenter = None):
        self.engine = engine or SphinxEngine()
        self.segmenter = segmenter or SphinxTextSegmenter()
        self.logger = logging.getLogger(__name__)
    
    def recognize_with_segmentation(
        self, 
        audio_path: str, 
        language: str = "en",
        segmenter: ITextSegmenter = None
    ) -> SpeechRecognitionResult:
        """
        Распознает через Sphinx и оптимизирует сегментацию для DeepL
        """
        # Используем переданный сегментатор или собственный
        text_segmenter = segmenter or self.segmenter
        
        # 1. Обычное распознавание через Sphinx
        result = self.engine.recognize_audio(audio_path, language)
        
        # 2. Если текст получился, оптимизируем сегментацию
        if result.full_text and len(result.full_text.strip()) > 0:
            self.logger.debug(f"Оптимизация Sphinx сегментации: '{result.full_text[:50]}...'")
            
            # Разбиваем текст на оптимальные сегменты для DeepL
            optimized_segments = text_segmenter.segment_text(result.full_text)
            
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
                    confidence=0.8,
                    language=language,
                    metadata={
                        "engine": "sphinx_optimized",
                        "original_segment": i,
                        "optimized_for_deepl": True
                    }
                )
                new_segments.append(segment)
            
            # Обновляем результат
            result.segments = new_segments
            result.metadata["segmentation_optimized"] = True
            result.metadata["deepl_segments"] = len(new_segments)
            
            self.logger.info(f"Sphinx оптимизация: {len(optimized_segments)} сегментов для DeepL")
        
        return result