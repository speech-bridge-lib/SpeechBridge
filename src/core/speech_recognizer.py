#!/usr/bin/env python3
"""
SpeechRecognizer: Модуль распознавания речи с SSL fix
Поддерживает Google Speech Recognition и Whisper с fallback стратегиями
"""

# SSL Fix для macOS и multiprocessing fix - должен быть первым импортом
import os
import ssl

# Fix для multiprocessing на macOS (особенно с PyTorch/Whisper)
os.environ['TOKENIZERS_PARALLELISM'] = 'false'  # Отключаем параллелизм tokenizers
os.environ['OMP_NUM_THREADS'] = '1'            # Ограничиваем OpenMP потоки
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'  # Fallback для Metal Performance Shaders

try:
    import certifi

    cert_path = certifi.where()
    os.environ['SSL_CERT_FILE'] = cert_path
    os.environ['SSL_CERT_DIR'] = os.path.dirname(cert_path)
    os.environ['REQUESTS_CA_BUNDLE'] = cert_path
    os.environ['CURL_CA_BUNDLE'] = cert_path

    # Создаем SSL контекст с сертификатами
    context = ssl.create_default_context(cafile=cert_path)
    ssl._create_default_https_context = lambda: context
except Exception:
    pass

import logging
import tempfile
import time
from pathlib import Path
from typing import Optional, Dict, List

import speech_recognition as sr
from pydub import AudioSegment

# Whisper support
try:
    import whisper
    import torch
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from config import config


class SpeechRecognizer:
    """Класс для распознавания речи из аудио файлов с улучшенной обработкой ошибок"""

    def __init__(self):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.recognizer = sr.Recognizer()

        # Оптимизированные настройки параметров распознавания
        self.recognizer.energy_threshold = 300
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.8
        self.recognizer.operation_timeout = 30  # Устанавливаем timeout
        self.recognizer.phrase_threshold = 0.3

        # Инициализация доступных движков
        self.available_engines = self._test_engines_availability()

        # Конфигурация доступных моделей
        self.whisper_models = ["tiny", "base", "small", "medium", "large"]
        self.recognition_engines = ["whisper", "google", "sphinx"]
        
        # Текущие настройки (можно изменять через API)
        # Используем tiny для Intel Mac для лучшей производительности
        self.current_whisper_model = getattr(self.config, 'WHISPER_MODEL', 'tiny')
        self.preferred_engine = getattr(self.config, 'PREFERRED_RECOGNITION_ENGINE', 'whisper')
        
        self.logger.info(f"SpeechRecognizer инициализирован. Доступные движки: {list(self.available_engines.keys())}")
        self.logger.info(f"🎯 Текущие настройки: Whisper модель={self.current_whisper_model}, предпочтительный движок={self.preferred_engine}")

    def _test_engines_availability(self) -> Dict[str, bool]:
        """Тестирование доступности движков при инициализации"""
        engines = {}

        # Тест Google Speech Recognition
        engines['google'] = self._test_google_sr()

        # Тест Whisper
        try:
            import whisper
            engines['whisper'] = True
            self.logger.debug("Whisper доступен")
        except ImportError:
            engines['whisper'] = False
            self.logger.debug("Whisper недоступен")

        # Тест PocketSphinx
        engines['sphinx'] = self._test_sphinx()

        return engines

    def _test_google_sr(self) -> bool:
        """Тестирование Google Speech Recognition API"""
        try:
            # Создаем минимальное тестовое аудио
            test_audio = AudioSegment.silent(duration=100)  # 0.1 сек

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp_file:
                test_audio.export(tmp_file.name, format="wav",
                                  parameters=["-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000"])

                with sr.AudioFile(tmp_file.name) as source:
                    audio_data = self.recognizer.record(source)

                # Попытка быстрого API вызова
                try:
                    self.recognizer.recognize_google(audio_data, language="en-US")
                    self.logger.info("✓ Google Speech Recognition доступен")
                    return True
                except sr.UnknownValueError:
                    # Это нормально для тестового тишины - API доступен
                    self.logger.info("✓ Google Speech Recognition доступен")
                    return True
                except sr.RequestError as e:
                    self.logger.warning(f"✗ Google SR API недоступен: {e}")
                    return False

        except Exception as e:
            self.logger.warning(f"✗ Ошибка тестирования Google SR: {e}")
            return False

    def _test_sphinx(self) -> bool:
        """Тестирование PocketSphinx"""
        try:
            test_audio = AudioSegment.silent(duration=100)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp_file:
                test_audio.export(tmp_file.name, format="wav")
                with sr.AudioFile(tmp_file.name) as source:
                    audio_data = self.recognizer.record(source)
                    self.recognizer.recognize_sphinx(audio_data)
                    self.logger.debug("✓ Sphinx доступен")
                    return True
        except Exception:
            self.logger.debug("✗ Sphinx недоступен")
            return False

    def transcribe_audio(self, audio_path: str, language: str = None) -> str:
        """
        Распознавание речи из аудио файла с fallback стратегией и улучшенной обработкой

        Args:
            audio_path: путь к аудио файлу
            language: код языка (по умолчанию из конфига)

        Returns:
            str: распознанный текст
        """
        if language is None:
            language = self.config.SPEECH_LANGUAGE

        try:
            self.logger.debug(f"Начало распознавания речи из {audio_path}")

            if not Path(audio_path).exists():
                raise FileNotFoundError(f"Аудио файл не найден: {audio_path}")

            # Предварительная обработка аудио для улучшения качества
            processed_audio_path = self._preprocess_audio(audio_path)

            try:
                # Последовательно пробуем доступные движки
                result = None

                if self.available_engines.get('google', False):
                    result = self._transcribe_with_google_enhanced(processed_audio_path, language)
                    if result:
                        self.logger.info(f"Google SR успешно: '{result[:50]}...'")
                        return result

                if self.available_engines.get('whisper', False):
                    result = self._transcribe_with_whisper(processed_audio_path, language)
                    if result:
                        self.logger.info(f"Whisper успешно: '{result[:50]}...'")
                        return result

                if self.available_engines.get('sphinx', False):
                    result = self._try_sphinx(processed_audio_path, language)
                    if result:
                        self.logger.info(f"Sphinx успешно: '{result[:50]}...'")
                        return result

                self.logger.warning("Ни один движок не смог распознать речь")
                return ""

            finally:
                # Очистка временного файла
                if processed_audio_path != audio_path and Path(processed_audio_path).exists():
                    Path(processed_audio_path).unlink()

        except Exception as e:
            self.logger.error(f"Ошибка распознавания речи: {e}")
            return ""

    def _preprocess_audio(self, audio_path: str) -> str:
        """
        Предварительная обработка аудио для улучшения качества распознавания

        Returns:
            str: путь к обработанному аудио файлу
        """
        try:
            audio = AudioSegment.from_file(audio_path)

            # Конвертация в оптимальный формат
            audio = audio.set_frame_rate(16000).set_channels(1)

            # Нормализация громкости
            if audio.dBFS < -30:
                # Усиливаем тихое аудио
                gain_needed = -20 - audio.dBFS
                audio = audio.apply_gain(min(gain_needed, 15))  # Не более +15dB
                self.logger.debug(f"Усилено аудио на {min(gain_needed, 15):.1f} dB")

            elif audio.dBFS > -6:
                # Понижаем слишком громкое аудио
                gain_needed = -12 - audio.dBFS
                audio = audio.apply_gain(gain_needed)
                self.logger.debug(f"Понижено аудио на {abs(gain_needed):.1f} dB")

            # Базовая фильтрация
            if len(audio) > 1000:  # Только для аудио длиннее 1 секунды
                audio = audio.high_pass_filter(80)

            # Сохраняем во временный файл
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                audio.export(tmp_file.name, format="wav",
                             parameters=["-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000"])
                return tmp_file.name

        except Exception as e:
            self.logger.warning(f"Ошибка предварительной обработки, используем оригинал: {e}")
            return audio_path

    def _transcribe_with_google_enhanced(self, audio_path: str, language: str) -> Optional[str]:
        """
        Улучшенное распознавание через Google Speech Recognition с несколькими попытками
        """
        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                self.logger.debug(f"Google SR попытка {attempt + 1}/{max_attempts}")

                with sr.AudioFile(audio_path) as source:
                    # Настройка для шумоподавления
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    audio_data = self.recognizer.record(source)

                # Различные конфигурации для попыток
                configs = [
                    {"language": language, "show_all": False},
                    {"language": language, "show_all": True},
                    {"language": "en-US", "show_all": False} if language != "en-US" else None
                ]

                for config in filter(None, configs):
                    try:
                        api_key = self.config.SPEECH_API_KEY

                        if api_key and api_key != "your_google_speech_api_key":
                            text = self.recognizer.recognize_google(
                                audio_data,
                                key=api_key,
                                **config
                            )
                        else:
                            text = self.recognizer.recognize_google(audio_data, **config)

                        # Обработка результата
                        if isinstance(text, dict) and 'alternative' in text:
                            if text['alternative'] and text['alternative'][0].get('transcript'):
                                return text['alternative'][0]['transcript'].strip()
                        elif isinstance(text, str) and text.strip():
                            return text.strip()

                    except sr.UnknownValueError:
                        continue  # Пробуем следующую конфигурацию
                    except sr.RequestError as e:
                        if "quota" in str(e).lower() or "limit" in str(e).lower():
                            self.logger.warning("Google SR: превышены лимиты API")
                            return None
                        elif attempt < max_attempts - 1:
                            self.logger.warning(f"Google SR API ошибка (попытка {attempt + 1}): {e}")
                            time.sleep(1)  # Пауза между попытками
                            break
                        else:
                            self.logger.error(f"Google SR API ошибка: {e}")
                            return None

            except Exception as e:
                if attempt < max_attempts - 1:
                    self.logger.warning(f"Google SR попытка {attempt + 1} неудачна: {e}")
                    time.sleep(1)
                else:
                    self.logger.error(f"Google SR критическая ошибка: {e}")
                    return None

        return None

    def _transcribe_with_whisper(self, audio_path: str, language: str) -> Optional[str]:
        """
        Распознавание через OpenAI Whisper с временными метками
        """
        try:
            import whisper

            # Загружаем модель (кэшируется автоматически)
            model_name = getattr(self.config, 'WHISPER_MODEL', 'base')
            model = whisper.load_model(model_name)

            # Конвертируем код языка для Whisper
            whisper_language = self._convert_language_code_for_whisper(language)

            # Распознавание С ВРЕМЕННЫМИ МЕТКАМИ
            result = model.transcribe(
                audio_path,
                language=whisper_language,
                task="transcribe",
                fp16=False,
                verbose=False,
                word_timestamps=True  # КЛЮЧЕВОЙ ПАРАМЕТР!
            )

            text = result.get('text', '').strip()

            if text:
                # Логируем временные метки для диагностики
                segments = result.get('segments', [])
                if segments:
                    self.logger.info(f"🕒 Whisper: {len(segments)} сегментов с временными метками")
                    for i, seg in enumerate(segments[:3]):  # Первые 3 для диагностики
                        start = seg.get('start', 0)
                        end = seg.get('end', 0)
                        seg_text = seg.get('text', '')[:50]
                        self.logger.info(f"  Сегмент {i+1}: {start:.1f}-{end:.1f}с '{seg_text}...'")
                else:
                    self.logger.warning("⚠️ Whisper не вернул сегменты с временными метками")

                self.logger.info(f"✅ Whisper распознал: {len(text)} символов")
                return text

            return None

        except ImportError:
            self.logger.debug("Whisper не установлен, пропускаем")
            return None
        except Exception as e:
            self.logger.warning(f"Whisper ошибка: {e}")
            return None

    def transcribe_with_whisper_advanced(self, audio_path: str, language: str = "en", 
                                       model_size: str = "small") -> Optional[Dict]:
        """
        Продвинутое распознавание с Whisper через subprocess для избежания зависания
        Возвращает структурированные данные для дальнейшей обработки
        Технология перенесена из успешной реализации Google Colab
        """
        try:
            import subprocess
            import json
            import tempfile
            
            self.logger.info(f"🎯 Whisper Subprocess: модель {model_size}, язык {language}")
            
            # Создаем временный файл для результата
            with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as tmp_file:
                result_file = tmp_file.name
            
            # Создаем скрипт для изолированного выполнения Whisper
            whisper_script = f"""
import whisper
import json
import sys
import os
import time

print("SUBPROCESS: Начало выполнения...")

# Критическая оптимизация для Intel Mac - максимальное отключение многопроцессорности
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
os.environ['NUMEXPR_NUM_THREADS'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
os.environ['TORCH_USE_CUDA_DSA'] = '0'
# Дополнительные переменные для Intel Mac
os.environ['OMP_MAX_ACTIVE_LEVELS'] = '1'
os.environ['PYTHONHASHSEED'] = '0'

# Настройка multiprocessing для macOS
try:
    import multiprocessing
    if hasattr(multiprocessing, 'set_start_method'):
        try:
            multiprocessing.set_start_method('spawn', force=True)
            print("SUBPROCESS: Multiprocessing установлен в spawn режим")
        except RuntimeError as e:
            print(f"SUBPROCESS: Multiprocessing уже настроен: {{e}}")
except Exception as e:
    print(f"SUBPROCESS: Ошибка настройки multiprocessing: {{e}}")

try:
    print("SUBPROCESS: Импорт torch...")
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    # Отключаем MPS на Mac для стабильности 
    try:
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            if hasattr(torch.backends.mps, 'empty_cache'):
                torch.backends.mps.empty_cache()
            print("SUBPROCESS: MPS отключен")
    except Exception as e:
        print(f"SUBPROCESS: MPS недоступен: {{e}}")
    print("SUBPROCESS: Torch настроен")
    
    # Загружаем модель
    print("SUBPROCESS: Загрузка модели {model_size}...")
    start_time = time.time()
    model = whisper.load_model('{model_size}', device='cpu')
    load_time = time.time() - start_time
    print(f"SUBPROCESS: Модель загружена за {{load_time:.1f}}s")
    
    # Распознавание
    print("SUBPROCESS: Начало распознавания...")
    transcribe_start = time.time()
    result = model.transcribe(
        '{audio_path}',
        language='{self._convert_language_code_for_whisper(language)}',
        word_timestamps=True,
        verbose=False,
        fp16=False
    )
    transcribe_time = time.time() - transcribe_start
    print(f"SUBPROCESS: Распознавание завершено за {{transcribe_time:.1f}}s")
    
    # Сохраняем результат
    print("SUBPROCESS: Сохранение результата...")
    with open('{result_file}', 'w', encoding='utf-8') as f:
        json.dump({{
            'text': result.get('text', '').strip(),
            'segments': result.get('segments', []),
            'language': result.get('language', '{language}')
        }}, f, ensure_ascii=False, indent=2)
        
    print("SUCCESS")
    
except Exception as e:
    print(f"ERROR: {{e}}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
"""
            
            # Сохраняем скрипт
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as script_file:
                script_file.write(whisper_script)
                script_path = script_file.name
            
            try:
                # Запускаем Whisper в отдельном процессе с таймаутом
                self.logger.info("🚀 Запуск Whisper в изолированном процессе...")
                self.logger.info(f"📄 Скрипт создан: {script_path}")
                self.logger.info(f"📄 Результат сохранится в: {result_file}")
                
                import time
                start_time = time.time()
                
                try:
                    import sys
                    import os
                    
                    # Используем обычный Python вместо miniforge3 для избежания конфликтов
                    python_path = "/usr/local/bin/python3" if os.path.exists("/usr/local/bin/python3") else sys.executable
                    
                    self.logger.info(f"🐍 Используем Python: {python_path}")
                    
                    result = subprocess.run([
                        python_path, script_path
                    ], capture_output=True, text=True, timeout=600)  # 10 минут таймаут для длинных сегментов
                    
                    elapsed = time.time() - start_time
                    self.logger.info(f"⏱️ Subprocess завершился за {elapsed:.1f}s")
                    self.logger.info(f"🔍 Return code: {result.returncode}")
                    self.logger.info(f"📤 Stdout: {result.stdout[:200]}...")
                    if result.stderr:
                        self.logger.error(f"📥 Stderr: {result.stderr[:200]}...")
                        
                except subprocess.TimeoutExpired:
                    self.logger.error("⏰ Subprocess превысил таймаут 10 минут!")
                    return None
                    
                if result.returncode == 0 and "SUCCESS" in result.stdout:
                    # Читаем результат
                    with open(result_file, 'r', encoding='utf-8') as f:
                        whisper_result = json.load(f)
                    
                    # Извлекаем сегменты
                    segments = []
                    for segment in whisper_result.get("segments", []):
                        segments.append({
                            'start_time': segment['start'],
                            'end_time': segment['end'],
                            'text': segment['text'].strip()
                        })
                    
                    self.logger.info(f"📊 Whisper Subprocess: {len(segments)} исходных сегментов")
                    
                    # Добавим диагностику сегментов
                    total_whisper_duration = 0
                    if segments:
                        total_whisper_duration = segments[-1]['end_time'] - segments[0]['start_time']
                        self.logger.info(f"🕒 Whisper распознал аудио от {segments[0]['start_time']:.1f}s до {segments[-1]['end_time']:.1f}s (длительность: {total_whisper_duration:.1f}s)")
                        
                        # Показываем первые и последние сегменты для диагностики
                        for i, seg in enumerate(segments[:3]):  # Первые 3
                            self.logger.info(f"  🎯 Сегмент {i+1}: {seg['start_time']:.1f}-{seg['end_time']:.1f}s '{seg['text'][:50]}...'")
                        if len(segments) > 6:
                            self.logger.info(f"  ... ({len(segments)-6} средних сегментов) ...")
                        for i, seg in enumerate(segments[-3:], len(segments)-2):  # Последние 3
                            if i > 2: # Избегаем дублирования если сегментов мало
                                self.logger.info(f"  🎯 Сегмент {i}: {seg['start_time']:.1f}-{seg['end_time']:.1f}s '{seg['text'][:50]}...'")
                    
                    # Объединяем в предложения (технология из Colab)
                    sentence_segments = self._merge_segments_into_sentences(segments)
                    
                    return {
                        'text': whisper_result.get('text', '').strip(),
                        'segments': segments,
                        'sentences': sentence_segments,
                        'model': model_size,
                        'language': whisper_result.get('language', language),
                        'word_timestamps': True
                    }
                else:
                    self.logger.error(f"❌ Whisper subprocess failed: {result.stderr}")
                    return None
                    
            finally:
                # Очистка временных файлов
                try:
                    os.unlink(script_path)
                    os.unlink(result_file)
                except:
                    pass
            
        except Exception as e:
            self.logger.error(f"Ошибка Whisper Advanced: {e}")
            return None
    
    def _merge_segments_into_sentences(self, segments: List[Dict], max_gap_seconds: float = 1.5) -> List[Dict]:
        """
        Объединяет короткие сегменты в полные предложения для лучшего перевода
        Перенесено из успешной реализации Google Colab
        """
        self.logger.debug(f"📝 Объединяем сегменты в предложения (макс. пауза {max_gap_seconds}s)...")
        
        if not segments:
            return segments
        
        merged_segments = []
        current_sentence = None
        
        for i, segment in enumerate(segments):
            text = segment['text'].strip()
            
            if current_sentence is None:
                current_sentence = {
                    'start_time': segment['start_time'],
                    'end_time': segment['end_time'],
                    'text': text
                }
            else:
                gap = segment['start_time'] - current_sentence['end_time']
                
                # Условия объединения (логика из Colab)
                should_merge = (
                    gap <= max_gap_seconds and
                    not current_sentence['text'].rstrip().endswith(('.', '!', '?')) and
                    (not text or not text[0].isupper() or text.startswith(('and', 'or', 'but', 'so', 'because', 'that', 'which', 'who')))
                )
                
                if should_merge:
                    current_sentence['end_time'] = segment['end_time']
                    current_sentence['text'] = current_sentence['text'] + ' ' + text
                    self.logger.debug(f"   🔗 Объединяем сегмент {i+1}: пауза {gap:.1f}s")
                else:
                    merged_segments.append(current_sentence)
                    current_sentence = {
                        'start_time': segment['start_time'],
                        'end_time': segment['end_time'],
                        'text': text
                    }
        
        if current_sentence:
            merged_segments.append(current_sentence)
        
        self.logger.info(f"✅ Объединено: {len(segments)} сегментов → {len(merged_segments)} предложений")
        return merged_segments

    def transcribe_audio_with_timestamps(self, audio_path: str, language: str = 'en-US') -> Optional[dict]:
        """
        Распознавание с возвратом временных меток (только Whisper) с таймаутом
        
        Returns:
            dict: {'text': str, 'segments': [{'start': float, 'end': float, 'text': str}]}
        """
        try:
            import whisper
            import signal
            import os
            from pathlib import Path

            # Проверяем размер файла
            if not Path(audio_path).exists():
                self.logger.error(f"Аудио файл не найден: {audio_path}")
                return None
                
            file_size = Path(audio_path).stat().st_size
            if file_size < 1000:  # Менее 1KB
                self.logger.warning(f"Слишком маленький аудио файл: {file_size} байт")
                return None

            self.logger.info(f"🎙️ Whisper timestamps: файл {file_size} байт")

            # Функция для обработки таймаута
            def timeout_handler(signum, frame):
                raise TimeoutError("Whisper превысил лимит времени (180 секунд)")

            # Устанавливаем таймаут 3 минуты
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(180)

            try:
                model_name = getattr(self.config, 'WHISPER_MODEL', 'base')
                self.logger.info(f"🤖 Загружаем Whisper модель: {model_name}")
                
                # Загружаем модель с проверкой
                model = whisper.load_model(model_name)
                self.logger.info("✅ Whisper модель загружена")

                whisper_language = self._convert_language_code_for_whisper(language)

                # Распознавание с временными метками  
                self.logger.info("🔄 Начинаем распознавание с Whisper...")
                result = model.transcribe(
                    audio_path,
                    language=whisper_language,
                    task="transcribe",
                    fp16=False,
                    verbose=False,
                    word_timestamps=True,
                    no_speech_threshold=0.6,  # Более строгий порог для обнаружения речи
                    logprob_threshold=-1.0    # Более строгий порог для качества
                )

                text = result.get('text', '').strip()
                segments = result.get('segments', [])
                
                self.logger.info(f"🎯 Whisper результат: текст {len(text)} символов, {len(segments)} сегментов")

                if text and segments:
                    # Форматируем сегменты для удобного использования
                    formatted_segments = []
                    for seg in segments:
                        segment_text = seg.get('text', '').strip()
                        if segment_text:  # Только непустые сегменты
                            formatted_segments.append({
                                'start': seg.get('start', 0),
                                'end': seg.get('end', 0), 
                                'text': segment_text
                            })

                    self.logger.info(f"🕒 Whisper с временными метками: {len(formatted_segments)} валидных сегментов")
                    return {
                        'text': text,
                        'segments': formatted_segments
                    }

                self.logger.warning("Whisper не обнаружил речь или сегменты")
                return None

            finally:
                # Отменяем таймаут
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

        except ImportError:
            self.logger.debug("Whisper не установлен для временных меток")
            return None
        except TimeoutError as e:
            self.logger.error(f"⏰ Whisper таймаут: {e}")
            return None
        except Exception as e:
            self.logger.warning(f"Whisper временные метки ошибка: {e}")
            return None

    def _try_sphinx(self, audio_path: str, language: str) -> Optional[str]:
        """Попытка распознавания через PocketSphinx"""
        try:
            with sr.AudioFile(audio_path) as source:
                audio_data = self.recognizer.record(source)
                text = self.recognizer.recognize_sphinx(audio_data)
                return text.strip() if text else None
        except Exception as e:
            self.logger.debug(f"Sphinx ошибка: {e}")
            return None

    def _convert_language_code_for_whisper(self, language: str) -> str:
        """Конвертация кода языка для Whisper"""
        language_map = {
            'en-US': 'en', 'en-GB': 'en', 'ru-RU': 'ru', 'es-ES': 'es',
            'fr-FR': 'fr', 'de-DE': 'de', 'it-IT': 'it', 'pt-PT': 'pt',
            'zh-CN': 'zh', 'ja-JP': 'ja', 'ko-KR': 'ko'
        }

        if language in language_map:
            return language_map[language]

        base_language = language.split('-')[0].lower()
        return base_language if base_language in ['en', 'ru', 'es', 'fr', 'de', 'it', 'pt', 'zh', 'ja', 'ko'] else 'en'

    def transcribe_batch(self, audio_files: List[str], language: str = None) -> List[Dict]:
        """Пакетное распознавание нескольких аудио файлов"""
        results = []

        for i, audio_path in enumerate(audio_files):
            self.logger.info(f"Обработка файла {i + 1}/{len(audio_files)}: {Path(audio_path).name}")

            start_time = time.time()
            try:
                text = self.transcribe_audio(audio_path, language)
                processing_time = time.time() - start_time

                result = {
                    'file_path': audio_path,
                    'text': text,
                    'success': bool(text),
                    'processing_time': processing_time,
                    'error': None
                }

            except Exception as e:
                result = {
                    'file_path': audio_path,
                    'text': '',
                    'success': False,
                    'processing_time': time.time() - start_time,
                    'error': str(e)
                }
                self.logger.error(f"Ошибка обработки {audio_path}: {e}")

            results.append(result)

        success_count = sum(1 for r in results if r['success'])
        self.logger.info(f"Пакетная обработка завершена: {success_count}/{len(audio_files)} успешно")
        return results

    def get_supported_languages(self) -> Dict[str, str]:
        """Получение списка поддерживаемых языков"""
        return {
            'en-US': 'English (US)', 'en-GB': 'English (UK)', 'ru-RU': 'Russian',
            'es-ES': 'Spanish', 'fr-FR': 'French', 'de-DE': 'German',
            'it-IT': 'Italian', 'pt-PT': 'Portuguese', 'zh-CN': 'Chinese (Simplified)',
            'ja-JP': 'Japanese', 'ko-KR': 'Korean'
        }

    def test_recognition_engines(self) -> Dict[str, bool]:
        """Тестирование доступности движков распознавания"""
        return self.available_engines.copy()

    def get_engine_status(self) -> Dict[str, str]:
        """Получение детального статуса движков"""
        status = {}

        for engine, available in self.available_engines.items():
            if available:
                status[engine] = "available"
            else:
                status[engine] = "unavailable"

        return status

    def get_available_models(self) -> Dict[str, List[str]]:
        """Получение списка доступных моделей для каждого движка"""
        return {
            'whisper': self.whisper_models,
            'google': ['standard'],  # Google Speech API не имеет выбора модели
            'sphinx': ['default']    # PocketSphinx использует стандартную модель
        }
    
    def set_whisper_model(self, model: str) -> bool:
        """Установка модели Whisper"""
        if model not in self.whisper_models:
            self.logger.warning(f"Неизвестная модель Whisper: {model}. Доступные: {self.whisper_models}")
            return False
        
        self.current_whisper_model = model
        self.logger.info(f"🎯 Установлена модель Whisper: {model}")
        return True
    
    def set_preferred_engine(self, engine: str) -> bool:
        """Установка предпочтительного движка распознавания"""
        if engine not in self.recognition_engines:
            self.logger.warning(f"Неизвестный движок: {engine}. Доступные: {self.recognition_engines}")
            return False
        
        if not self.available_engines.get(engine, False):
            self.logger.warning(f"Движок {engine} недоступен")
            return False
        
        self.preferred_engine = engine
        self.logger.info(f"🎯 Установлен предпочтительный движок: {engine}")
        return True
    
    def get_current_settings(self) -> Dict[str, str]:
        """Получение текущих настроек"""
        return {
            'whisper_model': self.current_whisper_model,
            'preferred_engine': self.preferred_engine,
            'available_engines': list(self.available_engines.keys()),
            'available_whisper_models': self.whisper_models
        }
    
    def transcribe_with_engine(self, audio_path: str, engine: str = None, 
                             model: str = None, language: str = 'en-US') -> Optional[str]:
        """
        Распознавание с указанием конкретного движка и модели
        """
        # Используем указанный движок или предпочтительный
        selected_engine = engine or self.preferred_engine
        
        # Для Whisper используем указанную модель или текущую
        whisper_model = model or self.current_whisper_model
        
        self.logger.info(f"🎯 Распознавание: движок={selected_engine}, модель={whisper_model if selected_engine == 'whisper' else 'N/A'}")
        
        if selected_engine == 'whisper' and self.available_engines.get('whisper'):
            return self._transcribe_with_whisper(audio_path, language, whisper_model)
        elif selected_engine == 'google' and self.available_engines.get('google'):
            processed_audio = self._preprocess_audio(audio_path)
            result = self._transcribe_with_google_enhanced(processed_audio, language)
            if processed_audio != audio_path and os.path.exists(processed_audio):
                os.unlink(processed_audio)
            return result
        else:
            # Fallback на обычное распознавание
            return self.transcribe_audio(audio_path, language)
    
    def _transcribe_with_whisper(self, audio_path: str, language: str, model: str = None) -> Optional[str]:
        """
        Subprocess метод распознавания с Whisper для избежания зависания на Intel Mac
        """
        try:
            # Используем переданную модель или текущую
            model_name = model or self.current_whisper_model
            
            self.logger.info(f"🎯 Whisper Subprocess: загружаем модель {model_name}")
            
            # Вызываем новый subprocess метод
            result = self.transcribe_with_whisper_advanced(audio_path, language, model_name)
            
            if result and result.get('text'):
                return result['text']
                
            return None
            
            text = result.get('text', '').strip()
            
            if text:
                segments = result.get('segments', [])
                self.logger.info(f"✅ Whisper {model_name}: {len(text)} символов, {len(segments)} сегментов")
                return text
            
            return None
            
        except Exception as e:
            self.logger.error(f"Ошибка Whisper {model_name}: {e}")
            return None


if __name__ == "__main__":
    # Тестирование модуля
    print("=== Тестирование улучшенного SpeechRecognizer ===")

    recognizer = SpeechRecognizer()
    print("SpeechRecognizer инициализирован")

    # Статус движков
    status = recognizer.get_engine_status()
    print(f"Статус движков: {status}")

    # Тест поддерживаемых языков
    languages = recognizer.get_supported_languages()
    print(f"Поддерживаемые языки: {list(languages.keys())}")

    # Тест с реальным файлом
    test_file = "test.wav"
    if Path(test_file).exists():
        result = recognizer.transcribe_audio(test_file)
        print(f"Результат распознавания: '{result}'")
    else:
        print(f"Для тестирования создайте файл {test_file}")