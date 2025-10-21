#!/usr/bin/env python3
"""
SpeechSynthesizer: Модуль синтеза речи
Поддерживает Google TTS, ElevenLabs и локальные TTS движки
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List

from gtts import gTTS

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import config
from core.tts_manual_selector import tts_manual_selector


class SpeechSynthesizer:
    """Класс для синтеза речи из текста"""
    
    def __init__(self):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Настройки по умолчанию
        self.default_language = self.config.TTS_LANGUAGE
        self.default_voice = self.config.TTS_VOICE
        
        # Карта голосов по языкам: language_code -> voice_info
        self.language_voices = {
            'ru': {'voice': 'Milena', 'fallback': 'Milena'},
            'uk': {'voice': 'Lesya', 'fallback': 'Milena', 'quality_issues': True},  # Украинский голос с известными проблемами качества
            'en': {'voice': 'Samantha', 'fallback': 'Alex'},
            'de': {'voice': 'Anna', 'fallback': 'Markus'},
            'fr': {'voice': 'Amelie', 'fallback': 'Thomas'},
            'es': {'voice': 'Monica', 'fallback': 'Jorge'},
            'it': {'voice': 'Alice', 'fallback': 'Luca'},
            'pt': {'voice': 'Joana', 'fallback': 'Luciana'},
            'zh': {'voice': 'Ting-Ting', 'fallback': 'Sin-ji'},
            'ja': {'voice': 'Kyoko', 'fallback': 'Otoya'},
            'ko': {'voice': 'Yuna', 'fallback': 'Yuna'},
            'ar': {'voice': 'Maged', 'fallback': 'Maged'},
            'tr': {'voice': 'Yelda', 'fallback': 'Yelda'},
            'pl': {'voice': 'Zosia', 'fallback': 'Krzysztof'},
            'nl': {'voice': 'Ellen', 'fallback': 'Xander'},
            'sv': {'voice': 'Klara', 'fallback': 'Oskar'},
            'no': {'voice': 'Nora', 'fallback': 'Henrik'},
            'da': {'voice': 'Sara', 'fallback': 'Magnus'},
            'fi': {'voice': 'Satu', 'fallback': 'Onni'},
            # Добавляем fallback для неподдерживаемых языков
            'default': {'voice': 'Samantha', 'fallback': 'Alex'}
        }
        
        # Старая карта для обратной совместимости
        self.voice_map = {
            'ru-male-1': self._get_voice_for_language('ru'),
            'ru-male-2': self._get_voice_for_language('ru'),
            'ru-male-3': self._get_voice_for_language('ru'),
            'ru-female-1': self._get_voice_for_language('ru'),
            'ru-female-2': self._get_voice_for_language('ru'),
            'ru-female-3': self._get_voice_for_language('ru'),
        }
        
        # Стандартные параметры для всех голосов (без изменения тембра)
        self.voice_params = {
            'ru-male-1': {'rate': 190, 'pitch_adj': 'normal'},
            'ru-male-2': {'rate': 190, 'pitch_adj': 'normal'},
            'ru-male-3': {'rate': 190, 'pitch_adj': 'normal'},
            'ru-female-1': {'rate': 190, 'pitch_adj': 'normal'},
            'ru-female-2': {'rate': 190, 'pitch_adj': 'normal'},
            'ru-female-3': {'rate': 190, 'pitch_adj': 'normal'},
        }
        
        # Языково-специфичные параметры голосов для улучшения качества
        self.language_voice_params = {
            'ru': {'rate': 190, 'pitch_adj': 'normal'},  # Русский
            'uk': {'rate': 170, 'pitch_adj': 'normal'},  # Украинский
            'en': {'rate': 200, 'pitch_adj': 'normal'},  # Английский
            'de': {'rate': 180, 'pitch_adj': 'normal'},  # Немецкий
            'fr': {'rate': 180, 'pitch_adj': 'normal'},  # Французский
            'es': {'rate': 190, 'pitch_adj': 'normal'},  # Испанский
            'it': {'rate': 185, 'pitch_adj': 'normal'},  # Итальянский
            'pt': {'rate': 190, 'pitch_adj': 'normal'},  # Португальский
            'pl': {'rate': 175, 'pitch_adj': 'normal'},  # Польский
            'nl': {'rate': 185, 'pitch_adj': 'normal'},  # Голландский
            'sv': {'rate': 180, 'pitch_adj': 'normal'},  # Шведский
            'no': {'rate': 180, 'pitch_adj': 'normal'},  # Норвежский
            'da': {'rate': 185, 'pitch_adj': 'normal'},  # Датский
            'fi': {'rate': 160, 'pitch_adj': 'normal'},  # Финский - медленнее
            'ar': {'rate': 160, 'pitch_adj': 'normal'},  # Арабский - медленнее
            'tr': {'rate': 175, 'pitch_adj': 'normal'},  # Турецкий
            'zh': {'rate': 220, 'pitch_adj': 'normal'},  # Китайский - быстрее
            'ja': {'rate': 180, 'pitch_adj': 'normal'},  # Японский
            'ko': {'rate': 190, 'pitch_adj': 'normal'},  # Корейский
            'hi': {'rate': 170, 'pitch_adj': 'normal'},  # Хинди
            'th': {'rate': 165, 'pitch_adj': 'normal'},  # Тайский
            'vi': {'rate': 180, 'pitch_adj': 'normal'},  # Вьетнамский
            'hu': {'rate': 170, 'pitch_adj': 'normal'},  # Венгерский
            'cs': {'rate': 175, 'pitch_adj': 'normal'},  # Чешский
            'sk': {'rate': 175, 'pitch_adj': 'normal'},  # Словацкий
            'ro': {'rate': 180, 'pitch_adj': 'normal'},  # Румынский
            'bg': {'rate': 175, 'pitch_adj': 'normal'},  # Болгарский
            'hr': {'rate': 175, 'pitch_adj': 'normal'},  # Хорватский
            'sl': {'rate': 175, 'pitch_adj': 'normal'},  # Словенский
            'lv': {'rate': 170, 'pitch_adj': 'normal'},  # Латышский
            'lt': {'rate': 170, 'pitch_adj': 'normal'},  # Литовский
            'et': {'rate': 165, 'pitch_adj': 'normal'},  # Эстонский
            'id': {'rate': 185, 'pitch_adj': 'normal'},  # Индонезийский
            'ms': {'rate': 185, 'pitch_adj': 'normal'},  # Малайский
            'el': {'rate': 180, 'pitch_adj': 'normal'},  # Греческий
            'he': {'rate': 175, 'pitch_adj': 'normal'},  # Иврит
        }
        
        self.logger.debug("SpeechSynthesizer инициализирован")
    
    def _get_voice_for_language(self, language_code):
        """Получить подходящий голос для языка"""
        lang_info = self.language_voices.get(language_code.lower(), self.language_voices['default'])
        return lang_info['voice']
    
    def _get_fallback_voice(self, language_code):
        """Получить fallback голос для языка"""
        lang_info = self.language_voices.get(language_code.lower(), self.language_voices['default'])
        return lang_info['fallback']
    
    def set_target_language(self, target_language):
        """Установить целевой язык для TTS"""
        self.target_language = target_language.lower()
        voice_info = self.language_voices.get(self.target_language, self.language_voices['default'])
        voice_name = voice_info['voice']
        
        # Предупреждение о проблемах качества
        if voice_info.get('quality_issues'):
            self.logger.warning(f"⚠️ Голос {voice_name} для языка {target_language} имеет известные проблемы качества")
            self.logger.info(f"🔄 Используем замедленную скорость речи для улучшения качества")
        
        self.logger.info(f"🌍 TTS язык установлен: {target_language} -> голос: {voice_name}")

    def synthesize_speech(
            self,
            text: str,
            language: str = None,
            voice: str = None,
            speed: float = 1.0,
            pitch: float = 0.0,
            target_duration: float = None,
            speaker_id: str = None
    ) -> Optional[str]:
        """
        Синтез речи с использованием ручного селектора TTS движков
        """
        if not text or not text.strip():
            self.logger.debug("Пустой текст для синтеза")
            return None

        # Определяем язык
        language = language or getattr(self, 'target_language', self.default_language)
        
        # Используем ручной селектор для выбора движка и голоса
        effective_engine = tts_manual_selector.get_effective_engine_for_language(language)
        effective_voice = voice or tts_manual_selector.get_effective_voice_for_language(language)
        
        self.logger.info(f"🎛️ TTS селектор: язык={language}, движок={effective_engine.value}, голос={effective_voice}")
        
        # Используем новую TTS фабрику для синтеза
        result = tts_manual_selector.tts_factory.synthesize_with_engine(
            text=text,
            language=language,
            engine=effective_engine,
            voice_name=effective_voice,
            target_duration=target_duration,
            speaker_id=speaker_id
        )
        
        if result:
            self.logger.info(f"✅ Синтез успешен через {effective_engine.value}")
            return result
        else:
            self.logger.warning(f"⚠️ Синтез не удался через {effective_engine.value}, пробуем старый способ...")
            
        # Fallback на старый метод, если новый не сработал
        language = language or getattr(self, 'target_language', self.default_language)
        
        # Если голос не указан, автоматически выбираем по языку
        if not voice:
            voice = self._get_voice_for_language(language)
        
        # Если голос указан как старый формат (ru-male-1), используем маппинг
        if voice in self.voice_map:
            voice = self.voice_map[voice]

        try:
            # Для украинского языка сразу используем Google TTS (более надежный)
            if language and language.lower() == 'uk':
                self.logger.info(f"🇺🇦 Украинский текст: используем Google TTS (основной) для '{text[:50]}...'")
                google_result = self._synthesize_with_google_tts_ukrainian(text)
                if google_result:
                    self.logger.info("✅ Использован Google TTS для украинского языка (основной)")
                    return google_result
                else:
                    self.logger.warning("⚠️ Google TTS недоступен, пробуем Lesya как fallback")
            
            # Для всех остальных языков или если Google TTS недоступен для украинского
            macos_voice = self._get_macos_voice(voice, language)
            voice_params = self._get_voice_params(voice, language)
            
            self.logger.info(f"🎤 Синтез речи через {macos_voice} ({voice}): '{text[:50]}...'")

            # Синтез с выбранным голосом и параметрами
            result = self._synthesize_with_say_voice_params(text, language, macos_voice, voice_params)

            if result:
                # Проверяем качество украинского TTS - файл и длительность
                if language and language.lower() == 'uk':
                    from pathlib import Path
                    if Path(result).exists():
                        file_size = Path(result).stat().st_size
                        
                        # Проверяем длительность аудио
                        try:
                            from pydub import AudioSegment
                            audio = AudioSegment.from_wav(result)
                            duration = len(audio) / 1000.0  # в секундах
                            expected_duration = len(text) / 8.0  # примерно 8 символов в секунду для украинского
                            
                            # Проверяем на подозрительные проблемы
                            is_small_file = len(text) > 50 and file_size < 30000
                            is_short_audio = duration < expected_duration * 0.3  # менее 30% ожидаемой длительности
                            is_suspiciously_uniform = self._check_audio_uniformity(audio)  # проверка на монотонные звуки
                            
                            if is_small_file or is_short_audio or is_suspiciously_uniform:
                                reason = []
                                if is_small_file: reason.append("малый размер")
                                if is_short_audio: reason.append("короткая длительность") 
                                if is_suspiciously_uniform: reason.append("подозрительный звук")
                                
                                self.logger.warning(f"⚠️ Проблема с украинским TTS: {', '.join(reason)} (размер={file_size}байт, длительность={duration:.1f}с)")
                                self.logger.info("🔄 Переключаемся на Google TTS для украинского языка...")
                                google_result = self._synthesize_with_google_tts_ukrainian(text)
                                if google_result:
                                    self.logger.info("✅ Использован Google TTS вместо проблемного Lesya")
                                    # Удаляем проблемный файл
                                    try:
                                        Path(result).unlink()
                                    except:
                                        pass
                                    return google_result
                        except Exception as e:
                            self.logger.debug(f"Ошибка проверки украинского аудио: {e}")
                
                self.logger.info(f"✅ Использован macOS 'say' с голосом {macos_voice} (параметры: {voice_params})")
                return result
            else:
                self.logger.error("❌ macOS 'say' команда недоступна")
                
                # Для украинского языка пробуем Google TTS как fallback
                if language and language.lower() == 'uk':
                    self.logger.info("🔄 Пробуем Google TTS для украинского языка...")
                    google_result = self._synthesize_with_google_tts_ukrainian(text)
                    if google_result:
                        self.logger.info("✅ Использован Google TTS для украинского языка")
                        return google_result
                
                return None

        except Exception as e:
            self.logger.error(f"Критическая ошибка синтеза речи: {e}")
            return None
    
    def _synthesize_with_google_tts_ukrainian(self, text: str) -> Optional[str]:
        """Синтез украинского текста через Google TTS как fallback"""
        try:
            from gtts import gTTS
            import io
            
            # Создаем объект gTTS для украинского языка
            tts = gTTS(text=text, lang='uk', slow=False)
            
            # Сохраняем во временный файл
            temp_path = self.config.get_temp_filename("google_tts_ukrainian", ".mp3")
            tts.save(str(temp_path))
            
            if not Path(temp_path).exists():
                self.logger.error("❌ Google TTS не создал файл")
                return None
            
            # Конвертируем MP3 в WAV через pydub
            wav_path = self._convert_mp3_to_wav(temp_path)
            if wav_path:
                # Удаляем временный MP3
                try:
                    Path(temp_path).unlink()
                except:
                    pass
                return wav_path
            
            return None
            
        except ImportError:
            self.logger.error("❌ gTTS не установлен")
            return None
        except Exception as e:
            self.logger.error(f"❌ Ошибка Google TTS для украинского: {e}")
            return None
    
    def _convert_mp3_to_wav(self, mp3_path: str) -> Optional[str]:
        """Конвертация MP3 в WAV через pydub"""
        try:
            from pydub import AudioSegment
            
            wav_path = self.config.get_temp_filename("google_tts_converted", ".wav")
            
            # Загружаем MP3 файл
            audio = AudioSegment.from_mp3(mp3_path)
            
            # Экспортируем как WAV с оптимальными параметрами
            audio.export(str(wav_path), format="wav", parameters=["-acodec", "pcm_s16le", "-ar", "22050", "-ac", "1"])
            
            if Path(wav_path).exists() and Path(wav_path).stat().st_size > 1000:
                self.logger.info(f"✅ MP3 -> WAV конвертация успешна: {wav_path}")
                return str(wav_path)
            else:
                self.logger.error("❌ Конвертация MP3 -> WAV неудачна")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка конвертации MP3 -> WAV: {e}")
            return None
    
    def _check_audio_uniformity(self, audio_segment) -> bool:
        """
        Проверяет аудио на подозрительную монотонность (как звук 'Ба-а-анг')
        
        Args:
            audio_segment: объект AudioSegment
            
        Returns:
            bool: True если аудио подозрительно монотонное
        """
        try:
            # Простая проверка: если аудио слишком тихое или слишком громкое
            loudness = audio_segment.dBFS
            
            # Если звук аномально тихий (меньше -40dB) или слишком громкий (больше -5dB)
            if loudness < -40 or loudness > -5:
                return True
                
            # Проверяем вариацию громкости - речь должна иметь динамику
            # Разбиваем аудио на сегменты и проверяем разброс громкости
            if len(audio_segment) > 1000:  # если больше 1 секунды
                chunk_size = len(audio_segment) // 10  # делим на 10 частей
                loudness_values = []
                
                for i in range(0, len(audio_segment), chunk_size):
                    chunk = audio_segment[i:i+chunk_size]
                    if len(chunk) > 100:  # минимум 100мс
                        loudness_values.append(chunk.dBFS)
                
                if len(loudness_values) >= 3:
                    # Проверяем разброс громкости
                    max_loud = max(loudness_values)
                    min_loud = min(loudness_values)
                    variation = max_loud - min_loud
                    
                    # Если вариация меньше 3dB, это подозрительно монотонно
                    if variation < 3.0:
                        return True
            
            return False
            
        except Exception as e:
            # При ошибке считаем, что аудио нормальное
            return False

    # def synthesize_speech(
    #     self,
    #     text: str,
    #     language: str = None,
    #     voice: str = None,
    #     speed: float = 1.0,
    #     pitch: float = 0.0
    # ) -> Optional[str]:
    #     """
    #     Синтез речи из текста с fallback стратегией
    #
    #     Args:
    #         text: текст для синтеза
    #         language: код языка
    #         voice: голос для синтеза
    #         speed: скорость речи (0.5 - 2.0)
    #         pitch: высота тона (-20.0 - 20.0)
    #
    #     Returns:
    #         str: путь к аудио файлу или None при ошибке
    #     """
    #     if not text or not text.strip():
    #         self.logger.debug("Пустой текст для синтеза")
    #         return None
    #
    #     language = language or self.default_language
    #     voice = voice or self.default_voice
    #
    #     try:
    #         self.logger.debug(f"Синтез речи: '{text[:50]}...' (lang={language}, voice={voice})")
    #
    #         # Попытка синтеза через ElevenLabs (высокое качество)
    #         result = self._synthesize_with_elevenlabs(text, voice, speed)
    #         if result:
    #             self.logger.debug("ElevenLabs TTS успешно")
    #             return result
    #
    #         # Fallback на Google TTS
    #         result = self._synthesize_with_google_tts(text, language, speed < 1.0)
    #         if result:
    #             self.logger.debug("Google TTS успешно")
    #             return result
    #
    #         # Fallback на локальные TTS движки
    #         result = self._synthesize_with_local_tts(text, language, speed, pitch)
    #         if result:
    #             self.logger.debug("Локальный TTS успешно")
    #             return result
    #
    #         self.logger.warning("Все методы синтеза речи неудачны")
    #         return None
    #
    #     except Exception as e:
    #         self.logger.error(f"Ошибка синтеза речи: {e}")
    #         return None
    
    # ElevenLabs API удален - используем только локальные TTS движки
    
    # Google TTS удален - используем только локальные TTS движки
    
    def _synthesize_with_local_tts(
        self, 
        text: str, 
        language: str, 
        speed: float, 
        pitch: float
    ) -> Optional[str]:
        """
        Синтез речи с локальными TTS движками
        
        Args:
            text: текст для синтеза
            language: код языка
            speed: скорость речи
            pitch: высота тона
            
        Returns:
            str: путь к аудио файлу или None при ошибке
        """
        # Попытка использования разных локальных движков
        methods = [
            self._try_pyttsx3,
            self._try_espeak,
            self._try_festival,
        ]
        
        for method in methods:
            try:
                result = method(text, language, speed, pitch)
                if result:
                    return result
            except Exception as e:
                self.logger.debug(f"Локальный TTS метод неудачен: {e}")
                continue
        
        return None

    def _try_pyttsx3(self, text: str, language: str, speed: float, pitch: float) -> Optional[str]:
        """Синтез речи через pyttsx3 с улучшенной поддержкой русского"""
        try:
            import pyttsx3

            engine = pyttsx3.init()

            # Получаем все доступные голоса
            voices = engine.getProperty('voices')
            self.logger.debug(f"Найдено голосов: {len(voices)}")

            # Поиск русского голоса
            russian_voice = None
            for voice in voices:
                self.logger.debug(f"Голос: {voice.name}, ID: {voice.id}")
                if language.startswith('ru') and any(marker in voice.id.lower() for marker in ['ru', 'russian']):
                    russian_voice = voice.id
                    break

            # Устанавливаем голос если найден
            if russian_voice:
                engine.setProperty('voice', russian_voice)
                self.logger.debug(f"Установлен русский голос: {russian_voice}")
            else:
                self.logger.warning("Русский голос не найден, используем по умолчанию")

            # Настройка параметров
            rate = max(100, min(300, int(200 * speed)))  # 100-300 слов в минуту
            engine.setProperty('rate', rate)
            engine.setProperty('volume', 1.0)

            # Генерация уникального имени файла
            output_path = self.config.get_temp_filename("pyttsx3_tts", ".wav")

            # Синтез и сохранение
            engine.save_to_file(text, str(output_path))
            engine.runAndWait()

            # Проверяем, что файл создался
            if Path(output_path).exists() and Path(output_path).stat().st_size > 100:
                self.logger.info(f"pyttsx3 создал файл: {output_path}")
                
                # ИСПРАВЛЕНИЕ: pyttsx3 на macOS создает AIFF файлы с расширением .wav
                # Конвертируем в настоящий WAV для совместимости с pydub
                try:
                    import subprocess
                    fixed_path = self.config.get_temp_filename("pyttsx3_fixed", ".wav")
                    
                    cmd = [
                        'ffmpeg', '-f', 'aiff', '-i', str(output_path),
                        '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '1',
                        '-af', 'volume=20dB', '-y', str(fixed_path)
                    ]
                    
                    self.logger.info(f"Выполняем FFmpeg команду: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0 and Path(fixed_path).stat().st_size > 1000:
                        self.logger.info(f"pyttsx3 файл исправлен: {fixed_path}")
                        # Удаляем оригинальный AIFF файл только если конвертация успешна
                        try:
                            Path(output_path).unlink()
                        except:
                            pass
                        return str(fixed_path)
                    else:
                        self.logger.error(f"FFmpeg конвертация неудачна: {result.stderr}")
                        self.logger.error(f"Размер выходного файла: {Path(fixed_path).stat().st_size if Path(fixed_path).exists() else 'не существует'}")
                        # Попробуем альтернативную конвертацию
                        return self._alternative_conversion(output_path)
                        
                except Exception as e:
                    self.logger.warning(f"Ошибка конвертации pyttsx3 файла: {e}")
                    return str(output_path)  # Возвращаем как есть
            else:
                self.logger.warning("pyttsx3 не создал аудио файл")
                return None

        except ImportError:
            self.logger.error("pyttsx3 не установлен")
            return None
        except Exception as e:
            self.logger.error(f"pyttsx3 ошибка: {e}")
            return None
    
    def _alternative_conversion(self, aiff_path: str) -> str:
        """Альтернативная конвертация AIFF файлов"""
        try:
            import subprocess
            alt_path = self.config.get_temp_filename("pyttsx3_alt", ".wav")
            
            # Пытаемся различные подходы конвертации
            conversion_attempts = [
                # Попытка 1: принудительная конвертация с нормализацией
                [
                    'ffmpeg', '-f', 'aiff', '-i', str(aiff_path),
                    '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '1',
                    '-filter:a', 'loudnorm', '-y', str(alt_path)
                ],
                # Попытка 2: без фильтров, только базовая конвертация
                [
                    'ffmpeg', '-i', str(aiff_path),
                    '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '1',
                    '-y', str(alt_path)
                ],
                # Попытка 3: попробуем через sox если доступен
                [
                    'sox', str(aiff_path), str(alt_path), 'gain', '20'
                ]
            ]
            
            for i, cmd in enumerate(conversion_attempts):
                try:
                    self.logger.info(f"Попытка {i+1} альтернативной конвертации: {' '.join(cmd[:3])}")
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0 and Path(alt_path).exists() and Path(alt_path).stat().st_size > 1000:
                        self.logger.info(f"Альтернативная конвертация успешна: {alt_path}")
                        return str(alt_path)
                    else:
                        self.logger.warning(f"Попытка {i+1} неудачна: {result.stderr}")
                        
                except FileNotFoundError:
                    self.logger.debug(f"Команда {cmd[0]} не найдена")
                    continue
                except Exception as e:
                    self.logger.debug(f"Попытка {i+1} ошибка: {e}")
                    continue
            
            # Если все попытки неудачны, возвращаем оригинал
            self.logger.warning("Все попытки конвертации неудачны, возвращаем оригинальный файл")
            return str(aiff_path)
            
        except Exception as e:
            self.logger.error(f"Ошибка альтернативной конвертации: {e}")
            return str(aiff_path)

    def _synthesize_with_espeak_direct(self, text: str, language: str, speed: float) -> Optional[str]:
        """Прямой синтез через eSpeak с созданием совместимых WAV файлов"""
        try:
            import subprocess
            
            # Проверка наличия eSpeak
            result = subprocess.run(['which', 'espeak'], capture_output=True)
            if result.returncode != 0:
                self.logger.debug("eSpeak не найден")
                return None
            
            output_path = self.config.get_temp_filename("espeak_tts", ".wav")
            
            # Настройка параметров для русского языка
            lang_code = 'ru' if language.startswith('ru') else 'en'
            speed_wpm = int(150 * speed) if speed else 150
            
            # eSpeak команда для создания WAV файла
            cmd = [
                'espeak', '-v', lang_code, '-s', str(speed_wpm),
                '-w', str(output_path), text
            ]
            
            self.logger.info(f"Выполняем eSpeak: {' '.join(cmd[:5])}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and Path(output_path).exists() and Path(output_path).stat().st_size > 100:
                self.logger.info(f"eSpeak создал файл: {output_path}")
                return str(output_path)
            else:
                self.logger.warning(f"eSpeak неудача: {result.stderr}")
                return None
                
        except Exception as e:
            self.logger.debug(f"eSpeak ошибка: {e}")
            return None

    def _synthesize_with_festival_direct(self, text: str, language: str) -> Optional[str]:
        """Прямой синтез через Festival с созданием совместимых WAV файлов"""
        try:
            import subprocess
            
            # Проверка наличия Festival
            result = subprocess.run(['which', 'festival'], capture_output=True)
            if result.returncode != 0:
                self.logger.debug("Festival не найден")
                return None
            
            output_path = self.config.get_temp_filename("festival_tts", ".wav")
            
            # Создание скрипта для Festival с сохранением в WAV
            script_content = f'''
(set! text "{text}")
(set! utt (SayText text))
(utt.save.wave utt "{output_path}" 'riff)
'''
            
            script_path = self.config.get_temp_filename("festival_script", ".scm")
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            cmd = ['festival', '-b', str(script_path)]
            
            self.logger.info(f"Выполняем Festival: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Очистка временного скрипта
            try:
                Path(script_path).unlink()
            except:
                pass
            
            if result.returncode == 0 and Path(output_path).exists() and Path(output_path).stat().st_size > 100:
                self.logger.info(f"Festival создал файл: {output_path}")
                return str(output_path)
            else:
                self.logger.warning(f"Festival неудача: {result.stderr}")
                return None
                
        except Exception as e:
            self.logger.debug(f"Festival ошибка: {e}")
            return None

    def _try_pyttsx3_improved(self, text: str, language: str, speed: float, pitch: float) -> Optional[str]:
        """Улучшенный синтез через pyttsx3 с Python-конвертацией"""
        try:
            self.logger.info(f"🎯 Начинаем pyttsx3 синтез: '{text[:30]}...'")
            
            import pyttsx3

            engine = pyttsx3.init()

            # Получаем все доступные голоса
            voices = engine.getProperty('voices')
            self.logger.info(f"🎤 pyttsx3: найдено {len(voices)} голосов")

            # Поиск русского голоса
            russian_voice = None
            for voice in voices:
                if language.startswith('ru') and any(marker in voice.id.lower() for marker in ['ru', 'russian']):
                    russian_voice = voice.id
                    self.logger.info(f"🇷🇺 Найден русский голос: {voice.name}")
                    break

            # Устанавливаем голос если найден
            if russian_voice:
                engine.setProperty('voice', russian_voice)
                self.logger.info(f"✅ Установлен русский голос: {russian_voice}")
            else:
                self.logger.warning("⚠️ Русский голос не найден, используем по умолчанию")

            # Настройка параметров
            rate = max(100, min(300, int(200 * speed)))  # 100-300 слов в минуты
            engine.setProperty('rate', rate)
            engine.setProperty('volume', 1.0)
            self.logger.info(f"⚙️ Параметры: скорость={rate}, громкость=1.0")

            # Создание временного AIFF файла
            aiff_path = self.config.get_temp_filename("pyttsx3_raw", ".aiff")
            self.logger.info(f"📁 Создаем AIFF файл: {aiff_path}")

            # Синтез и сохранение в AIFF
            engine.save_to_file(text, str(aiff_path))
            engine.runAndWait()

            # Дополнительное ожидание для macOS
            import time
            time.sleep(1)

            # Проверяем, что файл создался
            if not Path(aiff_path).exists():
                self.logger.error("❌ pyttsx3 не создал файл")
                return None
            
            size = Path(aiff_path).stat().st_size
            self.logger.info(f"📊 AIFF файл: {size} байт")
            
            # Более строгая проверка размера для macOS pyttsx3
            if size < 10000:  # Минимум 10KB для реального аудио
                self.logger.error(f"❌ pyttsx3 создал пустой/слишком маленький файл: {size} байт")
                
                # Попробуем альтернативный метод для macOS
                self.logger.info("🔄 Пробуем альтернативный метод pyttsx3...")
                alternative_result = self._try_pyttsx3_alternative(text, language, engine)
                if alternative_result:
                    return alternative_result
                
                return None
                
            self.logger.info(f"✅ AIFF файл создан корректно: {size} байт")

            # Конвертация через pydub (работает лучше чем FFmpeg для AIFF)
            self.logger.info("🔄 Начинаем конвертацию AIFF -> WAV...")
            wav_path = self._convert_aiff_to_wav_python(aiff_path)
            
            if wav_path:
                self.logger.info(f"✅ pyttsx3 конвертация успешна: {wav_path}")
                # НЕ удаляем AIFF файл для отладки
                # try:
                #     Path(aiff_path).unlink()
                # except:
                #     pass
                return wav_path
            else:
                self.logger.warning("Конвертация AIFF -> WAV неудачна")
                return None

        except ImportError:
            self.logger.error("pyttsx3 не установлен")
            return None
        except Exception as e:
            self.logger.error(f"pyttsx3 ошибка: {e}")
            return None
    
    def _get_macos_voice(self, voice_id: str, language: str = None) -> str:
        """
        Получает реальное имя голоса macOS по voice_id или языку
        
        Args:
            voice_id: идентификатор голоса
            language: код языка для автоматического выбора голоса
            
        Returns:
            str: имя голоса macOS
        """
        # Если voice_id в старой карте голосов, используем его
        if voice_id in self.voice_map:
            return self.voice_map[voice_id]
        
        # Если voice_id это уже имя голоса macOS, возвращаем как есть
        if voice_id in ['Milena', 'Lesya', 'Samantha', 'Alex', 'Anna', 'Markus', 
                       'Amelie', 'Thomas', 'Monica', 'Jorge', 'Alice', 'Luca',
                       'Joana', 'Luciana', 'Ting-Ting', 'Sin-ji', 'Kyoko', 'Otoya',
                       'Yuna', 'Maged', 'Yelda', 'Zosia', 'Krzysztof', 'Ellen',
                       'Xander', 'Klara', 'Oskar', 'Nora', 'Henrik', 'Sara',
                       'Magnus', 'Satu', 'Onni']:
            return voice_id
        
        # Если указан язык, выбираем голос по языку
        if language:
            voice = self._get_voice_for_language(language)
            self.logger.info(f"🎤 Автоматический выбор голоса для {language}: {voice}")
            return voice
        
        # Fallback
        self.logger.warning(f"⚠️ Неизвестный voice_id: {voice_id}, используем Samantha")
        return 'Samantha'
    
    def _get_voice_params(self, voice_id: str, language: str = None) -> Dict:
        """
        Получает базовые параметры голоса для языка (без автоматической адаптации скорости)
        
        Args:
            voice_id: идентификатор голоса
            language: код языка для языково-специфичных параметров
            
        Returns:
            Dict: базовые параметры голоса (rate, pitch_adj)
        """
        # Получаем базовые параметры для языка
        base_params = self.language_voice_params.get(language.lower() if language else 'ru', {'rate': 190, 'pitch_adj': 'normal'})
        
        # ОТКЛЮЧАЕМ автоматический подбор скорости - используем только базовые языковые скорости
        # Синхронизация полностью контролируется через audio_processor.adjust_audio_duration
        self.logger.debug(f"🎵 {language.upper() if language else 'DEFAULT'}: используем базовую скорость {base_params['rate']} (автоподбор отключен)")
        return base_params
        
        # Проверяем старые параметры голосов для обратной совместимости
        if voice_id in self.voice_params:
            return self.voice_params[voice_id]
        
        return base_params
    
    def _calculate_conservative_rate_universal(self, text_length: int, target_duration: float, base_rate: int, language: str) -> int:
        """
        Консервативно корректирует скорость речи только в крайних случаях для сохранения синхронизации
        
        Args:
            text_length: длина текста в символах
            target_duration: целевая длительность в секундах
            base_rate: базовая скорость
            language: код языка для специфичных настроек
            
        Returns:
            int: скорректированная скорость речи (или базовая, если коррекция не нужна)
        """
        # Языково-специфичные коэффициенты и ограничения
        language_configs = {
            # Арабские и семитские языки - медленнее для ясности
            'ar': {'min_rate': 120, 'max_rate': 200, 'speed_factor': 0.9},  # Арабский
            'he': {'min_rate': 130, 'max_rate': 210, 'speed_factor': 0.95}, # Иврит
            
            # Азиатские языки
            'zh': {'min_rate': 140, 'max_rate': 280, 'speed_factor': 1.2},  # Китайский - быстрее
            'ja': {'min_rate': 130, 'max_rate': 220, 'speed_factor': 1.0},  # Японский
            'ko': {'min_rate': 140, 'max_rate': 230, 'speed_factor': 1.1},  # Корейский
            'th': {'min_rate': 130, 'max_rate': 200, 'speed_factor': 0.9},  # Тайский
            'vi': {'min_rate': 140, 'max_rate': 220, 'speed_factor': 1.0},  # Вьетнамский
            'hi': {'min_rate': 130, 'max_rate': 210, 'speed_factor': 0.95}, # Хинди
            'id': {'min_rate': 140, 'max_rate': 220, 'speed_factor': 1.0},  # Индонезийский
            'ms': {'min_rate': 140, 'max_rate': 220, 'speed_factor': 1.0},  # Малайский
            
            # Тюркские языки
            'tr': {'min_rate': 140, 'max_rate': 220, 'speed_factor': 1.0},  # Турецкий
            
            # Финно-угорские языки - медленнее
            'fi': {'min_rate': 120, 'max_rate': 200, 'speed_factor': 0.9},  # Финский
            'hu': {'min_rate': 130, 'max_rate': 210, 'speed_factor': 0.95}, # Венгерский
            'et': {'min_rate': 120, 'max_rate': 200, 'speed_factor': 0.9},  # Эстонский
            
            # Славянские языки
            'ru': {'min_rate': 140, 'max_rate': 240, 'speed_factor': 1.0},  # Русский
            'uk': {'min_rate': 130, 'max_rate': 220, 'speed_factor': 0.95}, # Украинский
            'pl': {'min_rate': 130, 'max_rate': 220, 'speed_factor': 0.95}, # Польский
            'cs': {'min_rate': 130, 'max_rate': 220, 'speed_factor': 0.95}, # Чешский
            'sk': {'min_rate': 130, 'max_rate': 220, 'speed_factor': 0.95}, # Словацкий
            'bg': {'min_rate': 130, 'max_rate': 220, 'speed_factor': 0.95}, # Болгарский
            'hr': {'min_rate': 130, 'max_rate': 220, 'speed_factor': 0.95}, # Хорватский
            'sl': {'min_rate': 130, 'max_rate': 220, 'speed_factor': 0.95}, # Словенский
            
            # Балтийские языки
            'lv': {'min_rate': 125, 'max_rate': 210, 'speed_factor': 0.9},  # Латышский
            'lt': {'min_rate': 125, 'max_rate': 210, 'speed_factor': 0.9},  # Литовский
            
            # Романские языки
            'fr': {'min_rate': 140, 'max_rate': 220, 'speed_factor': 1.0},  # Французский
            'es': {'min_rate': 140, 'max_rate': 230, 'speed_factor': 1.05}, # Испанский - чуть быстрее
            'it': {'min_rate': 140, 'max_rate': 225, 'speed_factor': 1.0},  # Итальянский
            'pt': {'min_rate': 140, 'max_rate': 230, 'speed_factor': 1.05}, # Португальский
            'ro': {'min_rate': 135, 'max_rate': 220, 'speed_factor': 1.0},  # Румынский
            
            # Германские языки
            'en': {'min_rate': 150, 'max_rate': 250, 'speed_factor': 1.1},  # Английский - быстрее
            'de': {'min_rate': 140, 'max_rate': 220, 'speed_factor': 1.0},  # Немецкий
            'nl': {'min_rate': 140, 'max_rate': 225, 'speed_factor': 1.0},  # Голландский
            'sv': {'min_rate': 140, 'max_rate': 220, 'speed_factor': 1.0},  # Шведский
            'no': {'min_rate': 140, 'max_rate': 220, 'speed_factor': 1.0},  # Норвежский
            'da': {'min_rate': 140, 'max_rate': 225, 'speed_factor': 1.0},  # Датский
            
            # Изолированные языки
            'el': {'min_rate': 135, 'max_rate': 220, 'speed_factor': 1.0},  # Греческий
            
            'default': {'min_rate': 130, 'max_rate': 220, 'speed_factor': 1.0}  # По умолчанию
        }
        
        # Получаем конфигурацию для языка
        config = language_configs.get(language.lower(), language_configs['default'])
        
        # Примерная скорость произношения: символов в секунду
        chars_per_second = text_length / target_duration if target_duration > 0 else 10
        
        # КОНСЕРВАТИВНАЯ коррекция: вмешиваемся только в крайних случаях
        # Основная синхронизация идет через audio_processor.adjust_audio_duration
        
        # Случай 1: Слишком быстрый текст (>20 символов/сек) - слегка ускоряем TTS
        if chars_per_second > 20:
            adaptive_rate = min(config['max_rate'], int(base_rate * 1.15))
            
        # Случай 2: Экстремально медленный текст (<3 символов/сек) - замедляем TTS  
        elif chars_per_second < 3:
            adaptive_rate = max(config['min_rate'], int(base_rate * 0.85))
            
        # Случай 3: Украинский язык с известными проблемами качества - слегка замедляем
        elif language.lower() == 'uk' and chars_per_second < 8:
            adaptive_rate = max(config['min_rate'], int(base_rate * 0.92))
            
        # Во всех остальных случаях используем базовую скорость
        else:
            adaptive_rate = base_rate
        
        return adaptive_rate
    
    def _synthesize_with_say_voice_params(self, text: str, language: str, voice_name: str, params: Dict) -> Optional[str]:
        """Синтез речи через macOS 'say' команду с указанным голосом и параметрами"""
        try:
            self.logger.info(f"🍎 Синтез через macOS 'say' с голосом {voice_name} (rate={params.get('rate', 190)})...")
            
            import subprocess
            
            # Создаем временный AIFF файл через say
            aiff_path = self.config.get_temp_filename(f"{voice_name.lower()}_say", ".aiff")
            
            # Команда say с выбранным голосом и скоростью
            cmd = [
                'say',
                '-v', voice_name,
                '-r', str(params.get('rate', 190)),  # Скорость в словах/мин
                '-o', str(aiff_path),
                text
            ]
            
            self.logger.info(f"🎙️ Создаем голос {voice_name} для: '{text[:30]}...'")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                self.logger.warning(f"⚠️ say команда неудачна (код {result.returncode}): {result.stderr}")
                
                # Fallback на стандартные параметры
                if params.get('rate', 190) != 190:
                    self.logger.info("🔄 Fallback на стандартную скорость...")
                    return self._synthesize_with_say_voice_params(text, language, voice_name, {'rate': 190, 'pitch_adj': 'normal'})
                else:
                    return None
            
            if not Path(aiff_path).exists():
                self.logger.error(f"❌ AIFF файл не создан: {aiff_path}")
                return None
            
            # Конвертируем AIFF в WAV через ffmpeg с обработкой высоты тона
            wav_path = self.config.get_temp_filename(f"{voice_name.lower()}_converted", ".wav")
            
            # Базовая команда ffmpeg
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', str(aiff_path),
                '-acodec', 'pcm_s16le',
                '-ar', '22050',
                '-ac', '1'
            ]
            
            # Не изменяем тон - используем стандартные настройки для всех голосов
            
            ffmpeg_cmd.append(str(wav_path))
            
            ffmpeg_result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            
            if ffmpeg_result.returncode == 0 and Path(wav_path).exists():
                # Удаляем временный AIFF файл
                try:
                    Path(aiff_path).unlink()
                except:
                    pass
                
                self.logger.info(f"✅ Создан WAV файл: {wav_path}")
                return str(wav_path)
            else:
                self.logger.error(f"❌ Ошибка ffmpeg: {ffmpeg_result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            self.logger.error("❌ Timeout при выполнении say команды")
            return None
        except Exception as e:
            self.logger.error(f"❌ Ошибка синтеза с голосом {voice_name}: {e}")
            return None

    def _synthesize_with_say_voice(self, text: str, language: str, voice_name: str) -> Optional[str]:
        """Синтез речи через macOS 'say' команду с указанным голосом"""
        try:
            self.logger.info(f"🍎 Синтез через macOS 'say' с голосом {voice_name}...")
            
            import subprocess
            
            # Создаем временный AIFF файл через say
            aiff_path = self.config.get_temp_filename(f"{voice_name.lower()}_say", ".aiff")
            
            # Команда say с выбранным голосом
            cmd = [
                'say',
                '-v', voice_name,
                '-o', str(aiff_path),
                text
            ]
            
            self.logger.info(f"🎙️ Создаем голос {voice_name} для: '{text[:30]}...'")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                self.logger.warning(f"⚠️ say команда неудачна (код {result.returncode}): {result.stderr}")
                
                # Fallback на Milena если голос не найден
                if voice_name != 'Milena':
                    self.logger.info("🔄 Fallback на голос Milena...")
                    return self._synthesize_with_say_voice(text, language, 'Milena')
                else:
                    return None
            
            if not Path(aiff_path).exists():
                self.logger.error(f"❌ AIFF файл не создан: {aiff_path}")
                return None
            
            # Конвертируем AIFF в WAV через ffmpeg
            wav_path = self.config.get_temp_filename(f"{voice_name.lower()}_converted", ".wav")
            
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', str(aiff_path),
                '-acodec', 'pcm_s16le',
                '-ar', '22050',
                '-ac', '1',
                str(wav_path)
            ]
            
            ffmpeg_result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            
            if ffmpeg_result.returncode == 0 and Path(wav_path).exists():
                # Удаляем временный AIFF файл
                try:
                    Path(aiff_path).unlink()
                except:
                    pass
                
                self.logger.info(f"✅ Создан WAV файл: {wav_path}")
                return str(wav_path)
            else:
                self.logger.error(f"❌ Ошибка ffmpeg: {ffmpeg_result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            self.logger.error("❌ Timeout при выполнении say команды")
            return None
        except Exception as e:
            self.logger.error(f"❌ Ошибка синтеза с голосом {voice_name}: {e}")
            return None

    def _synthesize_with_say_milena(self, text: str, language: str) -> Optional[str]:
        """Основной метод синтеза через macOS 'say' команду с голосом Milena"""
        try:
            self.logger.info("🍎 Синтез через macOS 'say' с голосом Milena...")
            
            import subprocess
            
            # Создаем временный AIFF файл через say
            aiff_path = self.config.get_temp_filename("milena_say", ".aiff")
            
            # Команда say с голосом Milena (высочайшее качество)
            cmd = [
                'say',
                '-v', 'Milena',  # Используем простое имя голоса Milena
                '-o', str(aiff_path),
                text
            ]
            
            self.logger.info(f"🎙️ Создаем голос Milena для: '{text[:30]}...'")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                if Path(aiff_path).exists():
                    size = Path(aiff_path).stat().st_size
                    self.logger.info(f"📁 AIFF файл Milena: {size} байт")
                    
                    if size > 10000:  # Реальный размер аудио файла
                        # Конвертируем в WAV
                        wav_path = self._convert_aiff_to_wav_python(aiff_path)
                        if wav_path:
                            self.logger.info("🎉 Голос Milena создан успешно!")
                            return wav_path
                        else:
                            self.logger.error("❌ Ошибка конвертации Milena AIFF -> WAV")
                    else:
                        self.logger.error(f"❌ 'say' создал пустой файл: {size} байт")
                else:
                    self.logger.error("❌ 'say' не создал файл")
            else:
                self.logger.error(f"❌ 'say' ошибка: {result.stderr}")
                
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка синтеза через 'say': {e}")
            return None

    def _convert_aiff_to_wav_python(self, aiff_path: str) -> Optional[str]:
        """Конвертация AIFF в WAV через pydub с увеличением громкости"""
        try:
            from pydub import AudioSegment
            
            wav_path = self.config.get_temp_filename("milena_converted", ".wav")
            
            self.logger.info(f"🔄 Конвертируем AIFF -> WAV: {aiff_path}")
            
            # Проверяем исходный файл
            if not Path(aiff_path).exists():
                self.logger.error(f"❌ AIFF файл не существует: {aiff_path}")
                return None
                
            aiff_size = Path(aiff_path).stat().st_size
            self.logger.info(f"📁 AIFF файл: {aiff_size} байт")
            
            # Загружаем AIFF файл (pydub умеет читать AIFF)
            self.logger.info("📖 Загружаем AIFF файл...")
            audio = AudioSegment.from_file(aiff_path, format="aiff")
            
            duration = len(audio) / 1000.0
            volume = audio.dBFS
            self.logger.info(f"🎵 AIFF: длительность={duration:.2f}с, громкость={volume:.1f}dBFS")
            
            # Увеличиваем громкость если слишком тихо
            if audio.dBFS < -30:
                gain_db = -20 - audio.dBFS  # Поднимаем до -20dB
                audio = audio + gain_db
                self.logger.info(f"🔊 Увеличена громкость на {gain_db:.1f}dB")
            
            # Сохраняем как WAV с оптимальными параметрами
            self.logger.info(f"💾 Сохраняем WAV: {wav_path}")
            audio.export(str(wav_path), format="wav", parameters=["-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1"])
            
            # Проверяем результат
            if not Path(wav_path).exists():
                self.logger.error("❌ WAV файл не создался")
                return None
                
            wav_size = Path(wav_path).stat().st_size
            self.logger.info(f"✅ WAV файл создан: {wav_size} байт")
            
            if wav_size > 1000:
                self.logger.info(f"🎉 pyttsx3 конвертация успешна: {wav_path}")
                return str(wav_path)
            else:
                self.logger.error(f"❌ Конвертированный WAV файл слишком мал: {wav_size} байт")
                return None
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка Python конвертации: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    # def _try_pyttsx3(self, text: str, language: str, speed: float, pitch: float) -> Optional[str]:
    #     """Попытка синтеза через pyttsx3"""
    #     try:
    #         import pyttsx3
    #
    #         engine = pyttsx3.init()
    #
    #         # Настройка параметров
    #         voices = engine.getProperty('voices')
    #
    #         # Поиск подходящего голоса для языка
    #         target_voice = None
    #         for voice in voices:
    #             if language.startswith('ru') and ('ru' in voice.id.lower() or 'russian' in voice.name.lower()):
    #                 target_voice = voice.id
    #                 break
    #             elif language.startswith('en') and ('en' in voice.id.lower() or 'english' in voice.name.lower()):
    #                 target_voice = voice.id
    #                 break
    #
    #         if target_voice:
    #             engine.setProperty('voice', target_voice)
    #
    #         # Настройка скорости (обычно 150-250 слов в минуту)
    #         rate = int(200 * speed)
    #         engine.setProperty('rate', rate)
    #
    #         # Настройка громкости
    #         engine.setProperty('volume', 1.0)
    #
    #         # Сохранение в файл
    #         output_path = self.config.get_temp_filename("pyttsx3_tts", ".wav")
    #         engine.save_to_file(text, str(output_path))
    #         engine.runAndWait()
    #
    #         if Path(output_path).exists() and Path(output_path).stat().st_size > 0:
    #             return str(output_path)
    #
    #         return None
    #
    #     except ImportError:
    #         return None
    #     except Exception:
    #         return None
    
    def _try_espeak(self, text: str, language: str, speed: float, pitch: float) -> Optional[str]:
        """Попытка синтеза через eSpeak"""
        try:
            import subprocess
            
            # Проверка наличия eSpeak
            subprocess.run(['espeak', '--version'], 
                          capture_output=True, check=True)
            
            output_path = self.config.get_temp_filename("espeak_tts", ".wav")
            
            # Настройка параметров
            lang_code = 'ru' if language.startswith('ru') else 'en'
            speed_wpm = int(175 * speed)  # слов в минуту
            pitch_val = int(50 + pitch)   # 0-99
            
            cmd = [
                'espeak',
                '-v', lang_code,
                '-s', str(speed_wpm),
                '-p', str(pitch_val),
                '-w', str(output_path),
                text
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and Path(output_path).exists():
                return str(output_path)
            
            return None
            
        except (ImportError, subprocess.CalledProcessError, FileNotFoundError):
            return None
    
    def _try_festival(self, text: str, language: str, speed: float, pitch: float) -> Optional[str]:
        """Попытка синтеза через Festival"""
        try:
            import subprocess
            
            # Проверка наличия Festival
            subprocess.run(['festival', '--version'], 
                          capture_output=True, check=True)
            
            output_path = self.config.get_temp_filename("festival_tts", ".wav")
            
            # Создание временного текстового файла
            text_path = self.config.get_temp_filename("festival_text", ".txt")
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(text)
            
            # Команда Festival
            cmd = [
                'festival',
                '--tts',
                str(text_path)
            ]
            
            # Перенаправление вывода в WAV файл
            with open(output_path, 'wb') as output_file:
                result = subprocess.run(cmd, stdout=output_file, stderr=subprocess.PIPE)
            
            # Очистка временного файла
            Path(text_path).unlink(missing_ok=True)
            
            if result.returncode == 0 and Path(output_path).exists():
                return str(output_path)
            
            return None
            
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
    
    def synthesize_batch(
        self, 
        texts: List[str], 
        language: str = None, 
        voice: str = None
    ) -> List[Dict]:
        """
        Пакетный синтез речи для нескольких текстов
        
        Args:
            texts: список текстов для синтеза
            language: код языка
            voice: голос для синтеза
            
        Returns:
            list: список результатов синтеза
        """
        results = []
        
        for i, text in enumerate(texts):
            self.logger.info(f"Синтез текста {i+1}/{len(texts)}: '{text[:30]}...'")
            
            start_time = None
            try:
                import time
                start_time = time.time()
                
                audio_path = self.synthesize_speech(text, language, voice)
                
                processing_time = time.time() - start_time if start_time else 0
                
                result = {
                    'text': text,
                    'audio_path': audio_path,
                    'success': bool(audio_path),
                    'processing_time': processing_time,
                    'error': None
                }
                
            except Exception as e:
                result = {
                    'text': text,
                    'audio_path': None,
                    'success': False,
                    'processing_time': 0,
                    'error': str(e)
                }
                
                self.logger.error(f"Ошибка синтеза текста '{text[:30]}...': {e}")
            
            results.append(result)
        
        success_count = sum(1 for r in results if r['success'])
        self.logger.info(f"Пакетный синтез завершен: {success_count}/{len(texts)} успешно")
        
        return results
    
    def get_available_voices(self) -> Dict[str, List[Dict]]:
        """
        Получение списка доступных голосов
        
        Returns:
            dict: словарь с голосами по языкам
        """
        voices = {
            'google_tts': [
                {'id': 'ru', 'name': 'Russian', 'language': 'ru'},
                {'id': 'en', 'name': 'English', 'language': 'en'},
                {'id': 'es', 'name': 'Spanish', 'language': 'es'},
                {'id': 'fr', 'name': 'French', 'language': 'fr'},
                {'id': 'de', 'name': 'German', 'language': 'de'},
                {'id': 'it', 'name': 'Italian', 'language': 'it'},
            ],
            'elevenlabs': [
                {'id': '21m00Tcm4TlvDq8ikWAM', 'name': 'Rachel', 'language': 'en'},
                {'id': 'AZnzlk1XvdvUeBnXmlld', 'name': 'Domi', 'language': 'en'},
                {'id': 'EXAVITQu4vr4xnSDxMaL', 'name': 'Bella', 'language': 'en'},
                # Русские голоса ElevenLabs (если доступны)
                {'id': 'custom_ru_voice', 'name': 'Russian Voice', 'language': 'ru'},
            ]
        }
        
        # Добавление локальных голосов если доступны
        try:
            import pyttsx3
            engine = pyttsx3.init()
            local_voices = engine.getProperty('voices')
            
            voices['local'] = []
            for voice in local_voices:
                voices['local'].append({
                    'id': voice.id,
                    'name': voice.name,
                    'language': self._detect_voice_language(voice.name)
                })
                
        except ImportError:
            voices['local'] = []
        
        return voices
    
    def _detect_voice_language(self, voice_name: str) -> str:
        """Определение языка голоса по имени"""
        voice_name_lower = voice_name.lower()
        
        if any(word in voice_name_lower for word in ['russian', 'ru', 'милена', 'александр']):
            return 'ru'
        elif any(word in voice_name_lower for word in ['english', 'en', 'american', 'british']):
            return 'en'
        elif any(word in voice_name_lower for word in ['spanish', 'es', 'español']):
            return 'es'
        elif any(word in voice_name_lower for word in ['french', 'fr', 'français']):
            return 'fr'
        elif any(word in voice_name_lower for word in ['german', 'de', 'deutsch']):
            return 'de'
        else:
            return 'unknown'
    
    def test_tts_engines(self) -> Dict[str, bool]:
        """
        Тестирование доступности macOS 'say' команды с голосом Milena
        
        Returns:
            dict: статус доступности Milena
        """
        engines = {}
        
        # Тестируем macOS 'say' команду с голосом Milena
        try:
            import subprocess
            
            # Проверяем доступность команды say
            result = subprocess.run(['which', 'say'], capture_output=True)
            if result.returncode != 0:
                engines['milena'] = False
                self.logger.error("❌ macOS 'say' команда недоступна")
                return engines
            
            # Проверяем доступность голоса Milena
            result = subprocess.run(['say', '-v', '?'], capture_output=True, text=True)
            if result.returncode == 0:
                voices_output = result.stdout
                # Ищем голос Milena (простое имя)
                if 'Milena' in voices_output and 'ru_RU' in voices_output:
                    engines['milena'] = True
                    self.logger.info("✅ Голос Milena доступен (русский, высокое качество)")
                else:
                    engines['milena'] = False
                    self.logger.error(f"❌ Голос Milena не найден в системе")
                    self.logger.debug(f"Доступные голоса (поиск Milena): {voices_output[:500]}")
            else:
                engines['milena'] = False
                self.logger.error("❌ Ошибка проверки голосов")
                
        except Exception as e:
            engines['milena'] = False
            self.logger.error(f"❌ Ошибка тестирования Milena: {e}")
        
        return engines
    
    def estimate_synthesis_time(self, text: str, method: str = 'google_tts') -> float:
        """
        Оценка времени синтеза речи
        
        Args:
            text: текст для синтеза
            method: метод синтеза
            
        Returns:
            float: оценка времени в секундах
        """
        char_count = len(text)
        word_count = len(text.split())
        
        # Примерные времена для разных методов
        time_estimates = {
            'google_tts': 0.1 + (char_count * 0.01),      # ~0.01s на символ
            'elevenlabs': 0.5 + (word_count * 0.2),       # ~0.2s на слово
            'local': 0.05 + (word_count * 0.1),           # ~0.1s на слово
        }
        
        return time_estimates.get(method, char_count * 0.01)
    
    def get_synthesis_quality_info(self, audio_path: str) -> Optional[Dict]:
        """
        Анализ качества синтезированной речи
        
        Args:
            audio_path: путь к аудио файлу
            
        Returns:
            dict: информация о качестве
        """
        try:
            if not Path(audio_path).exists():
                return None
            
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            
            # Базовые характеристики качества
            quality_info = {
                'sample_rate': audio.frame_rate,
                'bit_depth': audio.sample_width * 8,
                'channels': audio.channels,
                'duration': len(audio) / 1000.0,
                'file_size': Path(audio_path).stat().st_size,
                'average_loudness': audio.dBFS,
                'max_loudness': audio.max_dBFS,
                'format': Path(audio_path).suffix[1:].upper()
            }
            
            # Оценка качества на основе параметров
            quality_score = self._calculate_quality_score(quality_info)
            quality_info['quality_score'] = quality_score
            quality_info['quality_rating'] = self._get_quality_rating(quality_score)
            
            return quality_info
            
        except Exception as e:
            self.logger.error(f"Ошибка анализа качества: {e}")
            return None
    
    def _calculate_quality_score(self, info: Dict) -> float:
        """Расчет оценки качества на основе технических параметров"""
        score = 0.0
        
        # Sample rate (до 40 баллов)
        if info['sample_rate'] >= 44100:
            score += 40
        elif info['sample_rate'] >= 22050:
            score += 30
        elif info['sample_rate'] >= 16000:
            score += 20
        else:
            score += 10
        
        # Bit depth (до 30 баллов)
        if info['bit_depth'] >= 24:
            score += 30
        elif info['bit_depth'] >= 16:
            score += 25
        else:
            score += 15
        
        # Громкость (до 30 баллов)
        loudness = info['average_loudness']
        if -25 <= loudness <= -10:  # Оптимальный диапазон
            score += 30
        elif -35 <= loudness <= -5:
            score += 20
        else:
            score += 10
        
        return min(score, 100)  # Максимум 100 баллов
    
    def _get_quality_rating(self, score: float) -> str:
        """Преобразование оценки в текстовый рейтинг"""
        if score >= 90:
            return "Отличное"
        elif score >= 75:
            return "Хорошее"
        elif score >= 60:
            return "Удовлетворительное"
        elif score >= 40:
            return "Низкое"
        else:
            return "Очень низкое"


if __name__ == "__main__":
    # Тестирование модуля
    print("=== Тестирование SpeechSynthesizer ===")
    
    synthesizer = SpeechSynthesizer()
    print("SpeechSynthesizer инициализирован")
    
    # Тест доступных движков
    engines = synthesizer.test_tts_engines()
    print(f"Доступные TTS движки: {engines}")
    
    # Тест доступных голосов
    voices = synthesizer.get_available_voices()
    for engine, voice_list in voices.items():
        print(f"{engine}: {len(voice_list)} голосов")
    
    # Тест синтеза
    test_text = "Привет мир"
    result = synthesizer.synthesize_speech(test_text)
    if result:
        print(f"Тестовый синтез успешен: {result}")
        
        # Анализ качества
        quality = synthesizer.get_synthesis_quality_info(result)
        if quality:
            print(f"Качество: {quality['quality_rating']} ({quality['quality_score']:.1f}/100)")
    else:
        print("Тестовый синтез неудачен")