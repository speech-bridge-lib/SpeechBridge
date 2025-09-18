"""
DeepL переводчик для Video-Translator
Использует только DeepL API для высококачественного перевода
"""

import logging
import os
import re
# Импортируем config чтобы загрузить .env файл
from config import config

# Глобальные переменные
TRANSLATOR_TYPE = 'deepl'
translator_instance = None
_last_translation = None


def _init_deepl():
    """Инициализирует DeepL переводчик"""
    try:
        deepl_key = os.getenv('DEEPL_API_KEY')
        if not deepl_key:
            print("❌ DeepL: API ключ не найден в переменной DEEPL_API_KEY")
            print("   Добавьте DEEPL_API_KEY=your_key в .env файл")
            return None
            
        import deepl
        translator = deepl.Translator(deepl_key)
        
        # Тестовый перевод
        result = translator.translate_text("hello", target_lang="RU")
        if result and result.text and result.text != "hello":
            print(f"✅ DeepL инициализирован: 'hello' -> '{result.text}' (премиум качество)")
            return translator
        else:
            print("❌ DeepL: неожиданный результат тестирования")
            return None
    except ImportError:
        print("❌ DeepL: библиотека 'deepl' не установлена")
        print("   Установите: pip install deepl")
        return None
    except Exception as e:
        print(f"❌ DeepL инициализация ошибка: {e}")
        return None


# Инициализация ТОЛЬКО DeepL переводчика
print("🚀 Инициализация DeepL переводчика...")

translator_instance = _init_deepl()
if not translator_instance:
    print("💥 КРИТИЧЕСКАЯ ОШИБКА: DeepL переводчик недоступен!")
    print("   Приложение не может работать без переводчика.")

print("✅ Инициализация переводчика завершена")


def split_text_into_sentences(text, max_length=400):
    """
    Разбивает длинный текст на предложения для лучшего перевода
    
    Args:
        text: исходный текст
        max_length: максимальная длина одного сегмента
        
    Returns:
        List[str]: список предложений/сегментов
    """
    if len(text) <= max_length:
        return [text]
    
    # Сначала пробуем разбить по предложениям
    sentences = re.split(r'[.!?]+\s+', text)
    
    # Если получили только одно большое предложение, разбиваем по запятым и другим знакам
    if len(sentences) == 1 and len(sentences[0]) > max_length:
        sentences = re.split(r'[,;]\s+|\s+and\s+|\s+but\s+|\s+or\s+|\s+so\s+|\s+because\s+', text)
    
    # Объединяем короткие фрагменты
    result = []
    current_segment = ""
    
    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # Если добавление этого предложения превысит лимит
        if len(current_segment) + len(sentence) + 2 > max_length:
            if current_segment:
                result.append(current_segment.strip())
                current_segment = sentence
            else:
                # Предложение само по себе слишком длинное - принудительно разбиваем по словам
                words = sentence.split()
                temp_segment = ""
                for word in words:
                    if len(temp_segment) + len(word) + 1 <= max_length:
                        temp_segment += (" " + word) if temp_segment else word
                    else:
                        if temp_segment:
                            result.append(temp_segment.strip())
                        temp_segment = word
                if temp_segment:
                    current_segment = temp_segment
        else:
            if current_segment:
                current_segment += " " + sentence
            else:
                current_segment = sentence
    
    if current_segment:
        result.append(current_segment.strip())
    
    return result


def translate_text(text, src_lang='en', dest_lang='ru'):
    """Перевод текста через DeepL API"""
    global _last_translation

    if not text or not text.strip():
        return ""

    if not translator_instance:
        logging.error("DeepL переводчик не инициализирован")
        return f"[ОШИБКА ПЕРЕВОДА: {text}]"

    try:
        # DeepL использует коды языков в верхнем регистре
        target_lang = dest_lang.upper()
        if target_lang == 'RU':
            target_lang = 'RU'
        elif target_lang == 'EN':
            target_lang = 'EN-US'
        
        # Разбиваем длинный текст на сегменты для лучшего перевода
        text_segments = split_text_into_sentences(text, max_length=400)
        
        if len(text_segments) == 1:
            # Короткий текст - переводим как есть
            result = translator_instance.translate_text(text, target_lang=target_lang)
            translated = result.text
        else:
            # Длинный текст - переводим по частям
            logging.info(f"DeepL: разбиваем текст на {len(text_segments)} сегментов для перевода")
            translated_segments = []
            
            for i, segment in enumerate(text_segments):
                try:
                    result = translator_instance.translate_text(segment, target_lang=target_lang)
                    translated_segments.append(result.text)
                    logging.debug(f"DeepL: сегмент {i+1}/{len(text_segments)} переведен")
                except Exception as e:
                    logging.error(f"DeepL: ошибка перевода сегмента {i+1}: {e}")
                    translated_segments.append(f"[ОШИБКА СЕГМЕНТА {i+1}: {segment}]")
            
            translated = " ".join(translated_segments)

        _last_translation = {'original': text, 'translated': translated, 'method': 'deepl'}
        return translated

    except Exception as e:
        logging.error(f"DeepL перевод ошибка: {e}")
        return f"[ОШИБКА ПЕРЕВОДА: {text}]"


def get_translator_status():
    """Получить статус DeepL переводчика"""
    return {
        'type': 'deepl',
        'working': translator_instance is not None,
        'description': 'DeepL API - премиум качество перевода' if translator_instance else 'DeepL недоступен',
        'last_translation': _last_translation
    }