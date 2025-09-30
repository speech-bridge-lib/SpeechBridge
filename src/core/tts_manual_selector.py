#!/usr/bin/env python3
"""
TTSManualSelector: Система ручного выбора TTS движков для пользователя
Позволяет пользователю вручную выбирать TTS движок для каждого языка
"""

import logging
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import config
from core.tts_engine_factory import TTSEngineFactory, TTSEngine, VoiceInfo


@dataclass
class UserTTSPreference:
    """Пользовательские предпочтения TTS"""
    language: str
    preferred_engine: TTSEngine
    preferred_voice: Optional[str] = None
    fallback_engine: Optional[TTSEngine] = None
    enabled: bool = True
    notes: str = ""


class TTSManualSelector:
    """Система ручного выбора TTS движков"""
    
    def __init__(self):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.tts_factory = TTSEngineFactory()
        
        # Файл для сохранения пользовательских настроек
        self.preferences_file = self.config.LOGS_FOLDER / "tts_user_preferences.json"
        
        # Загружаем пользовательские настройки
        self.user_preferences: Dict[str, UserTTSPreference] = self._load_user_preferences()
        
        self.logger.info("🎛️ TTSManualSelector инициализирован")
    
    def get_available_engines_for_language(self, language: str) -> List[Dict]:
        """Получить доступные движки для языка с подробной информацией"""
        available_engines = []
        
        for engine in self.tts_factory.get_available_engines():
            if engine == TTSEngine.AUTO:
                continue
            
            if self.tts_factory._engine_supports_language(engine, language):
                engine_info = self.tts_factory.engines_info.get(engine)
                voices = self.tts_factory.get_voices_for_language(language, engine)
                
                engine_data = {
                    'engine': engine.value,
                    'name': engine_info.name if engine_info else engine.value,
                    'description': engine_info.description if engine_info else "",
                    'quality_score': engine_info.quality_score if engine_info else 5,
                    'speed_score': engine_info.speed_score if engine_info else 5,
                    'cost': engine_info.cost if engine_info else "unknown",
                    'limitations': engine_info.limitations if engine_info else "",
                    'voices': [
                        {
                            'name': voice.name,
                            'description': voice.description,
                            'quality_issues': voice.quality_issues
                        }
                        for voice in voices
                    ],
                    'is_recommended': engine == self.tts_factory.get_recommended_engine(language),
                    'is_currently_selected': self._is_engine_selected_for_language(engine, language)
                }
                
                available_engines.append(engine_data)
        
        # Сортируем по рекомендации и качеству
        available_engines.sort(key=lambda x: (not x['is_recommended'], -x['quality_score']))
        
        return available_engines
    
    def set_user_preference(
        self, 
        language: str, 
        engine: TTSEngine, 
        voice: str = None,
        fallback_engine: TTSEngine = None,
        notes: str = ""
    ) -> bool:
        """Установить пользовательские предпочтения для языка"""
        
        # Проверяем, поддерживает ли движок этот язык
        if not self.tts_factory._engine_supports_language(engine, language):
            self.logger.error(f"❌ Движок {engine.value} не поддерживает язык {language}")
            return False
        
        # Проверяем доступность движка
        if engine not in self.tts_factory.get_available_engines():
            self.logger.error(f"❌ Движок {engine.value} недоступен")
            return False
        
        # Создаем настройку
        preference = UserTTSPreference(
            language=language,
            preferred_engine=engine,
            preferred_voice=voice,
            fallback_engine=fallback_engine,
            enabled=True,
            notes=notes
        )
        
        self.user_preferences[language] = preference
        
        # Сохраняем настройки
        if self._save_user_preferences():
            self.logger.info(f"✅ Настройка TTS для {language}: {engine.value}" + 
                           (f" (голос: {voice})" if voice else ""))
            return True
        else:
            self.logger.error(f"❌ Ошибка сохранения настроек TTS для {language}")
            return False
    
    def get_user_preference(self, language: str) -> Optional[UserTTSPreference]:
        """Получить пользовательские настройки для языка"""
        return self.user_preferences.get(language)
    
    def get_effective_engine_for_language(self, language: str) -> TTSEngine:
        """Получить эффективный движок для языка (с учетом пользовательских настроек)"""
        preference = self.get_user_preference(language)
        
        if preference and preference.enabled:
            # Проверяем, что выбранный движок всё еще доступен
            if preference.preferred_engine in self.tts_factory.get_available_engines():
                if self.tts_factory._engine_supports_language(preference.preferred_engine, language):
                    return preference.preferred_engine
                else:
                    self.logger.warning(f"⚠️ Выбранный движок {preference.preferred_engine.value} больше не поддерживает {language}")
            else:
                self.logger.warning(f"⚠️ Выбранный движок {preference.preferred_engine.value} недоступен")
            
            # Пробуем fallback движок
            if preference.fallback_engine:
                if (preference.fallback_engine in self.tts_factory.get_available_engines() and
                    self.tts_factory._engine_supports_language(preference.fallback_engine, language)):
                    self.logger.info(f"🔄 Используем fallback движок {preference.fallback_engine.value} для {language}")
                    return preference.fallback_engine
        
        # Используем автоматический выбор
        return self.tts_factory.get_recommended_engine(language)
    
    def get_effective_voice_for_language(self, language: str) -> Optional[str]:
        """Получить эффективный голос для языка"""
        preference = self.get_user_preference(language)
        
        if preference and preference.enabled and preference.preferred_voice:
            # Проверяем, что голос доступен для выбранного движка
            voices = self.tts_factory.get_voices_for_language(language, preference.preferred_engine)
            voice_names = [v.name for v in voices]
            
            if preference.preferred_voice in voice_names:
                return preference.preferred_voice
            else:
                self.logger.warning(f"⚠️ Выбранный голос {preference.preferred_voice} недоступен для {language}")
        
        return None
    
    def remove_user_preference(self, language: str) -> bool:
        """Удалить пользовательские настройки для языка"""
        if language in self.user_preferences:
            del self.user_preferences[language]
            
            if self._save_user_preferences():
                self.logger.info(f"🗑️ Настройки TTS для {language} удалены (используется автоматический выбор)")
                return True
            else:
                self.logger.error(f"❌ Ошибка удаления настроек TTS для {language}")
                return False
        else:
            self.logger.warning(f"⚠️ Настройки TTS для {language} не найдены")
            return True
    
    def toggle_preference(self, language: str, enabled: bool) -> bool:
        """Включить/выключить пользовательские настройки для языка"""
        preference = self.get_user_preference(language)
        
        if preference:
            preference.enabled = enabled
            
            if self._save_user_preferences():
                status = "включены" if enabled else "выключены"
                self.logger.info(f"🔄 Настройки TTS для {language} {status}")
                return True
            else:
                self.logger.error(f"❌ Ошибка изменения настроек TTS для {language}")
                return False
        else:
            self.logger.warning(f"⚠️ Настройки TTS для {language} не найдены")
            return False
    
    def get_all_preferences(self) -> Dict[str, Dict]:
        """Получить все пользовательские настройки"""
        result = {}
        
        for language, preference in self.user_preferences.items():
            result[language] = {
                'language': preference.language,
                'preferred_engine': preference.preferred_engine.value,
                'preferred_voice': preference.preferred_voice,
                'fallback_engine': preference.fallback_engine.value if preference.fallback_engine else None,
                'enabled': preference.enabled,
                'notes': preference.notes,
                'effective_engine': self.get_effective_engine_for_language(language).value,
                'effective_voice': self.get_effective_voice_for_language(language)
            }
        
        return result
    
    def get_languages_with_preferences(self) -> List[str]:
        """Получить список языков с пользовательскими настройками"""
        return list(self.user_preferences.keys())
    
    def reset_all_preferences(self) -> bool:
        """Сбросить все пользовательские настройки"""
        self.user_preferences.clear()
        
        if self._save_user_preferences():
            self.logger.info("🔄 Все пользовательские настройки TTS сброшены")
            return True
        else:
            self.logger.error("❌ Ошибка сброса настроек TTS")
            return False
    
    def import_preferences_from_dict(self, preferences_dict: Dict) -> bool:
        """Импорт настроек из словаря"""
        try:
            for language, pref_data in preferences_dict.items():
                engine = TTSEngine(pref_data['preferred_engine'])
                fallback = TTSEngine(pref_data['fallback_engine']) if pref_data.get('fallback_engine') else None
                
                preference = UserTTSPreference(
                    language=language,
                    preferred_engine=engine,
                    preferred_voice=pref_data.get('preferred_voice'),
                    fallback_engine=fallback,
                    enabled=pref_data.get('enabled', True),
                    notes=pref_data.get('notes', "")
                )
                
                self.user_preferences[language] = preference
            
            if self._save_user_preferences():
                self.logger.info(f"📥 Импортировано настроек TTS: {len(preferences_dict)}")
                return True
            else:
                self.logger.error("❌ Ошибка сохранения импортированных настроек")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Ошибка импорта настроек: {e}")
            return False
    
    def _is_engine_selected_for_language(self, engine: TTSEngine, language: str) -> bool:
        """Проверить, выбран ли движок для языка"""
        preference = self.get_user_preference(language)
        if preference and preference.enabled:
            return preference.preferred_engine == engine
        else:
            return self.tts_factory.get_recommended_engine(language) == engine
    
    def _load_user_preferences(self) -> Dict[str, UserTTSPreference]:
        """Загрузить пользовательские настройки из файла"""
        preferences = {}
        
        if self.preferences_file.exists():
            try:
                with open(self.preferences_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for language, pref_data in data.items():
                    try:
                        engine = TTSEngine(pref_data['preferred_engine'])
                        fallback = TTSEngine(pref_data['fallback_engine']) if pref_data.get('fallback_engine') else None
                        
                        preference = UserTTSPreference(
                            language=language,
                            preferred_engine=engine,
                            preferred_voice=pref_data.get('preferred_voice'),
                            fallback_engine=fallback,
                            enabled=pref_data.get('enabled', True),
                            notes=pref_data.get('notes', "")
                        )
                        
                        preferences[language] = preference
                        
                    except (ValueError, KeyError) as e:
                        self.logger.warning(f"⚠️ Пропускаем некорректную настройку для {language}: {e}")
                
                self.logger.info(f"📂 Загружено пользовательских настроек TTS: {len(preferences)}")
                
            except Exception as e:
                self.logger.error(f"❌ Ошибка загрузки настроек TTS: {e}")
        
        return preferences
    
    def _save_user_preferences(self) -> bool:
        """Сохранить пользовательские настройки в файл"""
        try:
            # Подготавливаем данные для JSON
            data = {}
            for language, preference in self.user_preferences.items():
                data[language] = {
                    'preferred_engine': preference.preferred_engine.value,
                    'preferred_voice': preference.preferred_voice,
                    'fallback_engine': preference.fallback_engine.value if preference.fallback_engine else None,
                    'enabled': preference.enabled,
                    'notes': preference.notes
                }
            
            # Создаем директорию если не существует
            self.preferences_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Сохраняем в файл
            with open(self.preferences_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка сохранения настроек TTS: {e}")
            return False
    
    def get_selection_interface_data(self, language: str) -> Dict:
        """Получить данные для интерфейса выбора TTS"""
        # Безопасная сериализация user preferences с TTSEngine объектами
        current_preference = None
        if language in self.user_preferences:
            pref = self.user_preferences[language]
            current_preference = {
                'language': pref.language,
                'preferred_engine': pref.preferred_engine.value,
                'preferred_voice': pref.preferred_voice,
                'fallback_engine': pref.fallback_engine.value if pref.fallback_engine else None,
                'enabled': pref.enabled,
                'notes': pref.notes
            }
        
        return {
            'language': language,
            'available_engines': self.get_available_engines_for_language(language),
            'current_preference': current_preference,
            'effective_engine': self.get_effective_engine_for_language(language).value,
            'effective_voice': self.get_effective_voice_for_language(language),
            'recommended_engine': self.tts_factory.get_recommended_engine(language).value
        }
    
    def generate_selection_summary(self) -> str:
        """Создать текстовую сводку настроек TTS"""
        summary = []
        summary.append("🎛️ === НАСТРОЙКИ TTS ДВИЖКОВ ===")
        
        if not self.user_preferences:
            summary.append("📋 Пользовательские настройки не заданы (используется автоматический выбор)")
            return "\n".join(summary)
        
        summary.append(f"📊 Всего настроенных языков: {len(self.user_preferences)}")
        summary.append("")
        
        for language in sorted(self.user_preferences.keys()):
            preference = self.user_preferences[language]
            effective_engine = self.get_effective_engine_for_language(language)
            effective_voice = self.get_effective_voice_for_language(language)
            
            status = "🟢" if preference.enabled else "🔴"
            summary.append(f"{status} {language.upper()}:")
            summary.append(f"  📍 Выбрано: {preference.preferred_engine.value}")
            if preference.preferred_voice:
                summary.append(f"  🎤 Голос: {preference.preferred_voice}")
            if preference.fallback_engine:
                summary.append(f"  🔄 Fallback: {preference.fallback_engine.value}")
            summary.append(f"  ✅ Используется: {effective_engine.value}")
            if effective_voice:
                summary.append(f"  🎵 Активный голос: {effective_voice}")
            if preference.notes:
                summary.append(f"  📝 Заметки: {preference.notes}")
            summary.append("")
        
        return "\n".join(summary)


# Глобальный экземпляр селектора
tts_manual_selector = TTSManualSelector()


if __name__ == "__main__":
    # Тестирование
    print("=== Тестирование TTSManualSelector ===")
    
    selector = TTSManualSelector()
    
    print("\n=== Доступные движки для русского ===")
    ru_engines = selector.get_available_engines_for_language('ru')
    for engine in ru_engines:
        recommended = "⭐" if engine['is_recommended'] else ""
        selected = "✅" if engine['is_currently_selected'] else ""
        print(f"{recommended}{selected} {engine['name']}: качество={engine['quality_score']}/10")
    
    print("\n=== Устанавливаем пользовательские настройки ===")
    selector.set_user_preference('ru', TTSEngine.MACOS, 'Milena', TTSEngine.GOOGLE_TTS, "Предпочтение пользователя")
    selector.set_user_preference('uk', TTSEngine.GOOGLE_TTS, None, TTSEngine.MACOS, "Google TTS лучше для украинского")
    
    print("\n=== Эффективные движки ===")
    for lang in ['ru', 'uk', 'en']:
        effective = selector.get_effective_engine_for_language(lang)
        voice = selector.get_effective_voice_for_language(lang)
        print(f"{lang}: {effective.value}" + (f" (голос: {voice})" if voice else ""))
    
    print("\n=== Сводка настроек ===")
    print(selector.generate_selection_summary())