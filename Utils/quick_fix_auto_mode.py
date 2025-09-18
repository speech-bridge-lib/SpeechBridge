#!/usr/bin/env python3
"""
Быстрые исправления для потенциальных проблем в автоматическом режиме
"""

from pathlib import Path

def apply_quick_fixes():
    """Применяет быстрые исправления для распространенных проблем"""
    
    print("=== ПРИМЕНЕНИЕ БЫСТРЫХ ИСПРАВЛЕНИЙ ===")
    
    video_translator_path = Path("src/video_translator.py")
    if not video_translator_path.exists():
        print("❌ Файл video_translator.py не найден")
        return False
    
    with open(video_translator_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    fixes_applied = []
    
    # Исправление 1: Убедимся что os импортирован
    if 'import os' not in content:
        print("🔧 Исправление 1: Добавляем import os")
        content = content.replace('import ssl', 'import os\nimport ssl')
        fixes_applied.append("Добавлен import os")
    
    # Исправление 2: Добавляем обработку случая когда метод не существует
    old_whisper_call = """result_simple = self.speech_recognizer._transcribe_with_whisper(
                audio_path, 
                self.config.SPEECH_LANGUAGE,
                self.speech_recognizer.current_whisper_model
            )"""
    
    new_whisper_call = """# Пробуем разные варианты вызова _transcribe_with_whisper
            try:
                # Сначала пробуем с 3 параметрами
                result_simple = self.speech_recognizer._transcribe_with_whisper(
                    audio_path, 
                    self.config.SPEECH_LANGUAGE,
                    self.speech_recognizer.current_whisper_model
                )
            except TypeError:
                # Если не работает, пробуем с 2 параметрами
                result_simple = self.speech_recognizer._transcribe_with_whisper(
                    audio_path, 
                    self.config.SPEECH_LANGUAGE
                )"""
    
    if old_whisper_call in content and new_whisper_call not in content:
        print("🔧 Исправление 2: Добавляем fallback для _transcribe_with_whisper")
        content = content.replace(old_whisper_call, new_whisper_call)
        fixes_applied.append("Добавлен fallback для _transcribe_with_whisper")
    
    # Исправление 3: Добавляем дополнительные try-catch в критических местах
    old_try_engine = """result = self._try_engine_without_availability_check(audio_path, engine)
                
                if result and result.strip():"""
    
    new_try_engine = """try:
                    result = self._try_engine_without_availability_check(audio_path, engine)
                except Exception as engine_error:
                    self.logger.warning(f"⚠️ Исключение в _try_engine_without_availability_check для {engine}: {engine_error}")
                    result = ""
                
                if result and result.strip():"""
    
    if old_try_engine in content and new_try_engine not in content:
        print("🔧 Исправление 3: Добавляем дополнительный try-catch для движков")
        content = content.replace(old_try_engine, new_try_engine)
        fixes_applied.append("Добавлен дополнительный try-catch для движков")
    
    # Исправление 4: Добавляем защиту от None в конфиге
    old_config_access = "self.config.SPEECH_LANGUAGE"
    new_config_access = "getattr(self.config, 'SPEECH_LANGUAGE', 'en-US')"
    
    if old_config_access in content and content.count(old_config_access) > content.count(new_config_access):
        print("🔧 Исправление 4: Добавляем защиту от отсутствующих конфигов")
        content = content.replace(old_config_access, new_config_access)
        fixes_applied.append("Добавлена защита от отсутствующих конфигов")
    
    # Сохраняем исправления
    if fixes_applied:
        with open(video_translator_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"\n✅ Применено {len(fixes_applied)} исправлений:")
        for i, fix in enumerate(fixes_applied, 1):
            print(f"   {i}. {fix}")
        
        print(f"\n💾 Файл {video_translator_path} обновлен")
        return True
    else:
        print("ℹ️ Никаких дополнительных исправлений не требуется")
        return True

if __name__ == "__main__":
    success = apply_quick_fixes()
    if success:
        print("\n🎯 РЕКОМЕНДАЦИИ ДЛЯ ДАЛЬНЕЙШЕЙ ДИАГНОСТИКИ:")
        print("1. Попробуйте запустить ваш код еще раз")
        print("2. Если ошибка повторяется, пожалуйста, скопируйте:")
        print("   - Полный текст ошибки")
        print("   - Команду/параметры которые вы используете")
        print("   - Любые логи перед ошибкой")
        print("3. Это поможет точно определить и исправить проблему")
    else:
        print("\n❌ Не удалось применить исправления")
    
    exit(0 if success else 1)