#!/usr/bin/env python3
"""
Простой интерактивный селектор TTS движков
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from core.tts_manual_selector import tts_manual_selector
from core.tts_engine_factory import TTSEngine

def show_available_engines():
    """Показать доступные движки"""
    print("🎤 === ДОСТУПНЫЕ TTS ДВИЖКИ ===")
    
    engines = tts_manual_selector.tts_factory.get_available_engines()
    for i, engine in enumerate(engines, 1):
        if engine.value == 'auto':
            continue
        
        engine_info = tts_manual_selector.tts_factory.engines_info.get(engine)
        if engine_info:
            print(f"{i}. {engine_info.name}")
            print(f"   Качество: {engine_info.quality_score}/10")
            print(f"   Скорость: {engine_info.speed_score}/10") 
            print(f"   Стоимость: {engine_info.cost}")
            print(f"   Описание: {engine_info.description}")
            print()

def show_language_engines(language):
    """Показать движки для языка"""
    print(f"🌍 === ДВИЖКИ ДЛЯ {language.upper()} ===")
    
    engines = tts_manual_selector.get_available_engines_for_language(language)
    for i, engine in enumerate(engines, 1):
        recommended = "⭐ РЕКОМЕНДУЕМЫЙ" if engine['is_recommended'] else ""
        selected = "✅ ВЫБРАН" if engine['is_currently_selected'] else ""
        
        print(f"{i}. {engine['name']} {recommended} {selected}")
        print(f"   Качество: {engine['quality_score']}/10")
        print(f"   Скорость: {engine['speed_score']}/10")
        print(f"   Стоимость: {engine['cost']}")
        print(f"   Голосов: {len(engine['voices'])}")
        if engine['voices']:
            voices = [v['name'] for v in engine['voices'][:3]]
            print(f"   Примеры голосов: {', '.join(voices)}")
        print()

def show_current_preferences():
    """Показать текущие настройки"""
    print("📋 === ТЕКУЩИЕ НАСТРОЙКИ ===")
    
    preferences = tts_manual_selector.get_all_preferences()
    if not preferences:
        print("   Пользовательские настройки не заданы")
        print("   Используется автоматический выбор")
        return
    
    for lang, pref in preferences.items():
        print(f"🌍 {lang.upper()}:")
        print(f"   Выбрано: {pref['preferred_engine']}")
        if pref['preferred_voice']:
            print(f"   Голос: {pref['preferred_voice']}")
        if pref['fallback_engine']:
            print(f"   Резервный: {pref['fallback_engine']}")
        print(f"   Эффективный: {pref['effective_engine']}")
        print(f"   Состояние: {'🟢 Включен' if pref['enabled'] else '🔴 Выключен'}")
        if pref['notes']:
            print(f"   Заметки: {pref['notes']}")
        print()

def set_preference():
    """Установить настройки для языка"""
    print("\n⚙️ === НАСТРОЙКА TTS ===")
    
    # Выбор языка
    languages = ['ru', 'uk', 'en', 'de', 'fr', 'es', 'it', 'pt', 'zh', 'ja']
    print("Доступные языки:")
    for i, lang in enumerate(languages, 1):
        print(f"{i}. {lang}")
    
    try:
        lang_choice = input("\nВыберите язык (номер): ").strip()
        if not lang_choice or not lang_choice.isdigit():
            return
        
        lang_idx = int(lang_choice) - 1
        if lang_idx < 0 or lang_idx >= len(languages):
            print("❌ Неверный выбор языка")
            return
        
        language = languages[lang_idx]
        print(f"\n🌍 Выбран язык: {language}")
        
        # Показать доступные движки для языка
        show_language_engines(language)
        
        # Выбор движка
        engines = tts_manual_selector.get_available_engines_for_language(language)
        if not engines:
            print("❌ Нет доступных движков для этого языка")
            return
        
        print("Выберите TTS движок:")
        for i, engine in enumerate(engines, 1):
            recommended = " (рекомендуемый)" if engine['is_recommended'] else ""
            print(f"{i}. {engine['name']}{recommended}")
        
        engine_choice = input("Выберите движок (номер): ").strip()
        if not engine_choice or not engine_choice.isdigit():
            return
        
        engine_idx = int(engine_choice) - 1
        if engine_idx < 0 or engine_idx >= len(engines):
            print("❌ Неверный выбор движка")
            return
        
        selected_engine = engines[engine_idx]
        engine_enum = TTSEngine(selected_engine['engine']['value'])
        
        # Выбор голоса (опционально)
        voice = None
        if selected_engine['voices']:
            print(f"\nДоступные голоса для {selected_engine['name']}:")
            print("0. Автоматический выбор")
            for i, v in enumerate(selected_engine['voices'], 1):
                quality_warn = " ⚠️ (проблемы качества)" if v['quality_issues'] else ""
                print(f"{i}. {v['name']}{quality_warn}")
            
            voice_choice = input("Выберите голос (номер, 0 для авто): ").strip()
            if voice_choice and voice_choice.isdigit():
                voice_idx = int(voice_choice)
                if voice_idx > 0 and voice_idx <= len(selected_engine['voices']):
                    voice = selected_engine['voices'][voice_idx - 1]['name']
        
        # Выбор fallback движка
        fallback_engine = None
        print(f"\nВыберите резервный движок (опционально):")
        print("0. Без резервного")
        fallback_engines = [e for e in engines if e != selected_engine]
        for i, engine in enumerate(fallback_engines, 1):
            print(f"{i}. {engine['name']}")
        
        fallback_choice = input("Выберите резервный движок (номер, 0 для пропуска): ").strip()
        if fallback_choice and fallback_choice.isdigit():
            fallback_idx = int(fallback_choice)
            if fallback_idx > 0 and fallback_idx <= len(fallback_engines):
                fallback_engine = TTSEngine(fallback_engines[fallback_idx - 1]['engine']['value'])
        
        # Заметки
        notes = input("Заметки (опционально): ").strip()
        
        # Сохранение настроек
        print("\n💾 Сохранение настроек...")
        success = tts_manual_selector.set_user_preference(
            language=language,
            engine=engine_enum,
            voice=voice,
            fallback_engine=fallback_engine,
            notes=notes
        )
        
        if success:
            print("✅ Настройки сохранены успешно!")
            
            # Показать эффективные настройки
            effective_engine = tts_manual_selector.get_effective_engine_for_language(language)
            effective_voice = tts_manual_selector.get_effective_voice_for_language(language)
            
            print(f"\n🎯 Эффективные настройки для {language}:")
            print(f"   Движок: {effective_engine.value}")
            if effective_voice:
                print(f"   Голос: {effective_voice}")
        else:
            print("❌ Ошибка сохранения настроек")
    
    except KeyboardInterrupt:
        print("\n❌ Отменено пользователем")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

def test_tts():
    """Тестировать TTS"""
    print("\n🎤 === ТЕСТ TTS ===")
    
    language = input("Язык для теста (ru/uk/en): ").strip() or 'ru'
    text = input(f"Текст для синтеза [{f'Тест TTS для {language}'}]: ").strip()
    if not text:
        text = f"Тест TTS для {language}"
    
    print(f"\n🔄 Синтез: '{text}' на языке {language}")
    
    # Получаем эффективный движок
    effective_engine = tts_manual_selector.get_effective_engine_for_language(language)
    effective_voice = tts_manual_selector.get_effective_voice_for_language(language)
    
    print(f"🎛️ Используется: {effective_engine.value}" + 
          (f" (голос: {effective_voice})" if effective_voice else ""))
    
    # Выполняем синтез
    result = tts_manual_selector.tts_factory.synthesize_with_engine(
        text=text,
        language=language,
        engine=effective_engine,
        voice_name=effective_voice
    )
    
    if result:
        print(f"✅ Синтез успешен!")
        print(f"📁 Файл: {result}")
    else:
        print("❌ Синтез не удался")

def delete_preference():
    """Удалить настройки для языка"""
    print("\n🗑️ === УДАЛЕНИЕ НАСТРОЕК ===")
    
    preferences = tts_manual_selector.get_all_preferences()
    if not preferences:
        print("❌ Нет настроек для удаления")
        return
    
    print("Языки с настройками:")
    langs = list(preferences.keys())
    for i, lang in enumerate(langs, 1):
        print(f"{i}. {lang} ({preferences[lang]['preferred_engine']})")
    
    choice = input("Выберите язык для удаления (номер): ").strip()
    if not choice or not choice.isdigit():
        return
    
    idx = int(choice) - 1
    if idx < 0 or idx >= len(langs):
        print("❌ Неверный выбор")
        return
    
    language = langs[idx]
    confirm = input(f"Удалить настройки для {language}? (y/N): ").strip().lower()
    if confirm == 'y':
        success = tts_manual_selector.remove_user_preference(language)
        if success:
            print(f"✅ Настройки для {language} удалены")
        else:
            print(f"❌ Ошибка удаления настроек для {language}")

def main():
    """Главное меню"""
    print("🎛️ === TTS ENGINE MANUAL SELECTOR ===")
    print("Система ручного выбора TTS движков")
    print()
    
    while True:
        print("=== ГЛАВНОЕ МЕНЮ ===")
        print("1. 📊 Показать доступные движки")
        print("2. 🌍 Показать движки для языка")
        print("3. ⚙️ Настроить TTS для языка")
        print("4. 📋 Показать текущие настройки")
        print("5. 🎤 Тестировать TTS")
        print("6. 🗑️ Удалить настройки для языка")
        print("7. 🔥 Сбросить все настройки")
        print("0. 🚪 Выход")
        print()
        
        try:
            choice = input("Выберите действие: ").strip()
            
            if choice == '1':
                show_available_engines()
            elif choice == '2':
                language = input("Введите код языка (ru/uk/en): ").strip()
                if language:
                    show_language_engines(language)
            elif choice == '3':
                set_preference()
            elif choice == '4':
                show_current_preferences()
            elif choice == '5':
                test_tts()
            elif choice == '6':
                delete_preference()
            elif choice == '7':
                confirm = input("Сбросить ВСЕ настройки? (y/N): ").strip().lower()
                if confirm == 'y':
                    success = tts_manual_selector.reset_all_preferences()
                    if success:
                        print("✅ Все настройки сброшены")
                    else:
                        print("❌ Ошибка сброса настроек")
            elif choice == '0':
                print("👋 До свидания!")
                break
            else:
                print("❌ Неверный выбор")
            
            print()
            
        except KeyboardInterrupt:
            print("\n👋 До свидания!")
            break
        except Exception as e:
            print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    main()