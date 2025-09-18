"""
Whisper движок с изолированным процессом
SOLID: Single Responsibility + Open/Closed Principle
"""

import logging
import time
import tempfile
import subprocess
import json
from typing import List, Dict, Any
from pathlib import Path

from ..interfaces.speech_recognition_interface import (
    ISpeechRecognitionEngine, 
    SpeechSegment, 
    SpeechRecognitionResult,
    ISpeechRecognitionStrategy,
    ITextSegmenter
)


class WhisperEngine(ISpeechRecognitionEngine):
    """
    OpenAI Whisper движок с изолированным процессом
    SOLID: Single Responsibility - только Whisper распознавание
    """
    
    def __init__(self, model_size: str = "tiny", logger: logging.Logger = None):
        self.model_size = model_size
        self.logger = logger or logging.getLogger(__name__)
        self._available = None
    
    def get_engine_name(self) -> str:
        return f"whisper_{self.model_size}"
    
    def is_available(self) -> bool:
        if self._available is None:
            try:
                import whisper
                import torch
                
                # Проверяем доступность модели
                whisper.load_model(self.model_size)
                self._available = True
            except Exception as e:
                self.logger.debug(f"Whisper недоступен: {e}")
                self._available = False
        
        return self._available
    
    def get_supported_languages(self) -> List[str]:
        return ["en", "ru", "de", "fr", "es", "it", "ja", "ko", "zh", "pt", "ar"]
    
    def recognize_audio(self, audio_path: str, language: str = "en") -> SpeechRecognitionResult:
        """Распознает аудио через Whisper в изолированном процессе"""
        start_time = time.time()
        
        try:
            # Создаем временный файл для результата
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as result_file:
                result_path = result_file.name
            
            # Создаем скрипт для изолированного выполнения
            script_content = f'''
import sys
import os
import json
import warnings

# Подавляем предупреждения
warnings.filterwarnings("ignore")
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"

print("SUBPROCESS: Начало выполнения...", flush=True)

try:
    import multiprocessing
    multiprocessing.set_start_method('spawn', force=True)
    print("SUBPROCESS: Multiprocessing установлен в spawn режим", flush=True)
    
    import torch
    print("SUBPROCESS: Импорт torch...", flush=True)
    
    # Отключаем MPS для стабильности на Intel Mac
    if hasattr(torch.backends, 'mps'):
        torch.backends.mps.is_available = lambda: False
        print("SUBPROCESS: MPS отключен", flush=True)
    
    print("SUBPROCESS: Torch настроен", flush=True)
    
    import whisper
    print("SUBPROCESS: Загрузка модели {self.model_size}...", flush=True)
    
    model = whisper.load_model("{self.model_size}")
    print("SUBPROCESS: Модель загружена", flush=True)
    
    print("SUBPROCESS: Начало транскрибации...", flush=True)
    result = model.transcribe(
        "{audio_path}",
        language="{language}",
        word_timestamps=True,
        verbose=False,
        temperature=0.0,
        beam_size=1,
        best_of=1,
        fp16=False
    )
    print("SUBPROCESS: Транскрибация завершена", flush=True)
    
    # Сохраняем результат
    with open("{result_path}", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print("SUBPROCESS: Результат сохранен", flush=True)
    
except Exception as e:
    print(f"SUBPROCESS ERROR: {{e}}", flush=True)
    error_result = {{
        "text": "",
        "segments": [],
        "error": str(e)
    }}
    with open("{result_path}", "w", encoding="utf-8") as f:
        json.dump(error_result, f, ensure_ascii=False, indent=2)
'''
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as script_file:
                script_file.write(script_content)
                script_path = script_file.name
            
            self.logger.info("🚀 Запуск Whisper в изолированном процессе...")
            self.logger.info(f"📄 Скрипт создан: {script_path}")
            self.logger.info(f"📄 Результат сохранится в: {result_path}")
            
            # Запускаем изолированный процесс
            process = subprocess.run(
                ["python", script_path],
                capture_output=True,
                text=True,
                timeout=300,  # 5 минут таймаут
                env={**os.environ, "PYTHONPATH": ""}  # Чистое окружение
            )
            
            processing_time = time.time() - start_time
            self.logger.info(f"⏱️ Subprocess завершился за {processing_time:.1f}s")
            self.logger.info(f"🔍 Return code: {process.returncode}")
            
            if process.stdout:
                self.logger.info(f"📤 Stdout: {process.stdout[:200]}...")
            
            if process.stderr:
                self.logger.error(f"📥 Stderr: {process.stderr[:500]}...")
            
            # Читаем результат
            if not Path(result_path).exists():
                raise RuntimeError("Результат Whisper не найден")
            
            with open(result_path, 'r', encoding='utf-8') as f:
                whisper_result = json.load(f)
            
            # Очищаем временные файлы
            Path(script_path).unlink(missing_ok=True)
            Path(result_path).unlink(missing_ok=True)
            
            if "error" in whisper_result:
                raise RuntimeError(f"Whisper subprocess error: {whisper_result['error']}")
            
            # Конвертируем результат Whisper в наш формат
            return self._convert_whisper_result(whisper_result, processing_time, language)
            
        except subprocess.TimeoutExpired:
            self.logger.error("❌ Whisper subprocess timeout")
            raise RuntimeError("Whisper subprocess timeout")
        except Exception as e:
            self.logger.error(f"❌ Whisper subprocess failed: {e}")
            raise
    
    def _convert_whisper_result(
        self, 
        whisper_result: Dict[str, Any], 
        processing_time: float,
        language: str
    ) -> SpeechRecognitionResult:
        """Конвертирует результат Whisper в наш формат"""
        
        segments = []
        full_text = whisper_result.get("text", "")
        
        # Конвертируем сегменты Whisper
        for i, whisper_segment in enumerate(whisper_result.get("segments", [])):
            segment = SpeechSegment(
                start_time=whisper_segment.get("start", 0.0),
                end_time=whisper_segment.get("end", 0.0),
                text=whisper_segment.get("text", "").strip(),
                confidence=whisper_segment.get("avg_logprob", 0.0),  # Whisper дает logprob
                language=language,
                metadata={
                    "engine": "whisper",
                    "model_size": self.model_size,
                    "segment_id": i,
                    "tokens": whisper_segment.get("tokens", []),
                    "words": whisper_segment.get("words", [])
                }
            )
            segments.append(segment)
        
        # Если нет сегментов, создаем один общий
        if not segments and full_text:
            segment = SpeechSegment(
                start_time=0.0,
                end_time=processing_time,  # Приблизительно
                text=full_text,
                confidence=0.9,
                language=language,
                metadata={
                    "engine": "whisper",
                    "model_size": self.model_size,
                    "single_segment": True
                }
            )
            segments.append(segment)
        
        total_duration = segments[-1].end_time if segments else 0.0
        
        result = SpeechRecognitionResult(
            segments=segments,
            full_text=full_text,
            total_duration=total_duration,
            engine_used=f"whisper_{self.model_size}",
            processing_time=processing_time,
            metadata={
                "model_size": self.model_size,
                "whisper_language": whisper_result.get("language"),
                "segments_count": len(segments)
            }
        )
        
        self.logger.info(f"Whisper успешно: {len(segments)} сегментов, '{full_text[:50]}...'")
        return result


class WhisperStrategy(ISpeechRecognitionStrategy):
    """
    Стратегия распознавания через Whisper
    SOLID: Strategy Pattern + Dependency Injection
    """
    
    def __init__(self, engine: WhisperEngine = None):
        self.engine = engine or WhisperEngine()
        self.logger = logging.getLogger(__name__)
    
    def recognize_with_segmentation(
        self, 
        audio_path: str, 
        language: str = "en",
        segmenter: ITextSegmenter = None
    ) -> SpeechRecognitionResult:
        """
        Распознает через Whisper
        Whisper уже дает хорошую сегментацию, дополнительная обычно не нужна
        """
        result = self.engine.recognize_audio(audio_path, language)
        
        # Whisper обычно дает хорошую сегментацию из коробки
        # Но если передан сегментатор и есть очень длинные сегменты, можем применить
        if segmenter and result.segments:
            long_segments = [s for s in result.segments if len(s.text) > 400]
            
            if long_segments:
                self.logger.debug(f"Whisper: найдено {len(long_segments)} длинных сегментов")
                
                new_segments = []
                for segment in result.segments:
                    if len(segment.text) > 400:
                        # Применяем сегментацию к длинному сегменту
                        sub_segments = segmenter.segment_text(segment.text)
                        
                        if len(sub_segments) > 1:
                            duration = segment.end_time - segment.start_time
                            sub_duration = duration / len(sub_segments)
                            
                            for i, sub_text in enumerate(sub_segments):
                                sub_start = segment.start_time + i * sub_duration
                                sub_end = segment.start_time + (i + 1) * sub_duration
                                
                                sub_segment = SpeechSegment(
                                    start_time=sub_start,
                                    end_time=sub_end,
                                    text=sub_text,
                                    confidence=segment.confidence,
                                    language=segment.language,
                                    metadata={
                                        **segment.metadata,
                                        "whisper_subsegmented": True,
                                        "original_segment_id": segment.metadata.get("segment_id")
                                    }
                                )
                                new_segments.append(sub_segment)
                        else:
                            new_segments.append(segment)
                    else:
                        new_segments.append(segment)
                
                if len(new_segments) != len(result.segments):
                    result.segments = new_segments
                    result.metadata["whisper_segmentation_applied"] = True
                    self.logger.info(f"Whisper сегментация: {len(new_segments)} итоговых сегментов")
        
        return result