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
from typing import Optional, Dict, List, Callable
import json
from datetime import datetime
from pathlib import Path

# Core модули
from core import VideoProcessor, AudioProcessor, SpeechRecognizer, SpeechSynthesizer
from translator_compat import translate_text, get_translator_status
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

        # Создание рабочих директорий
        self.config.create_directories()

        self.logger.info("VideoTranslator инициализирован с модульной архитектурой")
        self._log_component_status()
    
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
                    raise ValueError(f"Движок {engine} не смог распознать аудио в файле {audio_path}")
                else:
                    self.logger.warning(f"⚠️ Движок {engine} не вернул результат")
                    return ""
                
        except Exception as e:
            if is_manual_selection:
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
                logging.FileHandler(self.config.LOG_FILE),
                logging.StreamHandler()
            ]
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

    def save_translation_results(self, video_path: str, segments: List[Dict], output_dir: str = None) -> str:
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
                'source_language': self.config.SOURCE_LANGUAGE,
                'target_language': self.config.TARGET_LANGUAGE,
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
                text_content.append(f"EN: {original_text}")
                text_content.append(f"RU: {translated_text}")
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

    def save_complete_transcript(self, video_path: str, segments: List[Dict], output_dir: str = None) -> str:
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

                if original_text:
                    text_content.append(f"EN: {original_text}")
                else:
                    text_content.append(f"EN: [речь не распознана]")

                if translated_text:
                    text_content.append(f"RU: {translated_text}")
                else:
                    text_content.append(f"RU: [нет перевода]")

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

    def save_subtitles_srt(self, video_path: str, segments: List[Dict], output_dir: str = None, subtitle_type: str = "both") -> str:
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
                self._create_srt_file(segments, srt_file_original, "original")
                srt_files.append(str(srt_file_original))
                
            if subtitle_type in ["translated", "both"]:
                srt_file_translated = Path(output_dir) / f"{video_name}_subtitles_translated_{timestamp}.srt"
                self._create_srt_file(segments, srt_file_translated, "translated")
                srt_files.append(str(srt_file_translated))
            
            if subtitle_type == "both":
                srt_file_dual = Path(output_dir) / f"{video_name}_subtitles_dual_{timestamp}.srt"
                self._create_srt_file(segments, srt_file_dual, "dual")
                srt_files.append(str(srt_file_dual))
            
            self.logger.info(f"SRT субтитры сохранены: {', '.join([Path(f).name for f in srt_files])}")
            return srt_files[0] if srt_files else ""
            
        except Exception as e:
            self.logger.error(f"Ошибка создания SRT субтитров: {e}")
            return ""
    
    def _create_srt_file(self, segments: List[Dict], output_file: Path, subtitle_type: str):
        """Создание конкретного SRT файла"""
        def format_time(seconds: float) -> str:
            """Форматирование времени для SRT"""
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millisecs = int((seconds % 1) * 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
        
        srt_content = []
        subtitle_index = 1
        
        for segment in segments:
            start_time = segment.get('start_time', 0)
            end_time = segment.get('end_time', start_time + 1)
            
            original_text = segment.get('original_text', segment.get('text', ''))
            translated_text = segment.get('translated_text', '')
            
            # Определяем текст субтитров
            if subtitle_type == "original":
                subtitle_text = original_text or '[речь не распознана]'
            elif subtitle_type == "translated":
                subtitle_text = translated_text or '[нет перевода]'
            elif subtitle_type == "dual":
                lines = []
                if original_text:
                    lines.append(f"EN: {original_text}")
                if translated_text:
                    lines.append(f"RU: {translated_text}")
                subtitle_text = '\n'.join(lines) if lines else '[нет текста]'
            
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
                        save_texts: bool = True, speech_engine: str = 'auto', 
                        output_format: str = 'TRANSLATION_ONLY') -> bool:
        """
        Основная функция перевода видео с сохранением текстов

        Args:
            video_path: путь к исходному видео
            output_path: путь для сохранения результата
            progress_callback: функция для отслеживания прогресса
            save_texts: сохранять ли текстовые результаты
            speech_engine: предпочтительный движок распознавания ('auto', 'whisper', 'google', 'sphinx')
            output_format: формат вывода ('TRANSLATION_ONLY', 'SUBTITLES_ONLY', 'TRANSLATION_WITH_SUBTITLES')

        Returns:
            bool: True при успехе, False при ошибке
        """
        start_time = time.time()

        try:
            self.logger.info(f"Начало перевода видео: {video_path} -> {output_path}")
            self.logger.info(f"📋 Настройки: движок={speech_engine}, формат={output_format}")
            
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

            # ВРЕМЕННО: используем только старый надёжный метод сегментации
            # TODO: вернуть Whisper timestamps когда исправим зависание
            self.logger.info("🔄 Используем стабильную сегментацию по паузам")
            segments = self.audio_processor.segment_audio(audio_path)
            
            if not segments:
                self.logger.error("Ошибка сегментации аудио")
                if progress_callback:
                    progress_callback("Ошибка сегментации аудио", 0)
                return False
                
            self.logger.info(f"✅ Создано {len(segments)} сегментов по паузам")

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

                    # 3a. Распознавание речи (или использование уже распознанного из Whisper)
                    if segment.get('source') == 'whisper_timestamps':
                        # Для Whisper сегментов текст уже распознан
                        original_text = segment.get('original_text', '')
                        self.logger.debug(f"Сегмент {i + 1} из Whisper ({len(original_text)} символов): {original_text[:100]}...")
                    else:
                        # Обычное распознавание для сегментов по паузам с выбранным движком
                        is_manual_selection = speech_engine != 'auto'
                        original_text = self._transcribe_with_engine(segment['path'], selected_engine, is_manual_selection)
                        self.logger.debug(f"Сегмент {i + 1} распознан через {selected_engine} ({len(original_text)} символов): {original_text[:100]}...")

                    if not original_text:
                        self.logger.warning(f"Сегмент {i + 1}: речь не распознана")
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
                    translated_text = translate_text(
                        original_text,
                        self.config.SOURCE_LANGUAGE,
                        self.config.TARGET_LANGUAGE
                    )

                    if not translated_text:
                        translated_text = original_text  # Fallback на оригинальный текст

                    self.logger.debug(
                        f"Сегмент {i + 1} переведен ({len(translated_text)} символов): {translated_text[:100]}...")

                    # 3c. Синтез речи
                    tts_path = self.speech_synthesizer.synthesize_speech(
                        translated_text,
                        self.config.TTS_LANGUAGE
                    )

                    if tts_path:
                        # 3d. Подгонка длительности
                        adjusted_tts_path = self.audio_processor.adjust_audio_duration(
                            tts_path,
                            segment['duration']
                        )
                        tts_path = adjusted_tts_path

                    processing_time = time.time() - segment_start_time
                    successful_segments += 1

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
                    translation_file = self.save_translation_results(video_path, translated_segments)
                    if translation_file:
                        saved_files.append(('translation', translation_file))

                    # Сохранение полного транскрипта
                    transcript_file = self.save_complete_transcript(video_path, translated_segments)
                    if transcript_file:
                        saved_files.append(('transcript', transcript_file))
                    
                    # Создание SRT субтитров
                    srt_file = self.save_subtitles_srt(video_path, translated_segments, subtitle_type="both")
                    if srt_file:
                        saved_files.append(('subtitles', srt_file))

                except Exception as e:
                    self.logger.error(f"Ошибка сохранения текстовых файлов: {e}")

            if progress_callback:
                progress_callback("Создание финального видео", 85)

            # 5. Создание финального видео
            success = self.video_processor.create_final_video(video_path, translated_segments, output_path)

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