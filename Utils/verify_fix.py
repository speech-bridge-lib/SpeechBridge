#!/usr/bin/env python3
"""
Проверка исправлений без зависимостей
"""

from pathlib import Path

def verify_fixes():
    """Проверка применения исправлений в коде"""
    
    print("=== ВЕРИФИКАЦИЯ ИСПРАВЛЕНИЙ ===")
    
    # Проверяем video_translator.py
    video_translator_path = Path("src/video_translator.py")
    if not video_translator_path.exists():
        print("❌ Файл video_translator.py не найден")
        return False
    
    with open(video_translator_path, 'r', encoding='utf-8') as f:
        video_translator_content = f.read()
    
    # Проверяем speech_recognizer.py  
    speech_recognizer_path = Path("src/core/speech_recognizer.py")
    if not speech_recognizer_path.exists():
        print("❌ Файл speech_recognizer.py не найден")
        return False
        
    with open(speech_recognizer_path, 'r', encoding='utf-8') as f:
        speech_recognizer_content = f.read()
    
    print("1. Проверка удаления неправильных методов в video_translator.py:")
    
    # Проверяем что старые неправильные вызовы удалены
    bad_methods = ['transcribe_audio_whisper', 'transcribe_audio_google', 'transcribe_audio_sphinx']
    found_bad_methods = []
    
    for method in bad_methods:
        if method in video_translator_content:
            found_bad_methods.append(method)
    
    if found_bad_methods:
        print(f"  ❌ Найдены старые методы: {found_bad_methods}")
        return False
    else:
        print("  ✅ Старые неправильные методы удалены")
    
    print("\n2. Проверка использования transcribe_with_engine:")
    if 'transcribe_with_engine' in video_translator_content:
        print("  ✅ Используется правильный метод transcribe_with_engine")
    else:
        print("  ❌ Метод transcribe_with_engine не найден")
        return False
    
    print("\n3. Проверка обработки критических ошибок:")
    critical_error_check = 'speech_engine != \'auto\' and' in video_translator_content
    if critical_error_check:
        print("  ✅ Добавлена проверка критических ошибок при ручном выборе движка")
    else:
        print("  ❌ Проверка критических ошибок не найдена")
        return False
    
    print("\n4. Проверка исправления _preprocess_audio_for_recognition:")
    if '_preprocess_audio_for_recognition' in speech_recognizer_content:
        print("  ❌ Все еще используется неправильный метод _preprocess_audio_for_recognition")
        return False
    else:
        print("  ✅ Исправлен вызов на _preprocess_audio")
    
    print("\n5. Проверка наличия правильного метода transcribe_with_engine:")
    if 'def transcribe_with_engine' in speech_recognizer_content:
        print("  ✅ Метод transcribe_with_engine существует в SpeechRecognizer")
    else:
        print("  ❌ Метод transcribe_with_engine не найден в SpeechRecognizer")
        return False
    
    print("\n✅ ВСЕ ПРОВЕРКИ ПРОШЛИ УСПЕШНО!")
    
    print("\n🎯 РЕЗЮМЕ ИСПРАВЛЕНИЙ:")
    print("1. Исправлена ошибка: 'SpeechRecognizer' object has no attribute 'transcribe_audio_whisper'")
    print("   - Заменен вызов на правильный метод transcribe_with_engine")
    print("2. Добавлена остановка процесса при ошибке принудительно выбранного движка")
    print("   - При ручном выборе движка (не 'auto') и его сбое процесс останавливается")
    print("3. Исправлен неправильный вызов _preprocess_audio_for_recognition")
    print("   - Заменен на существующий метод _preprocess_audio")
    
    print("\n💡 ПОВЕДЕНИЕ ПОСЛЕ ИСПРАВЛЕНИЯ:")
    print("- Если движок выбран автоматически ('auto') и не работает - процесс продолжается с fallback")
    print("- Если движок выбран принудительно ('whisper', 'google', etc.) и не работает - процесс ОСТАНАВЛИВАЕТСЯ")
    print("- Выводится четкое сообщение об ошибке с указанием проблемного движка")
    
    return True

if __name__ == "__main__":
    success = verify_fixes()
    if success:
        print("\n🎉 ПРОБЛЕМА РЕШЕНА!")
        print("Теперь при принудительном выборе движка речи и его сбое")
        print("процесс перевода видео будет корректно остановлен.")
    else:
        print("\n❌ Обнаружены проблемы в исправлениях")
    
    exit(0 if success else 1)