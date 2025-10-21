#!/usr/bin/env python3
"""
TTSEngineFactory: Фабрика TTS движков с поддержкой выбора модели для любого языка
Поддерживает macOS TTS, Google TTS, и ElevenLabs TTS
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from enum import Enum
from dataclasses import dataclass

from gtts import gTTS
import subprocess
import tempfile

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import config
from core.voice_cloner import VoiceCloner


class TTSEngine(Enum):
    """Доступные TTS движки"""
    MACOS = "macos"
    GOOGLE_TTS = "google_tts"
    ELEVENLABS = "elevenlabs"
    UKRAINIAN_TTS = "ukrainian_tts"  # ESPnet-based Ukrainian TTS
    RADTTS_UK = "radtts_uk"         # RADTTS Ukrainian model
    PORETSKY_RU = "poretsky_ru"     # Poretsky Russian TTS
    VOICE_CLONING = "voice_cloning"  # Custom voice cloning engine
    AUTO = "auto"  # Автоматический выбор лучшего движка для языка


@dataclass
class TTSEngineInfo:
    """Информация о TTS движке"""
    name: str
    description: str
    supported_languages: List[str]
    quality_score: int  # 1-10, где 10 - лучшее качество
    speed_score: int    # 1-10, где 10 - самый быстрый
    cost: str          # "free", "api_key", "paid"
    limitations: str


@dataclass 
class VoiceInfo:
    """Информация о голосе"""
    name: str
    language: str
    gender: str
    engine: TTSEngine
    quality_issues: bool = False
    rate: int = 180
    description: str = ""


class TTSEngineFactory:
    """Фабрика для создания и управления TTS движками"""
    
    def __init__(self):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Информация о доступных движках
        self.engines_info = {
            TTSEngine.MACOS: TTSEngineInfo(
                name="macOS System TTS",
                description="Встроенный TTS macOS с высоким качеством",
                supported_languages=["ru", "uk", "en", "de", "fr", "es", "it", "pt", "zh", "ja", "ko", "ar", "tr", "pl", "nl", "sv", "no", "da", "fi"],
                quality_score=8,
                speed_score=9,
                cost="free",
                limitations="Только macOS, ограниченный набор голосов"
            ),
            TTSEngine.GOOGLE_TTS: TTSEngineInfo(
                name="Google Text-to-Speech",
                description="Google TTS с поддержкой множества языков",
                supported_languages=["ru", "uk", "en", "de", "fr", "es", "it", "pt", "zh", "ja", "ko", "ar", "tr", "pl", "nl", "sv", "no", "da", "fi", "hi", "th", "vi", "hu", "cs", "sk", "ro", "bg", "hr", "sl", "lv", "lt", "et"],
                quality_score=7,
                speed_score=6,
                cost="free",
                limitations="Требует интернет, ограничения по количеству запросов"
            ),
            TTSEngine.ELEVENLABS: TTSEngineInfo(
                name="ElevenLabs TTS",
                description="AI TTS с максимальным качеством и реалистичностью",
                supported_languages=["en", "ru", "de", "fr", "es", "it", "pt", "pl", "uk"],
                quality_score=10,
                speed_score=4,
                cost="api_key",
                limitations="Требует API ключ, платный, медленный"
            ),
            TTSEngine.UKRAINIAN_TTS: TTSEngineInfo(
                name="Ukrainian TTS (ESPnet)",
                description="Специализированный ESPnet-based TTS для украинского языка",
                supported_languages=["uk"],
                quality_score=9,
                speed_score=7,
                cost="free",
                limitations="Требует установки ESPnet, только украинский язык"
            ),
            TTSEngine.RADTTS_UK: TTSEngineInfo(
                name="RADTTS Ukrainian",
                description="RADTTS модель специально для украинского языка",
                supported_languages=["uk"],
                quality_score=8,
                speed_score=6,
                cost="free",
                limitations="Требует GPU для оптимальной работы, только украинский"
            ),
            TTSEngine.PORETSKY_RU: TTSEngineInfo(
                name="Poretsky Russian TTS",
                description="Специализированный TTS для русского языка от Poretsky",
                supported_languages=["ru"],
                quality_score=8,
                speed_score=7,
                cost="free",
                limitations="Только русский язык, требует установки зависимостей"
            ),
            TTSEngine.VOICE_CLONING: TTSEngineInfo(
                name="Voice Cloning TTS",
                description="Клонирование голоса на основе образцов речи из диаризации",
                supported_languages=["ru", "uk", "en", "de", "fr", "es", "it", "pt", "pl"],
                quality_score=9,
                speed_score=5,
                cost="free",
                limitations="Требует образцы голоса для клонирования, медленнее стандартных TTS"
            )
        }
        
        # Определяем доступные голоса для каждого движка
        self.available_voices = self._discover_available_voices()
        
        # Initialize voice cloner
        self.voice_cloner = VoiceCloner(self.config)
        
        # Рекомендуемые движки для каждого языка (в порядке приоритета)
        self.language_engine_priority = {
            'ru': [TTSEngine.PORETSKY_RU, TTSEngine.MACOS, TTSEngine.GOOGLE_TTS, TTSEngine.ELEVENLABS],
            'uk': [TTSEngine.UKRAINIAN_TTS, TTSEngine.RADTTS_UK, TTSEngine.MACOS, TTSEngine.GOOGLE_TTS, TTSEngine.ELEVENLABS], 
            'en': [TTSEngine.MACOS, TTSEngine.ELEVENLABS, TTSEngine.GOOGLE_TTS],
            'de': [TTSEngine.MACOS, TTSEngine.GOOGLE_TTS, TTSEngine.ELEVENLABS],
            'fr': [TTSEngine.MACOS, TTSEngine.GOOGLE_TTS, TTSEngine.ELEVENLABS],
            'es': [TTSEngine.MACOS, TTSEngine.GOOGLE_TTS, TTSEngine.ELEVENLABS],
            'it': [TTSEngine.MACOS, TTSEngine.GOOGLE_TTS, TTSEngine.ELEVENLABS],
            'pt': [TTSEngine.MACOS, TTSEngine.GOOGLE_TTS, TTSEngine.ELEVENLABS],
            'pl': [TTSEngine.MACOS, TTSEngine.GOOGLE_TTS, TTSEngine.ELEVENLABS],
            # Для остальных языков Google TTS обычно лучше
            'default': [TTSEngine.GOOGLE_TTS, TTSEngine.MACOS, TTSEngine.ELEVENLABS]
        }
        
        self.logger.info("🏭 TTSEngineFactory инициализирована")
        self._log_available_engines()
    
    def _discover_available_voices(self) -> Dict[TTSEngine, List[VoiceInfo]]:
        """Обнаружение доступных голосов в системе"""
        voices = {
            TTSEngine.MACOS: [],
            TTSEngine.GOOGLE_TTS: [],
            TTSEngine.ELEVENLABS: [],
            TTSEngine.UKRAINIAN_TTS: [],
            TTSEngine.RADTTS_UK: [],
            TTSEngine.PORETSKY_RU: []
        }
        
        # Обнаружение macOS голосов
        try:
            result = subprocess.run(['say', '-v', '?'], capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            voice_name = parts[0]
                            lang_code = parts[1] if len(parts) > 1 else 'en_US'
                            
                            # Извлекаем код языка
                            lang = lang_code.split('_')[0] if '_' in lang_code else lang_code[:2]
                            
                            # Определяем качество для известных голосов
                            quality_issues = False
                            if voice_name == 'Lesya' and lang == 'uk':
                                quality_issues = True  # Известные проблемы с украинским голосом
                            
                            voice_info = VoiceInfo(
                                name=voice_name,
                                language=lang,
                                gender="unknown",
                                engine=TTSEngine.MACOS,
                                quality_issues=quality_issues,
                                description=f"macOS системный голос для {lang}"
                            )
                            voices[TTSEngine.MACOS].append(voice_info)
        except Exception as e:
            self.logger.debug(f"Не удалось обнаружить macOS голоса: {e}")
        
        # Google TTS голоса (статический список поддерживаемых языков)
        google_languages = [
            ('ru', 'Russian'), ('uk', 'Ukrainian'), ('en', 'English'),
            ('de', 'German'), ('fr', 'French'), ('es', 'Spanish'),
            ('it', 'Italian'), ('pt', 'Portuguese'), ('pl', 'Polish'),
            ('zh', 'Chinese'), ('ja', 'Japanese'), ('ko', 'Korean'),
            ('ar', 'Arabic'), ('tr', 'Turkish'), ('nl', 'Dutch'),
            ('sv', 'Swedish'), ('no', 'Norwegian'), ('da', 'Danish'),
            ('fi', 'Finnish'), ('hi', 'Hindi'), ('th', 'Thai'),
            ('vi', 'Vietnamese'), ('hu', 'Hungarian'), ('cs', 'Czech'),
            ('sk', 'Slovak'), ('ro', 'Romanian'), ('bg', 'Bulgarian'),
            ('hr', 'Croatian'), ('sl', 'Slovenian'), ('lv', 'Latvian'),
            ('lt', 'Lithuanian'), ('et', 'Estonian')
        ]
        
        for lang_code, lang_name in google_languages:
            voice_info = VoiceInfo(
                name=f"Google-{lang_name}",
                language=lang_code,
                gender="unknown",
                engine=TTSEngine.GOOGLE_TTS,
                description=f"Google TTS для {lang_name}"
            )
            voices[TTSEngine.GOOGLE_TTS].append(voice_info)
        
        # ElevenLabs голоса (требует API ключ)
        if self.config.ELEVENLABS_API_KEY:
            elevenlabs_languages = [
                ('en', 'English'), ('ru', 'Russian'), ('de', 'German'),
                ('fr', 'French'), ('es', 'Spanish'), ('it', 'Italian'),
                ('pt', 'Portuguese'), ('pl', 'Polish'), ('uk', 'Ukrainian')
            ]
            
            for lang_code, lang_name in elevenlabs_languages:
                voice_info = VoiceInfo(
                    name=f"ElevenLabs-{lang_name}",
                    language=lang_code,
                    gender="unknown",
                    engine=TTSEngine.ELEVENLABS,
                    description=f"ElevenLabs AI голос для {lang_name}"
                )
                voices[TTSEngine.ELEVENLABS].append(voice_info)
        
        # Ukrainian TTS (ESPnet) голоса
        ukrainian_tts_voices = [
            ('uk', 'Ukrainian Male (ESPnet)')
        ]
        for lang_code, voice_name in ukrainian_tts_voices:
            voice_info = VoiceInfo(
                name=voice_name,
                language=lang_code,
                gender="male",
                engine=TTSEngine.UKRAINIAN_TTS,
                description="ESPnet-based Ukrainian TTS"
            )
            voices[TTSEngine.UKRAINIAN_TTS].append(voice_info)
        
        # RADTTS-UK голоса
        radtts_uk_voices = [
            ('uk', 'RADTTS Ukrainian Female')
        ]
        for lang_code, voice_name in radtts_uk_voices:
            voice_info = VoiceInfo(
                name=voice_name,
                language=lang_code,
                gender="female",
                engine=TTSEngine.RADTTS_UK,
                description="RADTTS Ukrainian model"
            )
            voices[TTSEngine.RADTTS_UK].append(voice_info)
        
        # Poretsky Russian TTS голоса
        poretsky_ru_voices = [
            ('ru', 'Aidar (Poretsky)'),
            ('ru', 'Baya (Poretsky)'),
            ('ru', 'Kseniya (Poretsky)')
        ]
        for lang_code, voice_name in poretsky_ru_voices:
            voice_info = VoiceInfo(
                name=voice_name,
                language=lang_code,
                gender="unknown",
                engine=TTSEngine.PORETSKY_RU,
                description="Poretsky Russian TTS voice"
            )
            voices[TTSEngine.PORETSKY_RU].append(voice_info)
        
        return voices
    
    def get_available_engines(self) -> List[TTSEngine]:
        """Получить список доступных движков"""
        available = []
        
        # macOS TTS всегда доступен на macOS
        available.append(TTSEngine.MACOS)
        
        # Google TTS доступен если есть интернет (проверяем наличие gtts)
        try:
            import gtts
            available.append(TTSEngine.GOOGLE_TTS)
        except ImportError:
            pass
        
        # ElevenLabs доступен если есть API ключ
        if self.config.ELEVENLABS_API_KEY:
            available.append(TTSEngine.ELEVENLABS)
        
        # Ukrainian TTS (ESPnet) - всегда добавляем (с fallback)
        available.append(TTSEngine.UKRAINIAN_TTS)
        
        # RADTTS-UK - проверяем наличие torch
        try:
            import torch
            available.append(TTSEngine.RADTTS_UK)
        except ImportError:
            pass
        
        # Poretsky Russian TTS - всегда добавляем (с fallback)
        available.append(TTSEngine.PORETSKY_RU)
        
        # Voice Cloning - доступен если включен в конфигурации
        if hasattr(self.config, 'USE_VOICE_CLONING') and self.config.USE_VOICE_CLONING:
            available.append(TTSEngine.VOICE_CLONING)
        
        available.append(TTSEngine.AUTO)
        return available
    
    def get_engine_info(self, engine) -> Optional[TTSEngineInfo]:
        """Получить информацию о движке"""
        # Convert string to enum if needed
        if isinstance(engine, str):
            try:
                engine = TTSEngine(engine)
            except ValueError:
                return None
        return self.engines_info.get(engine)
    
    def get_recommended_engine(self, language: str) -> TTSEngine:
        """Получить рекомендуемый движок для языка"""
        lang = language.lower()
        priorities = self.language_engine_priority.get(lang, self.language_engine_priority['default'])
        
        available_engines = self.get_available_engines()
        
        for engine in priorities:
            if engine in available_engines:
                # Проверяем, поддерживает ли движок этот язык
                if self._engine_supports_language(engine, lang):
                    return engine
        
        # Fallback на первый доступный
        return available_engines[0] if available_engines else TTSEngine.MACOS
    
    def _engine_supports_language(self, engine: TTSEngine, language: str) -> bool:
        """Проверить поддержку языка движком"""
        if engine == TTSEngine.AUTO:
            return True
        
        engine_info = self.engines_info.get(engine)
        if not engine_info:
            return False
        
        return language in engine_info.supported_languages
    
    def get_voices_for_language(self, language: str, engine: TTSEngine = None) -> List[VoiceInfo]:
        """Получить доступные голоса для языка"""
        lang = language.lower()
        voices = []
        
        if engine is None:
            # Ищем во всех движках
            for engine_voices in self.available_voices.values():
                voices.extend([v for v in engine_voices if v.language == lang])
        else:
            # Ищем в конкретном движке
            engine_voices = self.available_voices.get(engine, [])
            voices.extend([v for v in engine_voices if v.language == lang])
        
        return voices
    
    def synthesize_with_engine(
        self, 
        text: str, 
        language: str,
        engine = TTSEngine.AUTO,
        voice_name: str = None,
        target_duration: float = None,
        **kwargs
    ) -> Optional[str]:
        """Синтез речи с указанным движком"""
        
        # Convert string to enum if needed
        if isinstance(engine, str):
            try:
                engine = TTSEngine(engine)
            except ValueError:
                self.logger.error(f"❌ Неизвестный движок TTS: {engine}")
                return None
        
        if engine == TTSEngine.AUTO:
            engine = self.get_recommended_engine(language)
        
        self.logger.info(f"🎤 Синтез речи: движок={engine.value}, язык={language}, текст='{text[:50]}...'")
        
        try:
            if engine == TTSEngine.MACOS:
                return self._synthesize_macos(text, language, voice_name)
            elif engine == TTSEngine.GOOGLE_TTS:
                return self._synthesize_google_tts(text, language, target_duration)
            elif engine == TTSEngine.ELEVENLABS:
                return self._synthesize_elevenlabs(text, language, voice_name)
            elif engine == TTSEngine.UKRAINIAN_TTS:
                return self._synthesize_ukrainian_tts(text, language)
            elif engine == TTSEngine.RADTTS_UK:
                return self._synthesize_radtts_uk(text, language)
            elif engine == TTSEngine.PORETSKY_RU:
                return self._synthesize_poretsky_ru(text, language)
            elif engine == TTSEngine.VOICE_CLONING:
                return self._synthesize_voice_cloning(text, language, 
                                                   speaker_id=kwargs.get('speaker_id'), 
                                                   target_duration=target_duration)
            else:
                self.logger.error(f"Неподдерживаемый движок: {engine}")
                return None
        
        except Exception as e:
            self.logger.error(f"Ошибка синтеза с движком {engine.value}: {e}")
            
            # Fallback на другой движок
            fallback_engine = self._get_fallback_engine(engine, language)
            if fallback_engine and fallback_engine != engine:
                self.logger.info(f"🔄 Fallback на движок {fallback_engine.value}")
                return self.synthesize_with_engine(text, language, fallback_engine, voice_name)
            
            return None
    
    def _synthesize_macos(self, text: str, language: str, voice_name: str = None) -> Optional[str]:
        """Синтез через macOS TTS"""
        if not voice_name:
            # Автоматический выбор голоса для языка
            voices = self.get_voices_for_language(language, TTSEngine.MACOS)
            if voices:
                # Предпочитаем голоса без проблем качества
                good_voices = [v for v in voices if not v.quality_issues]
                selected_voice = good_voices[0] if good_voices else voices[0]
                voice_name = selected_voice.name
            else:
                voice_name = "Alex"  # Fallback голос
        
        try:
            # Создаем временный файл для вывода (AIFF формат для macOS say)
            temp_path = self.config.get_temp_filename(f"macos_tts_{voice_name}", ".aiff")
            
            # Команда say с выводом в файл (без указания формата, по умолчанию AIFF)
            cmd = ['say', '-v', voice_name, '-o', str(temp_path), text]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and temp_path.exists():
                # Конвертируем AIFF в WAV для совместимости
                wav_path = temp_path.with_suffix('.wav')
                try:
                    cmd_convert = [
                        'ffmpeg', '-i', str(temp_path), 
                        '-acodec', 'pcm_s16le', 
                        '-ar', '16000', 
                        '-ac', '1',
                        '-y', str(wav_path)
                    ]
                    
                    convert_result = subprocess.run(cmd_convert, capture_output=True, text=True)
                    
                    if convert_result.returncode == 0 and wav_path.exists():
                        # Удаляем временный AIFF
                        temp_path.unlink(missing_ok=True)
                        self.logger.info(f"✅ macOS TTS успешно (голос: {voice_name})")
                        return str(wav_path)
                    else:
                        self.logger.warning(f"⚠️ Ошибка конвертации AIFF->WAV: {convert_result.stderr}")
                        # Возвращаем оригинальный AIFF файл
                        return str(temp_path)
                
                except Exception as e:
                    self.logger.warning(f"⚠️ Исключение конвертации: {e}")
                    return str(temp_path)
            else:
                self.logger.error(f"❌ Ошибка macOS TTS: {result.stderr}")
                return None
        
        except Exception as e:
            self.logger.error(f"❌ Исключение macOS TTS: {e}")
            return None
    
    def _synthesize_google_tts(self, text: str, language: str, target_duration: float = None) -> Optional[str]:
        """Синтез через Google TTS с возможностью настройки скорости"""
        try:
            # Создаем объект gTTS
            tts = gTTS(text=text, lang=language, slow=False)
            
            # Сохраняем во временный файл
            temp_path = self.config.get_temp_filename(f"google_tts_{language}", ".mp3")
            tts.save(str(temp_path))
            
            # Конвертируем MP3 в WAV через ffmpeg с возможностью изменения скорости
            wav_path = temp_path.with_suffix('.wav')
            
            # Базовая команда конвертации
            cmd = [
                'ffmpeg', '-i', str(temp_path), 
                '-acodec', 'pcm_s16le', 
                '-ar', '16000', 
                '-ac', '1'
            ]
            
            # Если указана целевая длительность, настраиваем скорость
            speed_factor = 1.0
            if target_duration:
                # Сначала конвертируем без изменения скорости для определения оригинальной длительности
                temp_wav = temp_path.with_suffix('.temp.wav')
                temp_cmd = cmd + ['-y', str(temp_wav)]
                temp_result = subprocess.run(temp_cmd, capture_output=True, text=True)
                
                if temp_result.returncode == 0 and temp_wav.exists():
                    # Определяем длительность созданного аудио
                    duration_cmd = [
                        'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1', str(temp_wav)
                    ]
                    duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
                    
                    if duration_result.returncode == 0:
                        try:
                            actual_duration = float(duration_result.stdout.strip())
                            speed_factor = actual_duration / target_duration
                            
                            # Ограничиваем speed_factor разумными пределами
                            speed_factor = max(0.5, min(speed_factor, 2.0))
                            
                            self.logger.info(f"🎵 Google TTS: целевая длительность {target_duration}s, фактическая {actual_duration}s, speed_factor {speed_factor:.2f}")
                            
                        except ValueError:
                            self.logger.warning(f"⚠️ Не удалось определить длительность Google TTS")
                    
                    # Удаляем временный файл
                    temp_wav.unlink(missing_ok=True)
            
            # Применяем speed_factor если он отличается от 1.0
            if abs(speed_factor - 1.0) > 0.05:  # Применяем только если разница больше 5%
                cmd.extend(['-filter:a', f'atempo={speed_factor}'])
                self.logger.info(f"🚀 Применяем ускорение Google TTS: {speed_factor:.2f}x")
            
            cmd.extend(['-y', str(wav_path)])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and wav_path.exists():
                # Удаляем временный MP3
                temp_path.unlink(missing_ok=True)
                speed_info = f" (скорость: {speed_factor:.2f}x)" if abs(speed_factor - 1.0) > 0.05 else ""
                self.logger.info(f"✅ Google TTS успешно (язык: {language}){speed_info}")
                return str(wav_path)
            else:
                self.logger.error(f"❌ Ошибка конвертации Google TTS: {result.stderr}")
                return None
        
        except Exception as e:
            self.logger.error(f"❌ Исключение Google TTS: {e}")
            return None
    
    def _synthesize_elevenlabs(self, text: str, language: str, voice_name: str = None) -> Optional[str]:
        """Синтез через ElevenLabs TTS"""
        self.logger.warning("⚠️ ElevenLabs TTS не реализован в этой версии")
        return None
    
    def _synthesize_ukrainian_tts(self, text: str, language: str) -> Optional[str]:
        """Синтез через Ukrainian TTS (ESPnet)"""
        if language != 'uk':
            self.logger.error("Ukrainian TTS поддерживает только украинский язык")
            return None
        
        try:
            # Проверяем наличие espnet_model_zoo
            import espnet_model_zoo
            from espnet2.bin.tts_inference import Text2Speech
            
            # Загружаем украинскую модель ESPnet
            tag = "espnet/ukrainian_male_glow"
            text2speech = Text2Speech.from_pretrained(
                model_tag=tag,
                vocoder_tag="parallel_wavegan/ljspeech_parallel_wavegan.v1",
                device="cpu",
                speed_control_alpha=1.0,
                noise_scale=0.333,
                noise_scale_dur=0.333
            )
            
            # Синтезируем речь
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
            
            # Генерируем аудио
            wav, sr = text2speech(text)["wav"], text2speech.fs
            
            # Сохраняем в формате WAV
            import soundfile as sf
            sf.write(str(temp_path), wav.cpu().numpy(), sr)
            
            self.logger.info(f"✅ Ukrainian TTS успешно (ESPnet)")
            return str(temp_path)
            
        except ImportError as e:
            self.logger.warning(f"⚠️ ESPnet не установлен, используем fallback: {e}")
            # Fallback на macOS TTS для украинского
            return self._synthesize_macos(text, language, "Milena")
        except Exception as e:
            self.logger.warning(f"⚠️ Ошибка Ukrainian TTS, используем fallback: {e}")
            return self._synthesize_macos(text, language, "Milena")
    
    def _synthesize_radtts_uk(self, text: str, language: str) -> Optional[str]:
        """Синтез через RADTTS Ukrainian"""
        if language != 'uk':
            self.logger.error("RADTTS-UK поддерживает только украинский язык")
            return None
        
        try:
            # Проверяем наличие RADTTS
            import torch
            import numpy as np
            
            # Для RADTTS нужна специальная настройка
            # Это пример интеграции, может потребоваться адаптация под конкретную модель
            
            # Создаем временный файл
            temp_path = self.config.get_temp_filename("radtts_uk", ".wav")
            
            # Здесь должна быть интеграция с RADTTS моделью
            # Пока используем заглушку для демонстрации структуры
            self.logger.warning("⚠️ RADTTS-UK интеграция в разработке")
            
            # Fallback на macOS TTS для украинского
            return self._synthesize_macos(text, language, "Milena")
            
        except ImportError as e:
            self.logger.error(f"❌ RADTTS зависимости не установлены: {e}")
            return None
        except Exception as e:
            self.logger.error(f"❌ Ошибка RADTTS-UK: {e}")
            return None
    
    def _synthesize_poretsky_ru(self, text: str, language: str) -> Optional[str]:
        """Синтез через Poretsky Russian TTS"""
        if language != 'ru':
            self.logger.error("Poretsky TTS поддерживает только русский язык")
            return None
        
        try:
            # Проверяем наличие ru_tts
            import subprocess
            import json
            
            # Создаем временный файл
            temp_path = self.config.get_temp_filename("poretsky_ru", ".wav")
            
            # Команда для Poretsky TTS (примерная структура)
            # Может потребоваться адаптация под конкретную установку
            cmd = [
                'python', '-m', 'ru_tts',
                '--text', text,
                '--output', str(temp_path),
                '--speaker', 'aidar',  # Один из доступных спикеров
                '--sample_rate', '16000'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0 and temp_path.exists():
                self.logger.info(f"✅ Poretsky TTS успешно")
                return str(temp_path)
            else:
                self.logger.warning(f"⚠️ Poretsky TTS недоступен: {result.stderr}")
                # Fallback на macOS TTS
                return self._synthesize_macos(text, language, "Milena")
                
        except ImportError as e:
            self.logger.error(f"❌ Poretsky TTS не установлен: {e}")
            return None
        except subprocess.TimeoutExpired:
            self.logger.error("❌ Poretsky TTS превысил лимит времени")
            return None
        except Exception as e:
            self.logger.error(f"❌ Ошибка Poretsky TTS: {e}")
            return None
    
    def _synthesize_voice_cloning(self, text: str, language: str, speaker_id: str = None,
                                target_duration: float = None) -> Optional[str]:
        """Синтез с клонированием голоса"""
        try:
            self.logger.info(f"🎤 Voice cloning: text='{text[:50]}...', language={language}, speaker_id={speaker_id}")

            # Check if voice cloning is enabled in config
            if not getattr(self.config, 'voice_cloning_enabled', True):
                self.logger.debug("Voice cloning disabled, falling back to Google TTS")
                return self._synthesize_google_tts(text, language, target_duration)
            
            # If no speaker_id provided or no voice profile available, fallback to Google TTS
            if not speaker_id:
                self.logger.debug("No speaker ID provided for voice cloning, using Google TTS")
                return self._synthesize_google_tts(text, language, target_duration)
            
            # Get voice profile for speaker
            voice_profile = self.voice_cloner.get_voice_profile(speaker_id)
            if not voice_profile:
                self.logger.debug(f"No voice profile found for speaker {speaker_id}, using Google TTS")
                return self._synthesize_google_tts(text, language, target_duration)
            
            # First generate base TTS audio using Google TTS
            base_tts_path = self._synthesize_google_tts(text, language, target_duration)
            if not base_tts_path:
                self.logger.error("Failed to generate base TTS for voice cloning")
                return None
            
            # Find reference voice sample for this speaker
            reference_audio = None

            # First check if voice cloner has a profile for this speaker (with audio path)
            voice_profile = self.voice_cloner.get_voice_profile(speaker_id)
            if voice_profile:
                self.logger.debug(f"Found voice profile for {speaker_id}")
                # Voice profile contains characteristics but we need the actual audio file
                # Check temp directory for voice segments (try both temp and src/temp)
                temp_dirs = [Path("temp"), Path("src/temp")]
                for temp_dir in temp_dirs:
                    for temp_file in temp_dir.glob("voice_segment_*.wav"):
                        # This is a simple approach - could be improved with proper mapping
                        reference_audio = str(temp_file)
                        self.logger.debug(f"Using temp voice segment for {speaker_id}: {reference_audio}")
                        break
                    if reference_audio:
                        break

            # Fallback: look for voice sample files in the directory
            if not reference_audio:
                voice_samples_dir = Path("temp/voice_profiles")
                for sample_file in voice_samples_dir.glob(f"{speaker_id}_sample_*.wav"):
                    reference_audio = str(sample_file)
                    break

            if not reference_audio or not Path(reference_audio).exists():
                self.logger.warning(f"No reference audio found for speaker {speaker_id}, using base TTS")
                self.logger.warning(f"Voice profile exists: {voice_profile is not None}")
                self.logger.warning(f"Reference audio path: {reference_audio}")
                return base_tts_path

            self.logger.info(f"🎤 Found reference audio for {speaker_id}: {reference_audio}")
            
            # Generate cloned voice audio
            output_dir = Path("temp")
            output_dir.mkdir(exist_ok=True)
            cloned_audio_path = output_dir / f"voice_cloned_{language}_{hash(text) % 10000}.wav"
            
            # Apply voice cloning
            result = self.voice_cloner.clone_voice(
                tts_audio_path=base_tts_path,
                reference_voice_path=reference_audio,
                output_path=str(cloned_audio_path),
                target_duration=target_duration
            )
            
            if result:
                self.logger.info(f"✅ Voice cloning successful for speaker {speaker_id}: {result}")
                # Clean up base TTS file
                try:
                    Path(base_tts_path).unlink()
                except:
                    pass
                return result
            else:
                self.logger.warning(f"⚠️ Voice cloning failed for speaker {speaker_id}, using base TTS")
                return base_tts_path
                
        except Exception as e:
            self.logger.error(f"❌ Voice cloning error: {e}")
            # Fallback to Google TTS
            return self._synthesize_google_tts(text, language, target_duration)
    
    def _get_fallback_engine(self, failed_engine: TTSEngine, language: str) -> Optional[TTSEngine]:
        """Получить резервный движок"""
        priorities = self.language_engine_priority.get(language.lower(), self.language_engine_priority['default'])
        available = self.get_available_engines()
        
        for engine in priorities:
            if engine != failed_engine and engine in available and engine != TTSEngine.AUTO:
                return engine
        
        return None
    
    def get_engine_comparison(self, language: str) -> Dict[TTSEngine, Dict]:
        """Получить сравнение движков для языка"""
        comparison = {}
        
        for engine in self.get_available_engines():
            if engine == TTSEngine.AUTO:
                continue
                
            engine_info = self.engines_info.get(engine)
            if not engine_info:
                continue
            
            supports_lang = self._engine_supports_language(engine, language)
            voices = self.get_voices_for_language(language, engine)
            
            comparison[engine] = {
                'name': engine_info.name,
                'supports_language': supports_lang,
                'quality_score': engine_info.quality_score,
                'speed_score': engine_info.speed_score,
                'cost': engine_info.cost,
                'available_voices': len(voices),
                'voice_names': [v.name for v in voices[:3]],  # Первые 3 голоса
                'limitations': engine_info.limitations,
                'recommended': engine == self.get_recommended_engine(language)
            }
        
        return comparison
    
    def _log_available_engines(self):
        """Логирование доступных движков"""
        available = self.get_available_engines()
        self.logger.info(f"🔍 Доступные TTS движки: {[e.value for e in available]}")
        
        for engine in available:
            if engine == TTSEngine.AUTO:
                continue
            
            voices_count = sum(len(voices) for voices in self.available_voices.values())
            engine_info = self.engines_info.get(engine)
            if engine_info:
                self.logger.info(f"  🎤 {engine.value}: {engine_info.name} (качество: {engine_info.quality_score}/10, скорость: {engine_info.speed_score}/10)")


# Глобальный экземпляр фабрики
tts_factory = TTSEngineFactory()


if __name__ == "__main__":
    # Тестирование фабрики
    print("=== Тестирование TTSEngineFactory ===")
    
    factory = TTSEngineFactory()
    
    print("\n=== Доступные движки ===")
    for engine in factory.get_available_engines():
        print(f"- {engine.value}")
    
    print("\n=== Рекомендации для языков ===")
    test_languages = ['ru', 'uk', 'en', 'de', 'zh']
    for lang in test_languages:
        recommended = factory.get_recommended_engine(lang)
        print(f"{lang}: {recommended.value}")
    
    print("\n=== Сравнение движков для русского ===")
    comparison = factory.get_engine_comparison('ru')
    for engine, info in comparison.items():
        print(f"{engine.value}: качество={info['quality_score']}, скорость={info['speed_score']}, голосов={info['available_voices']}")
    
    print("\n=== Тест синтеза ===")
    result = factory.synthesize_with_engine("Привет, это тест TTS", "ru", TTSEngine.AUTO)
    if result:
        print(f"✅ Синтез успешен: {result}")
    else:
        print("❌ Синтез не удался")