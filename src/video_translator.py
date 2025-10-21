#!/usr/bin/env python3
"""
VideoTranslator: Обновленный основной класс для перевода видео
Использует модульную архитектуру core компонентов + сохранение текстов
"""

# SSL Fix для macOS 
import os
import ssl
try:
    import certifi
    cert_path = certifi.where()
    os.environ['SSL_CERT_FILE'] = cert_path
    os.environ['SSL_CERT_DIR'] = os.path.dirname(cert_path)
    context = ssl.create_default_context(cafile=cert_path)
    ssl._create_default_https_context = lambda: context
except Exception:
    pass

import logging
import time
import subprocess
from typing import Optional, Dict, List, Callable, Tuple
import json
from datetime import datetime
from pathlib import Path

# Core модули
from core import VideoProcessor, AudioProcessor, SpeechRecognizer, SpeechSynthesizer
from core.speaker_diarization import SpeakerDiarization
from core.video_time_adjuster import VideoTimeAdjuster
from core.voice_activity_detector import VoiceActivityDetector
from core.voice_cloner import VoiceCloner
from core.tts_engine_factory import TTSEngineFactory
from translator_compat import translate_text, get_translator_status, get_language_info
from config import config

class VideoTranslator:
    """Основной класс для перевода видео с модульной архитектурой"""

    def __init__(self):
        self.config = config
        self.setup_logging()

        # Инициализация core компонентов
        self.video_processor = VideoProcessor()
        self.audio_processor = AudioProcessor()
        self.speech_recognizer = SpeechRecognizer()
        self.speech_synthesizer = SpeechSynthesizer()
        self.speaker_diarization = SpeakerDiarization(config)
        self.video_adjuster = VideoTimeAdjuster(config)
        self.voice_activity_detector = VoiceActivityDetector()
        
        # Voice cloning integration
        self.voice_cloner = VoiceCloner(config)
        self.tts_factory = TTSEngineFactory()
        
        # Enable voice cloning in speaker diarization
        self.speaker_diarization.enable_voice_cloning(self.voice_cloner)

        # Создание рабочих директорий
        self.config.create_directories()

        self.logger.info("VideoTranslator инициализирован с модульной архитектурой")
    
    def _get_subtitle_language_code(self, language_code):
        """Получить ISO языковой код для метаданных субтитров"""
        lang_info = get_language_info(language_code)
        return lang_info['iso']
    
    def _get_subtitle_title(self, language_code):
        """Получить название языка для метаданных субтитров"""
        lang_info = get_language_info(language_code)
        return lang_info['name']
    
    def _setup_tts_for_language(self, target_language):
        """Настроить TTS для целевого языка"""
        if hasattr(self.speech_synthesizer, 'set_target_language'):
            self.speech_synthesizer.set_target_language(target_language)
            self.logger.info(f"🎤 TTS настроен для языка: {target_language}")
        self._log_component_status()
    
    def _get_dynamic_language_labels(self, source_language, target_language):
        """Получить динамические языковые метки для двойных субтитров"""
        source_info = get_language_info(source_language) if source_language and source_language != 'auto' else {'name': 'EN', 'iso': 'eng'}
        target_info = get_language_info(target_language)
        
        # Используем краткие коды для субтитров (первые 2-3 символа названия языка)
        source_label = source_info['name'][:3].upper() if source_info['name'] else 'SRC'
        target_label = target_info['name'][:3].upper() if target_info['name'] else 'TGT'
        
        return source_label, target_label
    
    def get_available_engines(self) -> List[str]:
        """Возвращает список доступных движков распознавания"""
        engines = self.speech_recognizer.test_recognition_engines()
        return [name for name, available in engines.items() if available]
    
    def _select_speech_engine(self, preferred_engine: str, video_path: str) -> str:
        """
        Выбирает оптимальный движок распознавания речи
        
        Args:
            preferred_engine: предпочтительный движок ('auto', 'whisper', 'google', 'sphinx')
            video_path: путь к видеофайлу для анализа размера
            
        Returns:
            str: название выбранного движка
            
        Raises:
            ValueError: если ручно выбранный движок недоступен
        """
        # Проверяем доступные движки
        available_engines = self.speech_recognizer.test_recognition_engines()
        
        if preferred_engine != 'auto':
            # Если движок указан явно, проверяем его доступность
            if preferred_engine in available_engines and available_engines[preferred_engine]:
                self.logger.info(f"🎯 Выбран движок по требованию пользователя: {preferred_engine}")
                return preferred_engine
            else:
                # При ручном выборе выдаем ошибку, а не переключаемся
                error_msg = f"Выбранный движок '{preferred_engine}' недоступен или не работает"
                self.logger.error(f"❌ {error_msg}")
                raise ValueError(error_msg)
        
        # Автоматический выбор на основе размера файла (только для режима 'auto')
        try:
            file_size_mb = Path(video_path).stat().st_size / (1024 * 1024)
            
            # Для больших файлов (>100MB) предпочитаем Whisper
            if file_size_mb > 100:
                if 'whisper' in available_engines and available_engines['whisper']:
                    self.logger.info(f"🎤 Автоматически выбран Whisper для большого файла ({file_size_mb:.1f}MB)")
                    return 'whisper'
                else:
                    self.logger.warning("⚠️ Whisper недоступен для большого файла, ищем альтернативы")
            
            # Приоритет по качеству: Google > Whisper > Sphinx
            priority_engines = ['google', 'whisper', 'sphinx']
            for engine in priority_engines:
                if engine in available_engines and available_engines[engine]:
                    self.logger.info(f"🤖 Автоматически выбран {engine} для файла {file_size_mb:.1f}MB")
                    return engine
            
            # Если ничего не найдено, возвращаем первый доступный
            for engine, available in available_engines.items():
                if available:
                    self.logger.warning(f"⚠️ Используется резервный движок: {engine}")
                    return engine
                    
        except Exception as e:
            self.logger.error(f"Ошибка анализа файла: {e}")
        
        # Если совсем ничего не работает
        raise ValueError("Нет доступных движков распознавания речи")
    
    def _transcribe_with_engine(self, audio_path: str, engine: str, is_manual_selection: bool = False) -> str:
        """
        Распознает речь с указанным движком или пробует все доступные в авто режиме
        
        Args:
            audio_path: путь к аудиофайлу
            engine: движок распознавания ('whisper', 'google', 'sphinx')
            is_manual_selection: True если движок был выбран вручную
            
        Returns:
            str: распознанный текст
            
        Raises:
            ValueError: если при ручном выборе движок не работает или в авто режиме не сработал ни один движок
        """
        if is_manual_selection:
            # При ручном выборе пробуем только указанный движок
            self.logger.info(f"🎯 РУЧНОЙ РЕЖИМ: используем только движок {engine}")
            return self._try_single_engine(audio_path, engine, is_manual_selection=True)
        else:
            # В автоматическом режиме пробуем все доступные движки по приоритету
            self.logger.info(f"🤖 АВТОМАТИЧЕСКИЙ РЕЖИМ: попробуем все движки, предпочтение {engine}")
            return self._transcribe_with_auto_fallback(audio_path, preferred_engine=engine)
    
    def _try_single_engine(self, audio_path: str, engine: str, is_manual_selection: bool = False) -> str:
        """
        Пробует один конкретный движок для ручного режима
        
        Args:
            audio_path: путь к аудиофайлу
            engine: движок распознавания
            is_manual_selection: True если это ручной выбор
            
        Returns:
            str: распознанный текст
            
        Raises:
            ValueError: если движок не работает и это ручной выбор
        """
        try:
            self.logger.info(f"🎯 Ручной режим: пробуем движок {engine}")
            
            # Для ручного режима НЕ проверяем предварительную доступность
            # Просто пробуем и смотрим что получится
            result = self._try_engine_without_availability_check(audio_path, engine)
            
            if result and result.strip():
                self.logger.info(f"✅ Движок {engine} успешно распознал речь ({len(result)} символов)")
                return result.strip()
            else:
                if is_manual_selection:
                    # Проверяем, не является ли это коротким сегментом
                    import os
                    file_size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
                    if file_size < 10000:  # файл меньше 10KB
                        self.logger.warning(f"⚠️ Очень короткий аудио файл ({file_size} bytes), пропускаем")
                        return ""  # Возвращаем пустую строку вместо ошибки
                    else:
                        raise ValueError(f"Движок {engine} не смог распознать аудио в файле {audio_path}")
                else:
                    self.logger.warning(f"⚠️ Движок {engine} не вернул результат")
                    return ""
                
        except Exception as e:
            if is_manual_selection:
                # Проверяем, не является ли это коротким или проблемным сегментом
                import os
                file_size = os.path.getsize(audio_path) if os.path.exists(audio_path) else 0
                if file_size < 10000:  # файл меньше 10KB
                    self.logger.warning(f"⚠️ Очень короткий аудио файл ({file_size} bytes), пропускаем ошибку: {e}")
                    return ""  # Возвращаем пустую строку вместо критической ошибки
                else:
                    error_msg = f"Движок {engine} не работает: {str(e)}"
                    self.logger.error(f"❌ {error_msg}")
                    raise ValueError(error_msg)
            else:
                self.logger.warning(f"⚠️ Ошибка движка {engine}: {e}")
                return ""
    
    def _try_whisper_directly(self, audio_path: str) -> str:
        """Прямая попытка Whisper без fallback'ов"""
        self.logger.info(f"    🎯 WHISPER: Начало обработки")
        self.logger.info(f"    📁 Файл: {audio_path}")
        
        try:
            language = getattr(self.config, 'SPEECH_LANGUAGE', 'en-US')
            whisper_lang = language.split('-')[0].lower()
            model_size = self.speech_recognizer.current_whisper_model
            
            self.logger.info(f"    🌍 Язык: {language} -> {whisper_lang}")
            self.logger.info(f"    🤖 Модель: {model_size}")
            
            # Проверяем что speech_recognizer существует
            if not hasattr(self, 'speech_recognizer'):
                self.logger.error(f"    ❌ speech_recognizer не существует!")
                return ""
            
            self.logger.info(f"    ✅ speech_recognizer найден: {type(self.speech_recognizer)}")
            
            # Пробуем продвинутый метод Whisper с временными метками
            self.logger.info(f"    🔄 Попытка 1: transcribe_with_whisper_advanced")
            
            if hasattr(self.speech_recognizer, 'transcribe_with_whisper_advanced'):
                self.logger.info(f"    ✅ Метод transcribe_with_whisper_advanced найден")
                
                advanced_start = time.time()
                result = self.speech_recognizer.transcribe_with_whisper_advanced(
                    audio_path, 
                    language=whisper_lang,
                    model_size=model_size
                )
                advanced_time = time.time() - advanced_start
                
                self.logger.info(f"    ⏱️ transcribe_with_whisper_advanced выполнен за {advanced_time:.2f}с")
                self.logger.info(f"    📊 Результат типа: {type(result)}")
                
                if result and result.get('text'):
                    text = result['text'].strip()
                    self.logger.info(f"    ✅ Продвинутый метод вернул текст: {len(text)} символов")
                    self.logger.info(f"    📝 Превью: '{text[:50]}...'")
                    return text
                else:
                    self.logger.warning(f"    ⚠️ Продвинутый метод не вернул текст: {result}")
            else:
                self.logger.warning(f"    ⚠️ Метод transcribe_with_whisper_advanced не найден")
            
            # Если продвинутый метод не сработал, пробуем простой
            self.logger.info(f"    🔄 Попытка 2: _transcribe_with_whisper")
            
            if hasattr(self.speech_recognizer, '_transcribe_with_whisper'):
                self.logger.info(f"    ✅ Метод _transcribe_with_whisper найден")
                
                simple_start = time.time()
                result_simple = self.speech_recognizer._transcribe_with_whisper(
                    audio_path, 
                    language,
                    model_size
                )
                simple_time = time.time() - simple_start
                
                self.logger.info(f"    ⏱️ _transcribe_with_whisper выполнен за {simple_time:.2f}с")
                self.logger.info(f"    📊 Результат простого метода: {type(result_simple)}, '{result_simple}'")
                
                if result_simple:
                    self.logger.info(f"    ✅ Простой метод вернул: {len(result_simple)} символов")
                    return result_simple
                else:
                    self.logger.warning(f"    ⚠️ Простой метод не вернул результат")
            else:
                self.logger.error(f"    ❌ Метод _transcribe_with_whisper не найден!")
            
            self.logger.warning(f"    ⚠️ WHISPER: Все попытки не дали результата")
            return ""
            
        except Exception as e:
            self.logger.error(f"    ❌ WHISPER: Критическая ошибка: {e}")
            self.logger.error(f"    🔍 Тип ошибки: {type(e).__name__}")
            
            import traceback
            self.logger.debug(f"    🔍 Трассировка Whisper:")
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.debug(f"      {line}")
            
            return ""
    
    def _try_google_directly(self, audio_path: str) -> str:
        """Прямая попытка Google Speech без fallback'ов"""
        self.logger.info(f"    🎯 GOOGLE: Начало обработки")
        self.logger.info(f"    📁 Файл: {audio_path}")
        
        processed_audio = None
        try:
            language = getattr(self.config, 'SPEECH_LANGUAGE', 'en-US')
            self.logger.info(f"    🌍 Язык: {language}")
            
            # Проверяем методы
            if not hasattr(self.speech_recognizer, '_preprocess_audio'):
                self.logger.error(f"    ❌ Метод _preprocess_audio не найден!")
                return ""
            
            if not hasattr(self.speech_recognizer, '_transcribe_with_google_enhanced'):
                self.logger.error(f"    ❌ Метод _transcribe_with_google_enhanced не найден!")
                return ""
            
            self.logger.info(f"    ✅ Все методы Google найдены")
            
            # Предварительная обработка аудио
            self.logger.info(f"    🔄 Предварительная обработка аудио...")
            preprocess_start = time.time()
            processed_audio = self.speech_recognizer._preprocess_audio(audio_path)
            preprocess_time = time.time() - preprocess_start
            
            self.logger.info(f"    ⏱️ Предобработка за {preprocess_time:.2f}с")
            self.logger.info(f"    📁 Обработанный файл: {processed_audio}")
            
            # Распознавание через Google
            self.logger.info(f"    🔄 Вызов Google Speech API...")
            google_start = time.time()
            result = self.speech_recognizer._transcribe_with_google_enhanced(
                processed_audio, 
                language
            )
            google_time = time.time() - google_start
            
            self.logger.info(f"    ⏱️ Google API выполнен за {google_time:.2f}с")
            self.logger.info(f"    📊 Результат: {type(result)}, '{result}'")
            
            if result and result.strip():
                self.logger.info(f"    ✅ Google вернул текст: {len(result)} символов")
                self.logger.info(f"    📝 Превью: '{result[:50]}...'")
                return result
            else:
                self.logger.warning(f"    ⚠️ Google не вернул результат")
                return ""
                
        except Exception as e:
            self.logger.error(f"    ❌ GOOGLE: Критическая ошибка: {e}")
            self.logger.error(f"    🔍 Тип ошибки: {type(e).__name__}")
            
            import traceback
            self.logger.debug(f"    🔍 Трассировка Google:")
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.debug(f"      {line}")
            
            return ""
        finally:
            # Очистка временного файла
            if processed_audio and processed_audio != audio_path and os.path.exists(processed_audio):
                try:
                    os.unlink(processed_audio)
                    self.logger.debug(f"    🧹 Удален временный файл: {processed_audio}")
                except:
                    self.logger.warning(f"    ⚠️ Не удалось удалить временный файл: {processed_audio}")
    
    def _try_sphinx_directly(self, audio_path: str) -> str:
        """Прямая попытка Sphinx без fallback'ов"""
        self.logger.info(f"    🎯 SPHINX: Начало обработки")
        self.logger.info(f"    📁 Файл: {audio_path}")
        
        try:
            language = getattr(self.config, 'SPEECH_LANGUAGE', 'en-US')
            self.logger.info(f"    🌍 Язык: {language}")
            
            # Проверяем метод
            if not hasattr(self.speech_recognizer, '_try_sphinx'):
                self.logger.error(f"    ❌ Метод _try_sphinx не найден!")
                return ""
            
            self.logger.info(f"    ✅ Метод _try_sphinx найден")
            
            # Вызов Sphinx
            self.logger.info(f"    🔄 Вызов Sphinx...")
            sphinx_start = time.time()
            result = self.speech_recognizer._try_sphinx(
                audio_path, 
                language
            )
            sphinx_time = time.time() - sphinx_start
            
            self.logger.info(f"    ⏱️ Sphinx выполнен за {sphinx_time:.2f}с")
            self.logger.info(f"    📊 Результат: {type(result)}, '{result}'")
            
            if result and result.strip():
                self.logger.info(f"    ✅ Sphinx вернул текст: {len(result)} символов")
                self.logger.info(f"    📝 Превью: '{result[:50]}...'")
                return result
            else:
                self.logger.warning(f"    ⚠️ Sphinx не вернул результат")
                return ""
                
        except Exception as e:
            self.logger.error(f"    ❌ SPHINX: Критическая ошибка: {e}")
            self.logger.error(f"    🔍 Тип ошибки: {type(e).__name__}")
            
            import traceback
            self.logger.debug(f"    🔍 Трассировка Sphinx:")
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.debug(f"      {line}")
            
            return ""
    
    def _transcribe_with_auto_fallback(self, audio_path: str, preferred_engine: str = None) -> str:
        """
        Автоматический режим: динамически определяет порядок движков на основе их доступности
        
        Args:
            audio_path: путь к аудиофайлу
            preferred_engine: предпочтительный движок (попробуем первым если доступен)
            
        Returns:
            str: распознанный текст
            
        Raises:
            ValueError: если ни один движок не сработал
        """
        self.logger.info("=" * 80)
        self.logger.info(f"🔄 НАЧАЛО АВТОМАТИЧЕСКОГО РЕЖИМА")
        self.logger.info(f"📁 Аудио файл: {audio_path}")
        self.logger.info(f"🎯 Предпочтительный движок: {preferred_engine}")
        
        # Проверяем что файл существует
        if not os.path.exists(audio_path):
            self.logger.error(f"❌ Аудио файл не существует: {audio_path}")
            raise ValueError(f"Аудио файл не найден: {audio_path}")
        
        file_size = os.path.getsize(audio_path)
        self.logger.info(f"📊 Размер аудио файла: {file_size} байт")
        
        # Определяем динамический порядок движков на основе доступности
        self.logger.info("🔍 ЭТАП 1: Тестирование доступности движков...")
        available_engines = self.speech_recognizer.test_recognition_engines()
        self.logger.info(f"📊 Результат теста доступности: {available_engines}")
        
        # Разделяем движки на доступные и недоступные
        working_engines = [engine for engine, available in available_engines.items() if available]
        broken_engines = [engine for engine, available in available_engines.items() if not available]
        
        self.logger.info(f"✅ Доступные движки: {working_engines}")
        self.logger.info(f"❌ Недоступные движки: {broken_engines}")
        
        # Формируем динамический порядок попыток
        engines_to_try = []
        
        # Если есть предпочтительный движок и он доступен, пробуем его первым
        if preferred_engine and preferred_engine in working_engines:
            engines_to_try.append(preferred_engine)
            working_engines.remove(preferred_engine)  # убираем из списка чтобы не дублировать
            self.logger.info(f"⭐ Предпочтительный движок {preferred_engine} доступен - будет первым")
        elif preferred_engine and preferred_engine in broken_engines:
            self.logger.warning(f"⚠️ Предпочтительный движок {preferred_engine} недоступен - попробуем в конце")
        
        # Добавляем доступные движки (приоритет работающим)
        engines_to_try.extend(working_engines)
        
        # Добавляем недоступные движки в конце (на случай если тест ошибся)
        engines_to_try.extend(broken_engines)
        
        self.logger.info(f"📋 ДИНАМИЧЕСКИЙ ПОРЯДОК попыток: {engines_to_try}")
        self.logger.info(f"💡 Логика: сначала доступные движки, потом недоступные (на случай ошибки теста)")
        self.logger.info("⚠️  ВАЖНО: Реальные попытки покажут истинную работоспособность")
        
        # Пробуем движки по очереди
        successful_attempts = []
        failed_attempts = []
        
        for i, engine in enumerate(engines_to_try):
            self.logger.info("-" * 60)
            
            # Определяем статус движка для информативного лога
            engine_status = "✅ ДОСТУПЕН" if engine in [e for e, a in available_engines.items() if a] else "❌ НЕДОСТУПЕН (по тесту)"
            self.logger.info(f"🤖 ПОПЫТКА {i+1}/{len(engines_to_try)}: ДВИЖОК {engine.upper()} ({engine_status})")
            self.logger.info(f"⏰ Время начала попытки: {time.strftime('%H:%M:%S')}")
            
            try:
                start_time = time.time()
                
                # Пробуем движок БЕЗ предварительной проверки доступности (реальный тест)
                self.logger.info(f"🔍 Реальная проверка работоспособности движка {engine}...")
                result = self._try_engine_without_availability_check(audio_path, engine)
                
                elapsed_time = time.time() - start_time
                self.logger.info(f"⏱️ Время выполнения движка {engine}: {elapsed_time:.2f} секунд")
                
                if result and result.strip():
                    self.logger.info(f"✅ УСПЕХ! Движок {engine} распознал речь на попытке {i+1}")
                    self.logger.info(f"📝 Длина результата: {len(result)} символов")
                    self.logger.info(f"📝 Первые 100 символов: '{result[:100]}...'")
                    self.logger.info(f"🎉 ДИНАМИЧЕСКИЙ АВТОМАТИЧЕСКИЙ РЕЖИМ ЗАВЕРШЕН УСПЕШНО с движком {engine}")
                    if engine in [e for e, a in available_engines.items() if a]:
                        self.logger.info(f"💡 Движок {engine} был в списке доступных - прогноз подтвердился")
                    else:
                        self.logger.info(f"💡 Движок {engine} считался недоступным, но реально сработал - тест ошибся!")
                    self.logger.info("=" * 80)
                    return result.strip()
                else:
                    failed_attempts.append(f"{engine}: пустой результат")
                    self.logger.warning(f"⚠️ Движок {engine} вернул пустой результат")
                    self.logger.warning(f"📊 Тип результата: {type(result)}, значение: '{result}'")
                    
            except Exception as e:
                elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
                failed_attempts.append(f"{engine}: {str(e)}")
                self.logger.error(f"❌ Движок {engine} упал с ошибкой: {e}")
                self.logger.error(f"🕐 Время до ошибки: {elapsed_time:.2f} секунд")
                
                # Подробная информация об ошибке
                import traceback
                self.logger.debug(f"🔍 Полный стек ошибки для {engine}:")
                self.logger.debug(traceback.format_exc())
                
            # Продолжаем к следующему движку
            if i < len(engines_to_try) - 1:
                self.logger.info(f"🔄 Переходим к следующему движку...")
            else:
                self.logger.warning(f"⚠️ Это была последняя попытка")
        
        # Если дошли сюда, ни один движок не сработал
        self.logger.error("=" * 80)
        self.logger.error(f"❌ ВСЕ ДВИЖКИ НЕ СРАБОТАЛИ В ДИНАМИЧЕСКОМ РЕЖИМЕ!")
        self.logger.error(f"📋 Подробные детали всех неудач:")
        for i, failure in enumerate(failed_attempts, 1):
            self.logger.error(f"   {i}. {failure}")
        
        self.logger.error(f"📁 Проблемный файл: {audio_path}")
        self.logger.error(f"📊 Размер файла: {file_size} байт")
        self.logger.error(f"📊 Тест доступности показал: {available_engines}")
        self.logger.error(f"🔄 Динамический порядок попыток: {', '.join(engines_to_try)}")
        self.logger.error(f"💡 Сначала пробовались доступные движки, потом недоступные")
        
        error_msg = f"Ни один из движков ({', '.join(engines_to_try)}) не смог распознать аудио в файле {audio_path}"
        self.logger.error(f"❌ Финальная ошибка: {error_msg}")
        self.logger.error("=" * 80)
        raise ValueError(error_msg)
    
    def _try_engine_without_availability_check(self, audio_path: str, engine: str) -> str:
        """
        Пробует движок напрямую без предварительной проверки доступности
        
        Args:
            audio_path: путь к аудиофайлу
            engine: движок распознавания
            
        Returns:
            str: распознанный текст или пустая строка при ошибке
        """
        self.logger.info(f"  🔍 НАЧАЛО: Прямая попытка движка {engine}")
        self.logger.info(f"  📁 Файл: {audio_path}")
        
        try:
            # Проверяем поддержку движка
            supported_engines = ['whisper', 'google', 'sphinx']
            if engine not in supported_engines:
                self.logger.error(f"  ❌ ОШИБКА: Неизвестный движок {engine}")
                self.logger.error(f"  📋 Поддерживаемые движки: {supported_engines}")
                return ""
            
            self.logger.info(f"  ✅ Движок {engine} поддерживается")
            
            # Вызываем конкретный метод движка напрямую
            result = None
            method_start_time = time.time()
            
            if engine == 'whisper':
                self.logger.info(f"  🤖 Вызываем _try_whisper_directly...")
                result = self._try_whisper_directly(audio_path)
            elif engine == 'google':
                self.logger.info(f"  🤖 Вызываем _try_google_directly...")
                result = self._try_google_directly(audio_path)
            elif engine == 'sphinx':
                self.logger.info(f"  🤖 Вызываем _try_sphinx_directly...")
                result = self._try_sphinx_directly(audio_path)
            
            method_time = time.time() - method_start_time
            self.logger.info(f"  ⏱️ Время выполнения метода движка: {method_time:.2f} секунд")
            
            # Анализируем результат
            if result is None:
                self.logger.warning(f"  ⚠️ Движок {engine} вернул None")
                return ""
            elif result == "":
                self.logger.warning(f"  ⚠️ Движок {engine} вернул пустую строку")
                return ""
            elif isinstance(result, str) and result.strip():
                self.logger.info(f"  ✅ УСПЕХ: Движок {engine} вернул текст")
                self.logger.info(f"  📝 Длина: {len(result)} символов")
                self.logger.info(f"  📝 Превью: '{result[:50]}...'")
                return result
            else:
                self.logger.warning(f"  ⚠️ Движок {engine} вернул неожиданный тип: {type(result)}")
                self.logger.warning(f"  📊 Значение: {repr(result)}")
                return ""
                
        except Exception as e:
            self.logger.error(f"  ❌ ИСКЛЮЧЕНИЕ в движке {engine}: {e}")
            self.logger.error(f"  🔍 Тип исключения: {type(e).__name__}")
            
            # Детальная трассировка для отладки
            import traceback
            self.logger.debug(f"  🔍 Полная трассировка для {engine}:")
            for line in traceback.format_exc().split('\n'):
                if line.strip():
                    self.logger.debug(f"    {line}")
            
            return ""


    def setup_logging(self):
        """Настройка логирования"""
        logging.basicConfig(
            level=getattr(logging, self.config.LOG_LEVEL),
            format=self.config.LOG_FORMAT,
            handlers=[
                logging.FileHandler(self.config.LOG_FILE, mode='w'),  # 'w' = перезапись файла
                logging.StreamHandler()
            ],
            force=True  # Принудительно перенастраиваем логгер
        )
        self.logger = logging.getLogger(__name__)

    def _log_component_status(self):
        """Логирование статуса всех компонентов"""
        # Статус переводчика
        translator_status = get_translator_status()
        self.logger.info(f"Переводчик: {translator_status['type']} - {translator_status['description']}")

        # Статус TTS движков
        tts_engines = self.speech_synthesizer.test_tts_engines()
        available_tts = [name for name, available in tts_engines.items() if available]
        self.logger.info(f"Доступные TTS движки: {', '.join(available_tts) if available_tts else 'Нет'}")

        # Статус движков распознавания речи
        sr_engines = self.speech_recognizer.test_recognition_engines()
        available_sr = [name for name, available in sr_engines.items() if available]
        self.logger.info(f"Доступные SR движки: {', '.join(available_sr) if available_sr else 'Нет'}")

    def _format_time(self, seconds: float) -> str:
        """Форматирование времени в MM:SS или HH:MM:SS"""
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"

    def save_recognition_results(self, video_path: str, segments: List[Dict], output_dir: str = None) -> str:
        """
        Сохранение результатов распознавания речи

        Args:
            video_path: путь к исходному видео
            segments: список сегментов с распознанным текстом
            output_dir: директория для сохранения (по умолчанию outputs/)

        Returns:
            str: путь к сохраненному файлу
        """
        try:
            if output_dir is None:
                output_dir = self.config.OUTPUT_FOLDER

            # Создание имени файла на основе видео
            video_name = Path(video_path).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = Path(output_dir) / f"{video_name}_recognition_{timestamp}.txt"

            # Подготовка данных для сохранения
            recognition_data = {
                'source_video': str(Path(video_path).name),
                'processing_date': datetime.now().isoformat(),
                'total_segments': len(segments),
                'segments': []
            }

            # Текстовый вывод для удобного чтения
            text_content = []
            text_content.append(f"РАСПОЗНАВАНИЕ РЕЧИ")
            text_content.append(f"Видео: {Path(video_path).name}")
            text_content.append(f"Дата обработки: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
            text_content.append(f"Всего сегментов: {len(segments)}")
            text_content.append("=" * 60)
            text_content.append("")

            for segment in segments:
                segment_info = {
                    'id': segment.get('id', 0),
                    'start_time': segment.get('start_time', 0),
                    'end_time': segment.get('end_time', 0),
                    'duration': segment.get('duration', 0),
                    'text': segment.get('original_text', ''),
                    'status': 'recognized' if segment.get('original_text') else 'no_speech'
                }
                recognition_data['segments'].append(segment_info)

                # Форматированный текстовый вывод
                start_time = segment.get('start_time', 0)
                end_time = segment.get('end_time', 0)
                original_text = segment.get('original_text', '[речь не распознана]')

                text_content.append(f"[{self._format_time(start_time)} - {self._format_time(end_time)}]")
                text_content.append(f"{original_text}")
                text_content.append("")

            # Сохранение текстового файла
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(text_content))

            # Сохранение JSON файла для программного доступа
            json_file = output_file.with_suffix('.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(recognition_data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"Результаты распознавания сохранены: {output_file}")
            return str(output_file)

        except Exception as e:
            self.logger.error(f"Ошибка сохранения результатов распознавания: {e}")
            return ""

    def save_translation_results(self, video_path: str, segments: List[Dict], output_dir: str = None, source_language: str = 'auto', target_language: str = 'ru') -> str:
        """
        Сохранение результатов перевода

        Args:
            video_path: путь к исходному видео
            segments: список сегментов с переведенным текстом
            output_dir: директория для сохранения (по умолчанию outputs/)

        Returns:
            str: путь к сохраненному файлу
        """
        try:
            if output_dir is None:
                output_dir = self.config.OUTPUT_FOLDER

            # Создание имени файла
            video_name = Path(video_path).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = Path(output_dir) / f"{video_name}_translation_{timestamp}.txt"

            # Подготовка данных
            translation_data = {
                'source_video': str(Path(video_path).name),
                'processing_date': datetime.now().isoformat(),
                'source_language': source_language,
                'target_language': target_language,
                'translator_type': self.get_translator_status()['type'],
                'total_segments': len(segments),
                'segments': []
            }

            # Текстовый вывод
            text_content = []
            text_content.append(f"ПЕРЕВОД ТЕКСТА")
            text_content.append(f"Видео: {Path(video_path).name}")
            text_content.append(f"Дата обработки: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
            text_content.append(f"Направление перевода: {self.config.SOURCE_LANGUAGE} → {self.config.TARGET_LANGUAGE}")
            text_content.append(f"Переводчик: {self.get_translator_status()['type']}")
            text_content.append(f"Всего сегментов: {len(segments)}")
            text_content.append("=" * 60)
            text_content.append("")

            for segment in segments:
                segment_info = {
                    'id': segment.get('id', 0),
                    'start_time': segment.get('start_time', 0),
                    'end_time': segment.get('end_time', 0),
                    'duration': segment.get('duration', 0),
                    'original_text': segment.get('original_text', ''),
                    'translated_text': segment.get('translated_text', ''),
                    'status': segment.get('status', 'unknown')
                }
                translation_data['segments'].append(segment_info)

                # Форматированный вывод
                start_time = segment.get('start_time', 0)
                end_time = segment.get('end_time', 0)
                original_text = segment.get('original_text', '[нет текста]')
                translated_text = segment.get('translated_text', '[нет перевода]')

                text_content.append(f"[{self._format_time(start_time)} - {self._format_time(end_time)}]")
                source_label, target_label = self._get_dynamic_language_labels(source_language, target_language)
                text_content.append(f"{source_label}: {original_text}")
                text_content.append(f"{target_label}: {translated_text}")
                text_content.append("")

            # Сохранение файлов
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(text_content))

            json_file = output_file.with_suffix('.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(translation_data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"Результаты перевода сохранены: {output_file}")
            return str(output_file)

        except Exception as e:
            self.logger.error(f"Ошибка сохранения результатов перевода: {e}")
            return ""

    def save_complete_transcript(self, video_path: str, segments: List[Dict], output_dir: str = None, source_language: str = 'auto', target_language: str = 'ru') -> str:
        """
        Сохранение полного транскрипта (оригинал + перевод + временные метки)

        Args:
            video_path: путь к исходному видео
            segments: список сегментов с полной информацией
            output_dir: директория для сохранения

        Returns:
            str: путь к сохраненному файлу
        """
        try:
            if output_dir is None:
                output_dir = self.config.OUTPUT_FOLDER

            video_name = Path(video_path).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = Path(output_dir) / f"{video_name}_complete_{timestamp}.txt"

            # Статистика
            total_segments = len(segments)
            successful_segments = sum(1 for s in segments if s.get('original_text'))
            translated_segments = sum(1 for s in segments if s.get('translated_text'))

            text_content = []
            text_content.append(f"ПОЛНЫЙ ТРАНСКРИПТ И ПЕРЕВОД")
            text_content.append(f"Видео: {Path(video_path).name}")
            text_content.append(f"Дата обработки: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
            text_content.append(
                f"Общая длительность: {self._format_time(segments[-1].get('end_time', 0)) if segments else '0:00'}")
            text_content.append(f"Всего сегментов: {total_segments}")
            text_content.append(
                f"Распознано: {successful_segments} ({successful_segments / total_segments * 100:.1f}%)")
            text_content.append(
                f"Переведено: {translated_segments} ({translated_segments / total_segments * 100:.1f}%)")
            text_content.append("=" * 80)
            text_content.append("")

            for i, segment in enumerate(segments, 1):
                start_time = segment.get('start_time', 0)
                end_time = segment.get('end_time', 0)
                duration = segment.get('duration', 0)
                original_text = segment.get('original_text', '')
                translated_text = segment.get('translated_text', '')
                status = segment.get('status', 'unknown')

                text_content.append(f"СЕГМЕНТ {i}")
                text_content.append(
                    f"Время: {self._format_time(start_time)} - {self._format_time(end_time)} ({duration:.1f}s)")
                text_content.append(f"Статус: {status}")

                source_label, target_label = self._get_dynamic_language_labels(source_language, target_language)
                
                if original_text:
                    text_content.append(f"{source_label}: {original_text}")
                else:
                    text_content.append(f"{source_label}: [речь не распознана]")

                if translated_text:
                    text_content.append(f"{target_label}: {translated_text}")
                else:
                    text_content.append(f"{target_label}: [нет перевода]")

                text_content.append("-" * 40)
                text_content.append("")

            # Сохранение
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(text_content))

            self.logger.info(f"Полный транскрипт сохранен: {output_file}")
            return str(output_file)

        except Exception as e:
            self.logger.error(f"Ошибка сохранения полного транскрипта: {e}")
            return ""

    def save_subtitles_srt(self, video_path: str, segments: List[Dict], output_dir: str = None, subtitle_type: str = "both", source_language: str = 'auto', target_language: str = 'ru') -> str:
        """
        Сохранение субтитров в формате SRT для видео плеера
        
        Args:
            video_path: путь к исходному видео
            segments: список сегментов с полной информацией
            output_dir: директория для сохранения
            subtitle_type: тип субтитров ("original", "translated", "both")
            
        Returns:
            str: путь к сохраненному SRT файлу
        """
        try:
            video_name = Path(video_path).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if output_dir is None:
                output_dir = getattr(self.config, 'output_folder', 'outputs')
            
            # Создаем разные типы SRT файлов
            srt_files = []
            
            if subtitle_type in ["original", "both"]:
                srt_file_original = Path(output_dir) / f"{video_name}_subtitles_original_{timestamp}.srt"
                self._create_srt_file(segments, srt_file_original, "original", source_language, target_language)
                srt_files.append(str(srt_file_original))
                
            if subtitle_type in ["translated", "both"]:
                srt_file_translated = Path(output_dir) / f"{video_name}_subtitles_translated_{timestamp}.srt"
                self._create_srt_file(segments, srt_file_translated, "translated", source_language, target_language)
                srt_files.append(str(srt_file_translated))
            
            if subtitle_type == "both":
                srt_file_dual = Path(output_dir) / f"{video_name}_subtitles_dual_{timestamp}.srt"
                self._create_srt_file(segments, srt_file_dual, "dual", source_language, target_language)
                srt_files.append(str(srt_file_dual))
            
            self.logger.info(f"SRT субтитры сохранены: {', '.join([Path(f).name for f in srt_files])}")
            return srt_files[0] if srt_files else ""
            
        except Exception as e:
            self.logger.error(f"Ошибка создания SRT субтитров: {e}")
            return ""
    
    def _create_srt_file(self, segments: List[Dict], output_file: Path, subtitle_type: str, source_language: str = 'auto', target_language: str = 'ru'):
        """Создание конкретного SRT файла"""
        def format_time(seconds: float) -> str:
            """Форматирование времени для SRT"""
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millisecs = int((seconds % 1) * 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
        
        def format_subtitle_text(text: str, max_chars_per_line: int = 45, max_lines: int = 4) -> str:
            """
            Форматирование текста субтитров для удобочитаемости
            
            Args:
                text: исходный текст
                max_chars_per_line: максимум символов в строке (уменьшено с 60 до 35)
                max_lines: максимум строк в субтитре (новый параметр)
            """
            if not text:
                return text
            
            # Если текст короткий, возвращаем как есть
            if len(text) <= max_chars_per_line:
                return text
            
            # Разбиваем текст на слова
            words = text.strip().split()
            if not words:
                return text
            
            formatted_lines = []
            current_line = ""
            
            for word in words:
                # Проверяем, поместится ли слово в текущую строку
                test_line = current_line + (" " + word if current_line else word)
                
                if len(test_line) <= max_chars_per_line:
                    current_line = test_line
                else:
                    # Если текущая строка не пустая, сохраняем её
                    if current_line:
                        formatted_lines.append(current_line)
                        
                        # Ограничиваем количество строк
                        if len(formatted_lines) >= max_lines:
                            break
                    
                    # Начинаем новую строку
                    # Если слово слишком длинное, обрезаем его
                    if len(word) > max_chars_per_line:
                        current_line = word[:max_chars_per_line-3] + "..."
                    else:
                        current_line = word
            
            # Добавляем последнюю строку, если есть место
            if current_line and len(formatted_lines) < max_lines:
                formatted_lines.append(current_line)
            
            # Если текст не поместился полностью, добавляем многоточие
            if len(formatted_lines) == max_lines and len(words) > sum(len(line.split()) for line in formatted_lines):
                if formatted_lines:
                    last_line = formatted_lines[-1]
                    if len(last_line) <= max_chars_per_line - 3:
                        formatted_lines[-1] = last_line + "..."
                    else:
                        formatted_lines[-1] = last_line[:max_chars_per_line-3] + "..."
            
            return '\n'.join(formatted_lines)
        
        srt_content = []
        subtitle_index = 1
        
        def split_long_segment_for_subtitles(segment, max_duration=12.0, max_chars_total=180):
            """
            Умно разбивает длинные сегменты для субтитров
            
            Args:
                segment: исходный сегмент
                max_duration: максимальная длительность одного субтитра (увеличено с 8 до 12 сек)
                max_chars_total: максимальное количество символов в одном субтитре (45*4=180)
            """
            duration = segment.get('end_time', 0) - segment.get('start_time', 0)
            original_text = segment.get('original_text', segment.get('text', ''))
            translated_text = segment.get('translated_text', '')
            
            # Определяем основной текст для анализа (приоритет переводу)
            main_text = translated_text or original_text
            
            # Если сегмент достаточно короткий по времени И по тексту, оставляем как есть
            if duration <= max_duration and len(main_text) <= max_chars_total:
                return [segment]
            
            # Разбиваем текст на логические части
            def smart_text_split(text, max_chars):
                if not text or len(text) <= max_chars:
                    return [text]
                
                import re
                
                # Сначала пробуем разбить по предложениям
                sentences = re.split(r'([.!?]+\s+)', text)
                if len(sentences) < 3:  # Если предложений мало, разбиваем по другим знакам
                    sentences = re.split(r'([,;:]\s+|\s+и\s+|\s+а\s+|\s+но\s+|\s+что\s+)', text)
                
                # Группируем предложения в части
                parts = []
                current_part = ""
                
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    
                    test_part = current_part + (" " + sentence if current_part else sentence)
                    
                    if len(test_part) <= max_chars:
                        current_part = test_part
                    else:
                        if current_part:
                            parts.append(current_part.strip())
                        
                        # Если одно предложение слишком длинное, разбиваем по словам
                        if len(sentence) > max_chars:
                            words = sentence.split()
                            temp_part = ""
                            for word in words:
                                test_word = temp_part + (" " + word if temp_part else word)
                                if len(test_word) <= max_chars:
                                    temp_part = test_word
                                else:
                                    if temp_part:
                                        parts.append(temp_part.strip())
                                    temp_part = word
                            if temp_part:
                                current_part = temp_part
                        else:
                            current_part = sentence
                
                if current_part:
                    parts.append(current_part.strip())
                
                return [part for part in parts if part.strip()]
            
            # Разбиваем оба текста
            original_parts = smart_text_split(original_text, max_chars_total)
            translated_parts = smart_text_split(translated_text, max_chars_total)
            
            # Берем максимальное количество частей
            max_parts = max(len(original_parts), len(translated_parts), 1)
            
            # Создаем субсегменты
            sub_segments = []
            part_duration = duration / max_parts
            
            for i in range(max_parts):
                start = segment['start_time'] + i * part_duration
                end = segment['start_time'] + (i + 1) * part_duration
                
                # Берем соответствующие части текста
                orig_part = original_parts[i] if i < len(original_parts) else ""
                trans_part = translated_parts[i] if i < len(translated_parts) else ""
                
                # Создаем субсегмент только если есть хоть какой-то текст
                if orig_part or trans_part:
                    sub_segments.append({
                        **segment,
                        'start_time': start,
                        'end_time': end,
                        'original_text': orig_part,
                        'translated_text': trans_part
                    })
            
            return sub_segments if sub_segments else [segment]
        
        for segment in segments:
            # Разбиваем длинные сегменты на более короткие
            sub_segments = split_long_segment_for_subtitles(segment, max_duration=12.0)
            
            for sub_segment in sub_segments:
                start_time = sub_segment.get('start_time', 0)
                end_time = sub_segment.get('end_time', start_time + 1)
                
                original_text = sub_segment.get('original_text', sub_segment.get('text', ''))
                translated_text = sub_segment.get('translated_text', '')
                
                # Пропускаем пустые субсегменты
                if not original_text and not translated_text:
                    continue
                
                # Определяем текст субтитров
                if subtitle_type == "original":
                    subtitle_text = format_subtitle_text(original_text or '[речь не распознана]')
                elif subtitle_type == "translated":
                    subtitle_text = format_subtitle_text(translated_text or '[нет перевода]')
                elif subtitle_type == "dual":
                    lines = []
                    source_label, target_label = self._get_dynamic_language_labels(source_language, target_language)
                    if original_text:
                        lines.append(f"{source_label}: {format_subtitle_text(original_text, 40, 2)}")
                    if translated_text:
                        lines.append(f"{target_label}: {format_subtitle_text(translated_text, 40, 2)}")
                    subtitle_text = '\n'.join(lines) if lines else '[нет текста]'
                
                # Пропускаем очень короткие субтитры
                if len(subtitle_text.strip()) < 3:
                    continue
                
                # Добавляем в SRT
                srt_content.append(str(subtitle_index))
                srt_content.append(f"{format_time(start_time)} --> {format_time(end_time)}")
                srt_content.append(subtitle_text)
                srt_content.append("")  # Пустая строка между субтитрами
                
                subtitle_index += 1
        
        # Сохраняем файл
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(srt_content))

    def translate_video(self, video_path: str, output_path: str, progress_callback: Callable = None,
                        save_texts: bool = True, speech_engine: str = 'whisper', 
                        whisper_model: str = 'base', output_format: str = 'TRANSLATION_ONLY',
                        source_language: str = 'auto', target_language: str = 'ru') -> bool:
        """
        Основная функция перевода видео с сохранением текстов

        Args:
            video_path: путь к исходному видео
            output_path: путь для сохранения результата
            progress_callback: функция для отслеживания прогресса
            save_texts: сохранять ли текстовые результаты
            speech_engine: движок распознавания (только 'whisper')
            whisper_model: модель Whisper ('tiny', 'base', 'small', 'medium', 'large', 'large-v2', 'large-v3')
            output_format: формат вывода ('TRANSLATION_ONLY', 'SUBTITLES_ONLY', 'TRANSLATION_WITH_SUBTITLES')
            source_language: исходный язык ('auto' для автоопределения или код языка)
            target_language: целевой язык (код языка DeepL)

        Returns:
            bool: True при успехе, False при ошибке
        """
        start_time = time.time()

        try:
            self.logger.info(f"Начало перевода видео: {video_path} -> {output_path}")
            self.logger.info(f"📋 Настройки: движок={speech_engine}, модель={whisper_model}, формат={output_format}")
            self.logger.info(f"🌍 Языки: {source_language} → {target_language}")
            
            # Настраиваем TTS для целевого языка
            self._setup_tts_for_language(target_language)
            
            # Устанавливаем модель Whisper в SpeechRecognizer
            if hasattr(self.speech_recognizer, 'set_whisper_model'):
                self.speech_recognizer.set_whisper_model(whisper_model)
                self.logger.info(f"🎯 Установлена модель Whisper: {whisper_model}")
            
            # Логика выбора движка распознавания
            if speech_engine == 'auto':
                # В автоматическом режиме НЕ выбираем конкретный движок заранее
                selected_engine = 'auto'
                self.logger.info(f"🤖 Автоматический режим: будем пробовать все доступные движки")
            else:
                # В ручном режиме проверяем доступность указанного движка
                selected_engine = self._select_speech_engine(speech_engine, video_path)
                self.logger.info(f"🎯 Выбран движок по требованию пользователя: {selected_engine}")

            # Валидация входного файла
            validation = self.video_processor.validate_video_file(video_path)
            if not validation['valid']:
                error_msg = f"Валидация файла неудачна: {validation.get('error', 'неизвестная ошибка')}"
                self.logger.error(error_msg)
                if progress_callback:
                    progress_callback("Ошибка валидации файла", 0)
                return False

            video_info = validation['info']
            self.logger.info(f"Видео информация: {video_info['duration']:.1f}s, "
                             f"{video_info['size']}, {video_info['file_size_mb']:.1f}MB")

            # 1. Извлечение аудио
            if progress_callback:
                progress_callback("Извлечение аудио из видео", 10)

            audio_path, video_info = self.video_processor.extract_audio(video_path)
            if not audio_path:
                if progress_callback:
                    progress_callback("Ошибка извлечения аудио", 0)
                return False

            # 2. Сегментация аудио (временно отключены Whisper timestamps)
            if progress_callback:
                progress_callback("Сегментация аудио по паузам", 20)

            # Выбор метода сегментации в зависимости от настроек
            use_speaker_segments = getattr(self.config, 'USE_SPEAKER_DIARIZATION', False)
            
            if use_speaker_segments:
                self.logger.info("🎭 Используем сегментацию по спикерам")
                segments = self.speaker_diarization.segment_by_speakers(audio_path)
                
                # Объединяем короткие сегменты одного спикера
                segments = self.speaker_diarization.merge_short_segments(segments, min_duration=5.0)
                
                if not segments:
                    self.logger.warning("⚠️ Сегментация по спикерам не удалась, используем обычную")
                    segments = self.audio_processor.segment_audio(audio_path)
            else:
                self.logger.info("🔄 Используем стабильную сегментацию по паузам")
                segments = self.audio_processor.segment_audio(audio_path)
            
            if not segments:
                self.logger.error("Ошибка сегментации аудио")
                if progress_callback:
                    progress_callback("Ошибка сегментации аудио", 0)
                return False
                
            self.logger.info(f"✅ Создано {len(segments)} сегментов по паузам")
            
            # Применяем Voice Activity Detection для фильтрации сегментов без речи
            if progress_callback:
                progress_callback("Анализ речевой активности", 18)
            
            self.logger.info("🎤 Применяем Voice Activity Detection...")
            segments = self.voice_activity_detector.filter_speech_segments(segments, min_confidence=0.4)
            
            speech_segments = [s for s in segments if s.get('vad_is_speech', True)]
            self.logger.info(f"🎯 После VAD: {len(speech_segments)}/{len(segments)} сегментов содержат речь")

            # 3. Обработка каждого сегмента
            translated_segments = []
            total_segments = len(segments)
            successful_segments = 0

            for i, segment in enumerate(segments):
                try:
                    # Обновление прогресса
                    progress = 20 + (i / total_segments) * 50
                    if progress_callback:
                        progress_callback(f"Обработка сегмента {i + 1}/{total_segments}", int(progress))

                    segment_start_time = time.time()
                    self.logger.debug(f"Обработка сегмента {i + 1}/{total_segments}")

                    # Проверяем результат VAD - пропускаем сегменты без речи
                    self.logger.info(f"🔍 ГРАНИЦА СЕГМЕНТА {i + 1}/{total_segments}: Время {segment.get('start', 'N/A')} - {segment.get('end', 'N/A')} ({segment.get('duration', 'N/A')}s)")
                    self.logger.info(f"🔍 VAD статус: status={segment.get('status')}, vad_is_speech={segment.get('vad_is_speech')}")
                    
                    if segment.get('status') == 'no_speech_vad' or not segment.get('vad_is_speech', True):
                        self.logger.info(f"⏭️ Сегмент {i + 1}: пропускаем (нет речи по VAD)")
                        translated_segments.append({
                            **segment,
                            'original_text': '',
                            'translated_text': '',
                            'translated_audio_path': None,
                            'processing_time': time.time() - segment_start_time,
                            'status': 'no_speech_vad'
                        })
                        continue

                    # 3a. Распознавание речи (или использование уже распознанного из Whisper)
                    if segment.get('source') == 'whisper_timestamps':
                        # Для Whisper сегментов текст уже распознан
                        original_text = segment.get('original_text', '')
                        self.logger.info(f"🔍 ТЕКСТ ИЗ WHISPER {i + 1}: '{original_text}' (длина: {len(original_text)} символов)")
                        if len(original_text) == 0:
                            self.logger.warning(f"⚠️ ПУСТОЙ ТЕКСТ из Whisper сегмента {i + 1}!")
                    else:
                        # Обычное распознавание для сегментов по паузам с выбранным движком
                        is_manual_selection = speech_engine != 'auto'
                        original_text = self._transcribe_with_engine(segment['path'], selected_engine, is_manual_selection)
                        self.logger.info(f"🔍 ТЕКСТ РАСПОЗНАН {i + 1} через {selected_engine}: '{original_text}' (длина: {len(original_text)} символов)")

                    if not original_text:
                        self.logger.warning(f"❌ Сегмент {i + 1}: речь не распознана или текст пустой")
                        translated_segments.append({
                            **segment,
                            'original_text': '',
                            'translated_text': '',
                            'translated_audio_path': None,
                            'processing_time': time.time() - segment_start_time,
                            'status': 'no_speech'
                        })
                        continue

                    # 3b. Перевод текста
                    # Используем языки из параметров функции, а не из конфига
                    src_lang = source_language if source_language != 'auto' else self.config.SOURCE_LANGUAGE
                    tgt_lang = target_language
                    
                    self.logger.info(f"🔍 ПЕРЕВОД {i + 1}: '{original_text}' ({src_lang} -> {tgt_lang})")
                    
                    translated_text = translate_text(
                        original_text,
                        src_lang,
                        tgt_lang
                    )

                    if not translated_text:
                        self.logger.warning(f"⚠️ ПЕРЕВОД ПУСТОЙ для сегмента {i + 1}, используем оригинальный текст")
                        translated_text = original_text  # Fallback на оригинальный текст

                    self.logger.info(f"🔍 РЕЗУЛЬТАТ ПЕРЕВОДА {i + 1}: '{translated_text}' (длина: {len(translated_text)} символов)")
                    
                    # Проверяем на потерю важных фраз
                    if "кодовую базу" in original_text and "кодовую базу" not in translated_text:
                        self.logger.error(f"🚨 ПОТЕРЯ ФРАЗЫ 'кодовую базу' в сегменте {i + 1}! Оригинал: '{original_text}' -> Перевод: '{translated_text}'")
                    if "code base" in original_text and len(translated_text) < len(original_text) * 0.7:
                        self.logger.error(f"🚨 ПОДОЗРЕНИЕ НА ПОТЕРЮ ТЕКСТА в сегменте {i + 1}! Оригинал: {len(original_text)} -> Перевод: {len(translated_text)} символов")

                    # 3c. Синтез речи с учетом voice_id сегмента и target_duration для Google TTS
                    voice_id = segment.get('voice_id', None)  # Получаем назначенный голос
                    speaker_id = segment.get('speaker', None)  # Получаем speaker_id для voice cloning
                    segment_duration = segment.get('duration', None)  # Длительность сегмента

                    self.logger.info(f"🔍 TTS СИНТЕЗ {i + 1}: отправляем на синтез '{translated_text}' (язык: {target_language}, voice: {voice_id}, speaker: {speaker_id}, target_duration: {segment_duration}s)")

                    tts_path = self.speech_synthesizer.synthesize_speech(
                        translated_text,
                        target_language,
                        voice=voice_id,
                        target_duration=segment_duration,  # Передаем длительность для Google TTS timing adjustment
                        speaker_id=speaker_id  # Передаем speaker_id для voice cloning
                    )
                    
                    if tts_path:
                        self.logger.info(f"✅ TTS УСПЕШНО {i + 1}: создан файл {tts_path}")
                    else:
                        self.logger.error(f"❌ TTS ОШИБКА {i + 1}: не удалось создать аудио для '{translated_text}'")

                    if tts_path:
                        # 3d. Подгонка длительности
                        adjusted_tts_path = self.audio_processor.adjust_audio_duration(
                            tts_path,
                            segment['duration']
                        )
                        tts_path = adjusted_tts_path

                    processing_time = time.time() - segment_start_time
                    successful_segments += 1

                    self.logger.info(f"✅ СЕГМЕНТ {i + 1} ЗАВЕРШЕН: Оригинал='{original_text}' -> Перевод='{translated_text}' -> Аудио={tts_path is not None}")
                    self.logger.info(f"🔍 ФИНАЛЬНЫЙ РЕЗУЛЬТАТ {i + 1}: original_text='{original_text}', translated_text='{translated_text}', audio_path={tts_path}")

                    translated_segments.append({
                        **segment,
                        'original_text': original_text,
                        'translated_text': translated_text,
                        'translated_audio_path': tts_path,
                        'processing_time': processing_time,
                        'status': 'success' if tts_path else 'tts_failed'
                    })

                except Exception as e:
                    self.logger.error("🚨" * 30)
                    self.logger.error(f"🚨 ОШИБКА ПРИ ОБРАБОТКЕ СЕГМЕНТА {i + 1}/{total_segments}")
                    self.logger.error(f"📁 Аудио файл: {segment.get('path', 'N/A')}")
                    self.logger.error(f"⚙️ Движок: {speech_engine} ({'ручной' if speech_engine != 'auto' else 'автоматический'})")
                    self.logger.error(f"🔍 Тип ошибки: {type(e).__name__}")
                    self.logger.error(f"📝 Текст ошибки: {str(e)}")
                    
                    # Проверяем критические ошибки, которые должны остановить весь процесс
                    error_str = str(e)
                    is_critical_error = False
                    
                    if speech_engine != 'auto':
                        # При ручном выборе любая ошибка движка критическая
                        if isinstance(e, ValueError) and ("не работает" in error_str or "недоступен" in error_str or "не смог распознать" in error_str):
                            is_critical_error = True
                            self.logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: Ручной выбор движка '{speech_engine}' не сработал")
                            self.logger.error(f"🛑 Останавливаем весь процесс - пользователь указал конкретный движок")
                    else:
                        # В автоматическом режиме критична только ситуация, когда НИ ОДИН движок не сработал
                        if isinstance(e, ValueError) and "Ни один из доступных движков" in error_str:
                            is_critical_error = True
                            self.logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА: В автоматическом режиме НИ ОДИН движок не сработал")
                            self.logger.error(f"🛑 Останавливаем весь процесс - система распознавания полностью не работает")
                        else:
                            self.logger.warning(f"⚠️ В автоматическом режиме ошибка не критическая - продолжаем")
                    
                    if is_critical_error:
                        # Прерываем весь процесс
                        self.logger.error(f"🛑 ПРЕРЫВАНИЕ ВСЕГО ПРОЦЕССА ПЕРЕВОДА")
                        self.logger.error(f"📊 Статистика до прерывания: {successful_segments}/{i+1} сегментов обработано")
                        self.logger.error("🚨" * 30)
                        
                        if progress_callback:
                            progress_callback("Критическая ошибка системы распознавания", 0)
                        raise e  # Прокидываем ошибку наверх для остановки всего процесса
                    
                    # Для остальных ошибок продолжаем обработку
                    self.logger.warning(f"⚠️ Продолжаем обработку следующих сегментов...")
                    self.logger.error("🚨" * 30)
                    
                    # Детальная трассировка для отладки
                    import traceback
                    self.logger.debug(f"🔍 Полная трассировка ошибки сегмента {i+1}:")
                    for line in traceback.format_exc().split('\n'):
                        if line.strip():
                            self.logger.debug(f"  {line}")
                    
                    translated_segments.append({
                        **segment,
                        'original_text': '',
                        'translated_text': '',
                        'translated_audio_path': None,
                        'processing_time': time.time() - segment_start_time if 'segment_start_time' in locals() else 0,
                        'status': 'error',
                        'error': str(e)
                    })

            # Статистика обработки
            self.logger.info(f"Обработка сегментов завершена: {successful_segments}/{total_segments} успешно")

            # 4. Сохранение текстовых результатов
            if save_texts and progress_callback:
                progress_callback("Сохранение текстовых результатов", 75)

            saved_files = []
            if save_texts:
                try:
                    # Сохранение результатов распознавания
                    recognition_file = self.save_recognition_results(video_path, translated_segments)
                    if recognition_file:
                        saved_files.append(('recognition', recognition_file))

                    # Сохранение результатов перевода
                    translation_file = self.save_translation_results(video_path, translated_segments, source_language=source_language, target_language=target_language)
                    if translation_file:
                        saved_files.append(('translation', translation_file))

                    # Сохранение полного транскрипта
                    transcript_file = self.save_complete_transcript(video_path, translated_segments, source_language=source_language, target_language=target_language)
                    if transcript_file:
                        saved_files.append(('transcript', transcript_file))
                    
                    # Создание SRT субтитров
                    srt_file = self.save_subtitles_srt(video_path, translated_segments, subtitle_type="both", source_language=source_language, target_language=target_language)
                    if srt_file:
                        saved_files.append(('subtitles', srt_file))

                except Exception as e:
                    self.logger.error(f"Ошибка сохранения текстовых файлов: {e}")

            if progress_callback:
                progress_callback("Создание финального видео", 85)

            # 5. Создание финального видео с выбором метода синхронизации
            use_adaptive_timing = getattr(self.config, 'USE_ADAPTIVE_VIDEO_TIMING', True)
            # ВРЕМЕННО ОТКЛЮЧАЕМ блочную синхронизацию для использования VAD фильтрации
            use_block_sync = False  # getattr(self.config, 'USE_BLOCK_SYNCHRONIZATION', True)
            
            # Определяем нужно ли создавать видео или только субтитры
            create_video_with_audio = output_format in ['TRANSLATION_ONLY', 'TRANSLATION_WITH_SUBTITLES']
            
            if create_video_with_audio:
                # Создаем видео с переведенным аудио
                if use_block_sync:
                    # Новый блочный подход с точной синхронизацией
                    success = self._create_block_synchronized_video(video_path, translated_segments, output_path)
                elif use_adaptive_timing:
                    success = self._create_adaptive_final_video(video_path, translated_segments, output_path)
                else:
                    # Используем замедление видео по умолчанию для лучшей синхронизации
                    adjust_speed = getattr(self.config, 'ADJUST_VIDEO_SPEED', True)
                    success = self.video_processor.create_final_video(
                        video_path, translated_segments, output_path, 
                        adjust_video_speed=adjust_speed
                    )
            else:
                # Для SUBTITLES_ONLY - копируем оригинальное видео без изменений
                import shutil
                shutil.copy2(video_path, output_path)
                success = True
                self.logger.info(f"📹 Скопировано оригинальное видео для субтитров")
            
            # После создания видео, встраиваем субтитры если нужно
            if success and output_format in ['SUBTITLES_ONLY', 'TRANSLATION_WITH_SUBTITLES']:
                success = self._embed_subtitles_in_video(output_path, saved_files, target_language)

            if progress_callback:
                progress_callback("Завершено" if success else "Ошибка создания видео", 100 if success else 0)

            # 6. Очистка временных файлов
            self._cleanup_translation_files(audio_path, segments, translated_segments)

            # Финальная статистика
            total_time = time.time() - start_time
            self.logger.info(f"Перевод видео завершен за {total_time:.1f}s: {'успешно' if success else 'с ошибкой'}")

            if success and save_texts:
                self.logger.info(f"Сохранены текстовые файлы:")
                for file_type, file_path in saved_files:
                    self.logger.info(f"  - {file_type.title()}: {Path(file_path).name}")

            return success

        except Exception as e:
            total_time = time.time() - start_time
            self.logger.error(f"Критическая ошибка перевода видео за {total_time:.1f}s: {e}")
            if progress_callback:
                progress_callback("Критическая ошибка", 0)
            return False

    def _create_segments_from_whisper(self, whisper_result: dict, audio_path: str) -> List[Dict]:
        """
        Создает сегменты на основе временных меток Whisper
        
        Args:
            whisper_result: результат от transcribe_audio_with_timestamps
            audio_path: путь к оригинальному аудио файлу
            
        Returns:
            List[Dict]: список сегментов с временными метками
        """
        segments = []
        whisper_segments = whisper_result.get('segments', [])
        
        for i, whisper_seg in enumerate(whisper_segments):
            start_time = whisper_seg.get('start', 0)
            end_time = whisper_seg.get('end', 0)
            duration = end_time - start_time
            original_text = whisper_seg.get('text', '').strip()
            
            # Создаем временный аудио файл для этого сегмента (если нужно)
            segment_path = self.config.get_temp_filename(f"whisper_segment_{i}", ".wav")
            
            segment_data = {
                'id': i,
                'path': segment_path,  # Может быть пустой для Whisper сегментов
                'start_time': start_time,
                'end_time': end_time, 
                'duration': duration,
                'original_text': original_text,  # УЖЕ распознанный текст!
                'source': 'whisper_timestamps'
            }
            
            segments.append(segment_data)
            
            self.logger.debug(f"Whisper сегмент {i+1}: {start_time:.1f}-{end_time:.1f}с '{original_text[:50]}...'")
        
        self.logger.info(f"🕒 Создано {len(segments)} сегментов по временным меткам Whisper")
        return segments

    def _create_adaptive_final_video(self, video_path: str, segments: List[Dict], output_path: str) -> bool:
        """
        Создает финальное видео с адаптивной синхронизацией времени
        
        Args:
            video_path: путь к исходному видео
            segments: переведенные сегменты
            output_path: путь для сохранения результата
            
        Returns:
            bool: успешность создания видео
        """
        try:
            self.logger.info("🎬 Создание адаптивного финального видео")
            
            # Сначала создаем обычное видео
            temp_video_path = output_path.replace('.mp4', '_temp.mp4')
            adjust_speed = getattr(self.config, 'ADJUST_VIDEO_SPEED', True)
            success = self.video_processor.create_final_video(
                video_path, segments, temp_video_path, 
                adjust_video_speed=adjust_speed
            )
            
            if not success:
                self.logger.error("❌ Не удалось создать базовое видео")
                return False
            
            # Получаем путь к финальному аудио
            final_audio_path = self._find_combined_audio_path()
            
            if not final_audio_path:
                self.logger.warning("⚠️ Не найден путь к финальному аудио, используем обычное видео")
                if Path(temp_video_path).exists():
                    Path(temp_video_path).rename(output_path)
                    self.logger.info("✅ Базовое видео переименовано в финальное")
                    return True
                else:
                    self.logger.error("❌ Временное видео не найдено")
                    return False
            
            # Проверяем необходимость адаптации времени
            video_duration = self.video_adjuster._get_media_duration(video_path)
            audio_duration = self.video_adjuster._get_media_duration(final_audio_path)
            
            self.logger.info(f"📊 Оригинальное видео: {video_duration:.2f}s")
            self.logger.info(f"📊 Переведенное аудио: {audio_duration:.2f}s")
            
            duration_diff = abs(audio_duration - video_duration)
            
            if duration_diff < 2.0:  # Различие меньше 2 секунд
                self.logger.info("✅ Длительности близки, адаптация не требуется")
                Path(temp_video_path).rename(output_path)
                return True
            
            # Применяем адаптивную корректировку
            self.logger.info(f"🎛️ Применяем адаптивную корректировку (различие: {duration_diff:.1f}s)")
            
            # Используем сегменты для точной синхронизации если есть speaker data
            speaker_segments = [s for s in segments if 'speaker' in s]
            
            success = self.video_adjuster.adjust_video_for_audio(
                video_path, 
                final_audio_path, 
                output_path,
                segments=speaker_segments if speaker_segments else None
            )
            
            # Очистка временного файла
            try:
                Path(temp_video_path).unlink()
            except:
                pass
            
            if success:
                self.logger.info("✅ Адаптивное видео создано успешно")
                return True
            else:
                self.logger.error("❌ Ошибка создания адаптивного видео, используем базовую версию")
                # Fallback к обычному видео
                if Path(temp_video_path).exists():
                    Path(temp_video_path).rename(output_path)
                    return True
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка создания адаптивного видео: {e}")
            return False
    
    def _create_block_synchronized_video(self, video_path: str, segments: List[dict], output_path: str) -> bool:
        """
        Создает финальное видео используя блочную синхронизацию
        
        Args:
            video_path: путь к исходному видео
            segments: обработанные сегменты с переведенным аудио
            output_path: путь для сохранения результата
            
        Returns:
            bool: успех операции
        """
        try:
            self.logger.info("🎬 Создание видео с блочной синхронизацией")
            
            # Создаем временную директорию для блоков
            from tempfile import mkdtemp
            blocks_dir = mkdtemp(prefix="video_blocks_")
            self.logger.info(f"📁 Временная директория блоков: {blocks_dir}")
            
            # Создаем синхронизированные блоки
            video_blocks = self.video_processor.create_synchronized_video_blocks(
                video_path, segments, blocks_dir
            )
            
            if not video_blocks:
                self.logger.error("❌ Не удалось создать видео блоки")
                return False
            
            self.logger.info(f"✅ Создано {len(video_blocks)} синхронизированных блоков")
            
            # Объединяем блоки в финальное видео
            success = self.video_processor.combine_video_blocks(video_blocks, output_path)
            
            if success:
                self.logger.info("✅ Блочная синхронизация завершена успешно")
                
                # Показываем статистику
                import moviepy.editor as mp
                result_video = mp.VideoFileClip(output_path)
                
                total_original_duration = sum(s.get('duration', 0) for s in segments)
                total_translated_duration = sum(self._get_audio_duration(s.get('translated_audio_path', '')) for s in segments)
                
                self.logger.info(f"📊 Статистика синхронизации:")
                self.logger.info(f"   Оригинальная длительность: {total_original_duration:.2f}s")
                self.logger.info(f"   Переведенная длительность: {total_translated_duration:.2f}s")
                self.logger.info(f"   Финальное видео: {result_video.duration:.2f}s")
                self.logger.info(f"   Точность синхронизации: {abs(result_video.duration - total_translated_duration):.2f}s")
                
                result_video.close()
            else:
                self.logger.error("❌ Ошибка объединения блоков")
            
            # Очистка временных блоков
            try:
                import shutil
                shutil.rmtree(blocks_dir)
                self.logger.debug(f"🧹 Удалена временная директория: {blocks_dir}")
            except Exception as cleanup_error:
                self.logger.warning(f"⚠️ Не удалось удалить временные блоки: {cleanup_error}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"❌ Критическая ошибка блочной синхронизации: {e}")
            import traceback
            self.logger.error(f"Трассировка:\n{traceback.format_exc()}")
            return False
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """Получает длительность аудио файла"""
        try:
            if not audio_path or not Path(audio_path).exists():
                return 0.0
            
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except Exception:
            return 0.0
    
    def _find_combined_audio_path(self) -> Optional[str]:
        """Ищет путь к объединенному аудио файлу"""
        # Проверяем временные файлы в src/temp
        temp_dir = Path(self.config.TEMP_FOLDER)
        for audio_file in temp_dir.glob("final_audio_*.wav"):
            return str(audio_file)
        
        # Проверяем корневую директорию проекта (фоллбэк)
        project_root = Path(self.config.PROJECT_ROOT)
        for audio_file in project_root.glob("final_audio_*.wav"):
            return str(audio_file)
        
        return None

    def _cleanup_translation_files(self, audio_path: str, segments: List[Dict], translated_segments: List[Dict]):
        """Очистка всех временных файлов после перевода"""
        files_to_cleanup = []

        # Основной аудио файл
        if audio_path:
            files_to_cleanup.append(audio_path)

        # Файлы сегментов
        for segment in segments:
            if segment.get('path'):
                files_to_cleanup.append(segment['path'])

        # Переведенные аудио файлы
        for segment in translated_segments:
            if segment.get('translated_audio_path'):
                files_to_cleanup.append(segment['translated_audio_path'])

        # Очистка через AudioProcessor
        segment_dicts = [{'path': path} for path in files_to_cleanup if path]
        self.audio_processor.cleanup_temp_segments(segment_dicts)

    def get_system_status(self) -> Dict:
        """Получение подробного статуса системы"""
        return {
            'translator': get_translator_status(),
            'speech_recognition_engines': self.speech_recognizer.test_recognition_engines(),
            'tts_engines': self.speech_synthesizer.test_tts_engines(),
            'available_voices': self.speech_synthesizer.get_available_voices(),
            'config': {
                'max_file_size_mb': self.config.MAX_FILE_SIZE_MB,
                'max_duration_minutes': self.config.MAX_DURATION_MINUTES,
                'allowed_extensions': list(self.config.ALLOWED_EXTENSIONS),
                'audio_sample_rate': self.config.AUDIO_SAMPLE_RATE,
                'video_codec': self.config.VIDEO_CODEC,
                'audio_codec': self.config.AUDIO_CODEC
            }
        }

    def validate_video_file(self, file_path: str) -> Dict[str, any]:
        """Валидация видео файла (делегирование к VideoProcessor)"""
        return self.video_processor.validate_video_file(file_path)

    def get_processing_estimate(self, video_path: str) -> Dict[str, float]:
        """
        Оценка времени обработки видео

        Args:
            video_path: путь к видео файлу

        Returns:
            dict: оценки времени для каждого этапа
        """
        try:
            video_info = self.video_processor.get_video_info(video_path)
            if not video_info:
                return {}

            duration = video_info['duration']

            # Примерные коэффициенты времени обработки
            estimates = {
                'audio_extraction': duration * 0.1,  # 10% от длительности видео
                'segmentation': duration * 0.05,  # 5% от длительности
                'speech_recognition': duration * 0.5,  # 50% (зависит от API)
                'translation': duration * 0.1,  # 10% (быстрый перевод)
                'speech_synthesis': duration * 0.3,  # 30% (зависит от TTS)
                'video_creation': duration * 0.2,  # 20% от длительности
            }

            estimates['total'] = sum(estimates.values())
            estimates['video_duration'] = duration

            return estimates

        except Exception as e:
            self.logger.error(f"Ошибка оценки времени обработки: {e}")
            return {}

    def get_translator_status(self) -> Dict:
        """Получение статуса переводчика"""
        return get_translator_status()

    def create_translation_report(self, segments: List[Dict]) -> Dict:
        """
        Создание отчета о переводе

        Args:
            segments: обработанные сегменты

        Returns:
            dict: детальный отчет о переводе
        """
        report = {
            'total_segments': len(segments),
            'successful_segments': 0,
            'failed_segments': 0,
            'empty_segments': 0,
            'total_text_length': 0,
            'total_translated_length': 0,
            'processing_times': [],
            'errors': []
        }

        for segment in segments:
            status = segment.get('status', 'unknown')

            if status == 'success':
                report['successful_segments'] += 1
            elif status == 'no_speech':
                report['empty_segments'] += 1
            else:
                report['failed_segments'] += 1
                if segment.get('error'):
                    report['errors'].append(segment['error'])

            # Статистика текста
            original_text = segment.get('original_text', '')
            translated_text = segment.get('translated_text', '')

            report['total_text_length'] += len(original_text)
            report['total_translated_length'] += len(translated_text)

            # Время обработки
            processing_time = segment.get('processing_time', 0)
            if processing_time > 0:
                report['processing_times'].append(processing_time)

        # Расчет статистики
        if report['processing_times']:
            report['average_processing_time'] = sum(report['processing_times']) / len(report['processing_times'])
            report['total_processing_time'] = sum(report['processing_times'])
        else:
            report['average_processing_time'] = 0
            report['total_processing_time'] = 0

        report['success_rate'] = (report['successful_segments'] / report['total_segments'] * 100) if report[
                                                                                                         'total_segments'] > 0 else 0

        return report

    def _embed_subtitles_in_video(self, video_path: str, saved_files: List[Tuple[str, str]], target_language: str = 'ru') -> bool:
        """
        Встраивает субтитры в видео с помощью FFmpeg
        
        Args:
            video_path: путь к видео файлу
            saved_files: список сохраненных файлов (тип, путь)
            
        Returns:
            bool: успех встраивания
        """
        try:
            self.logger.info("🎬 Встраивание субтитров в видео...")
            
            # Находим файлы с субтитрами
            subtitle_files = {}
            for file_type, file_path in saved_files:
                if 'subtitles' in file_type.lower():
                    # Если тип просто 'subtitles', ищем все созданные .srt файлы
                    if file_type.lower() == 'subtitles':
                        # Ищем все созданные SRT файлы по паттерну
                        srt_path = Path(file_path)
                        output_dir = srt_path.parent
                        base_name = srt_path.stem.split('_subtitles_')[0] if '_subtitles_' in srt_path.stem else srt_path.stem
                        
                        # Ищем файлы по паттерну
                        for srt_type in ['original', 'translated', 'dual']:
                            for srt_file in output_dir.glob(f"{base_name}*subtitles_{srt_type}*.srt"):
                                subtitle_files[srt_type] = str(srt_file)
                    else:
                        # Новая логика с типами subtitles_original, subtitles_translated, etc
                        if 'original' in file_type.lower():
                            subtitle_files['original'] = file_path
                        elif 'translated' in file_type.lower():
                            subtitle_files['translated'] = file_path
                        elif 'dual' in file_type.lower():
                            subtitle_files['dual'] = file_path
            
            if not subtitle_files:
                self.logger.warning("❌ Не найдены файлы субтитров для встраивания")
                return True  # Не критическая ошибка
            
            # Создаем временное видео с субтитрами
            temp_video_path = video_path.replace('.mp4', '_with_subtitles_temp.mp4')
            
            # Используем переведенные субтитры по приоритету
            subtitle_to_embed = None
            for priority in ['translated', 'dual', 'original']:
                if priority in subtitle_files:
                    subtitle_to_embed = subtitle_files[priority]
                    break
            
            if not subtitle_to_embed:
                self.logger.warning("❌ Не найдены подходящие субтитры для встраивания")
                return True
                
            self.logger.info(f"📝 Встраиваем субтитры: {Path(subtitle_to_embed).name}")
            
            # FFmpeg команда для встраивания субтитров
            import subprocess
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,          # Исходное видео
                '-i', subtitle_to_embed,   # Файл субтитров
                '-c:v', 'copy',            # Копируем видео без перекодирования
                '-c:a', 'copy',            # Копируем аудио без перекодирования
                '-c:s', 'mov_text',        # Кодек субтитров для MP4
                '-metadata:s:s:0', f'language={self._get_subtitle_language_code(target_language)}',  # Язык субтитров
                '-metadata:s:s:0', f'title={self._get_subtitle_title(target_language)}', # Название дорожки субтитров
                temp_video_path
            ]
            
            self.logger.info("🔧 Запуск FFmpeg для встраивания субтитров...")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                # Заменяем оригинальное видео на видео с субтитрами
                import shutil
                shutil.move(temp_video_path, video_path)
                self.logger.info("✅ Субтитры успешно встроены в видео")
                
                # Проверяем результат
                try:
                    import moviepy.editor as mp
                    with mp.VideoFileClip(video_path) as test_video:
                        self.logger.info(f"  📊 Финальное видео: {test_video.duration:.2f}s")
                        if hasattr(test_video, 'audio') and test_video.audio:
                            self.logger.info(f"  🔊 Содержит аудио: Да")
                        else:
                            self.logger.info(f"  🔊 Содержит аудио: Нет")
                except Exception as e:
                    self.logger.warning(f"Ошибка проверки финального видео: {e}")
                
                return True
            else:
                self.logger.error(f"❌ Ошибка встраивания субтитров:")
                self.logger.error(f"  FFmpeg stderr: {result.stderr}")
                
                # Удаляем временный файл если он создался
                if Path(temp_video_path).exists():
                    Path(temp_video_path).unlink()
                
                return True  # Не критическая ошибка - видео все равно есть
                
        except Exception as e:
            self.logger.error(f"❌ Критическая ошибка встраивания субтитров: {e}")
            # Очистка временного файла
            temp_video_path = video_path.replace('.mp4', '_with_subtitles_temp.mp4')
            if Path(temp_video_path).exists():
                Path(temp_video_path).unlink()
            
            return True  # Не критическая ошибка


# Функции для обратной совместимости с существующим кодом
def extract_audio(video_path: str) -> Optional[str]:
    """Обратная совместимость: извлечение аудио"""
    translator = VideoTranslator()
    return translator.video_processor.extract_audio(video_path)


def segment_audio(audio_path: str) -> List[Dict]:
    """Обратная совместимость: сегментация аудио"""
    translator = VideoTranslator()
    return translator.audio_processor.segment_audio(audio_path)


def transcribe_segment(segment_path: str, language: str = 'en-US') -> str:
    """Обратная совместимость: распознавание речи"""
    translator = VideoTranslator()
    return translator.speech_recognizer.transcribe_audio(segment_path, language)



def synthesize_speech(text: str, lang: str = 'ru', slow: bool = False) -> Optional[str]:
    """Обратная совместимость: синтез речи"""
    translator = VideoTranslator()
    return translator.speech_synthesizer.synthesize_speech(text, lang)


def translate_video(input_video: str, output_video: str, source_language: str = 'auto',
                   target_language: str = 'ru', custom_output_dir: str = None,
                   use_gpu: bool = True, preserve_original_audio: bool = False,
                   generate_subtitles: bool = True, whisper_model: str = 'base',
                   tts_engine: str = 'auto') -> bool:
    """
    Функция-обертка для обратной совместимости с фреймворком

    Args:
        input_video: Путь к входному видео
        output_video: Путь к выходному видео
        source_language: Исходный язык
        target_language: Целевой язык
        custom_output_dir: Папка для сохранения (не используется, совместимость)
        use_gpu: Использовать GPU (передается в настройки)
        preserve_original_audio: Сохранять оригинальное аудио
        generate_subtitles: Генерировать субтитры
        whisper_model: Модель Whisper
        tts_engine: TTS движок

    Returns:
        bool: True если успешно, False если ошибка
    """
    try:
        translator = VideoTranslator()

        # Определяем формат вывода на основе параметра generate_subtitles
        output_format = 'TRANSLATION_WITH_SUBTITLES' if generate_subtitles else 'TRANSLATION_ONLY'

        # Вызываем метод класса с нужными параметрами
        result = translator.translate_video(
            video_path=input_video,
            output_path=output_video,
            source_language=source_language,
            target_language=target_language,
            whisper_model=whisper_model,
            speech_engine='whisper',  # Принудительно используем whisper
            output_format=output_format,  # Включаем субтитры
            save_texts=True  # Сохраняем текстовые файлы
        )

        return result

    except Exception as e:
        print(f"Error in translate_video wrapper: {e}")
        return False


if __name__ == "__main__":
    # Тестирование модуля
    print("=== Тестирование VideoTranslator (модульная версия) ===")

    translator = VideoTranslator()
    print("VideoTranslator инициализирован")

    # Статус системы
    status = translator.get_system_status()
    print(f"  Переводчик: {status['translator']['type']}")
    print(f"  SR движки: {[k for k, v in status['speech_recognition_engines'].items() if v]}")
    print(f"  TTS движки: {[k for k, v in status['tts_engines'].items() if v]}")

    # Тест с реальным файлом
    test_file = "test.mp4"
    if Path(test_file).exists():
        validation = translator.validate_video_file(test_file)
        print(f"Валидация {test_file}: {validation}")

        if validation['valid']:
            estimates = translator.get_processing_estimate(test_file)
            print(f"Оценка времени обработки: {estimates.get('total', 0):.1f}s")
    else:
        print(f"Тестовый файл {test_file} не найден")

    print("Тестирование завершено")
    print(f"Статус системы:")
    print(f"  Переводчик: {status['translator']['type']}")
    print(f"  SR движки: {[k for k, v in status['speech_recognition_engines'].items() if v]}")
    print(f"  TTS движки: {[k for k, v in status['tts_engines'].items() if v]}")

    # Тест с реальным файлом
    test_file = "test.mp4"
    if Path(test_file).exists():
        validation = translator.validate_video_file(test_file)
        print(f"Валидация {test_file}: {validation}")

        if validation['valid']:
            estimates = translator.get_processing_estimate(test_file)
            print(f"Оценка времени обработки: {estimates.get('total', 0):.1f}s")
    else:
        print(f"Тестовый файл {test_file} не найден")

print("Тестирование завершено")