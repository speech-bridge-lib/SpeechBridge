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

# Поддерживаемые языки DeepL API (обновлено 2025)
DEEPL_SOURCE_LANGUAGES = {
    'ar': 'Arabic',
    'bg': 'Bulgarian', 
    'cs': 'Czech',
    'da': 'Danish',
    'de': 'German',
    'el': 'Greek',
    'en': 'English',
    'es': 'Spanish',
    'et': 'Estonian',
    'fi': 'Finnish',
    'fr': 'French',
    'he': 'Hebrew',  # next-gen models only
    'hu': 'Hungarian',
    'id': 'Indonesian',
    'it': 'Italian',
    'ja': 'Japanese',
    'ko': 'Korean',
    'lt': 'Lithuanian',
    'lv': 'Latvian',
    'nb': 'Norwegian (Bokmål)',
    'nl': 'Dutch',
    'pl': 'Polish',
    'pt': 'Portuguese',
    'ro': 'Romanian',
    'ru': 'Russian',
    'sk': 'Slovak',
    'sl': 'Slovenian',
    'sv': 'Swedish',
    'th': 'Thai',  # next-gen models only
    'tr': 'Turkish',
    'uk': 'Ukrainian',
    'vi': 'Vietnamese',  # next-gen models only
    'zh': 'Chinese'
}

DEEPL_TARGET_LANGUAGES = {
    'ar': 'Arabic',
    'bg': 'Bulgarian',
    'cs': 'Czech', 
    'da': 'Danish',
    'de': 'German',
    'el': 'Greek',
    'en': 'English',
    'en-gb': 'English (British)',
    'en-us': 'English (American)',
    'es': 'Spanish',
    'es-419': 'Spanish (Latin American)',  # next-gen models only
    'et': 'Estonian',
    'fi': 'Finnish',
    'fr': 'French',
    'he': 'Hebrew',  # next-gen models only
    'hu': 'Hungarian',
    'id': 'Indonesian',
    'it': 'Italian',
    'ja': 'Japanese',
    'ko': 'Korean',
    'lt': 'Lithuanian',
    'lv': 'Latvian',
    'nb': 'Norwegian (Bokmål)',
    'nl': 'Dutch',
    'pl': 'Polish',
    'pt': 'Portuguese',
    'pt-br': 'Portuguese (Brazilian)',
    'pt-pt': 'Portuguese (European)',
    'ro': 'Romanian',
    'ru': 'Russian',
    'sk': 'Slovak',
    'sl': 'Slovenian',
    'sv': 'Swedish',
    'th': 'Thai',  # next-gen models only
    'tr': 'Turkish',
    'uk': 'Ukrainian',
    'vi': 'Vietnamese',  # next-gen models only
    'zh': 'Chinese',
    'zh-hans': 'Chinese (Simplified)',
    'zh-hant': 'Chinese (Traditional)'
}


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


def normalize_language_code(lang_code, is_target=False):
    """Нормализация языкового кода для DeepL API"""
    if not lang_code:
        return None
    
    lang_lower = lang_code.lower().strip()
    
    # Проверяем поддержку языка
    if is_target:
        if lang_lower not in DEEPL_TARGET_LANGUAGES:
            # Пытаемся найти совпадение без региональных вариантов
            base_lang = lang_lower.split('-')[0]
            if base_lang in DEEPL_TARGET_LANGUAGES:
                lang_lower = base_lang
            else:
                return None
        return lang_lower.upper()
    else:
        if lang_lower not in DEEPL_SOURCE_LANGUAGES:
            base_lang = lang_lower.split('-')[0]
            if base_lang in DEEPL_SOURCE_LANGUAGES:
                lang_lower = base_lang
            else:
                return None
        return lang_lower.upper()


def translate_text(text, src_lang='en', dest_lang='ru'):
    """Перевод текста через DeepL API с поддержкой всех языков"""
    global _last_translation

    if not text or not text.strip():
        return ""

    if not translator_instance:
        logging.error("DeepL переводчик не инициализирован")
        return f"[ОШИБКА ПЕРЕВОДА: {text}]"

    try:
        # Нормализуем языковые коды
        source_lang = normalize_language_code(src_lang, is_target=False)
        target_lang = normalize_language_code(dest_lang, is_target=True)
        
        if not target_lang:
            logging.error(f"Неподдерживаемый целевой язык: {dest_lang}")
            return f"[НЕПОДДЕРЖИВАЕМЫЙ ЯЗЫК {dest_lang}: {text}]"
        
        logging.info(f"DeepL перевод: {src_lang} → {dest_lang} (нормализовано: {source_lang} → {target_lang})")
        
        # Разбиваем длинный текст на сегменты для лучшего перевода
        text_segments = split_text_into_sentences(text, max_length=400)
        
        if len(text_segments) == 1:
            # Короткий текст - переводим как есть
            kwargs = {'target_lang': target_lang}
            if source_lang:
                kwargs['source_lang'] = source_lang
            
            result = translator_instance.translate_text(text, **kwargs)
            translated = result.text
        else:
            # Длинный текст - переводим по частям
            logging.info(f"DeepL: разбиваем текст на {len(text_segments)} сегментов для перевода")
            translated_segments = []
            
            for i, segment in enumerate(text_segments):
                try:
                    kwargs = {'target_lang': target_lang}
                    if source_lang:
                        kwargs['source_lang'] = source_lang
                    
                    result = translator_instance.translate_text(segment, **kwargs)
                    translated_segments.append(result.text)
                    logging.debug(f"DeepL: сегмент {i+1}/{len(text_segments)} переведен")
                except Exception as e:
                    logging.error(f"DeepL: ошибка перевода сегмента {i+1}: {e}")
                    translated_segments.append(f"[ОШИБКА СЕГМЕНТА {i+1}: {segment}]")
            
            translated = " ".join(translated_segments)

        _last_translation = {
            'original': text, 
            'translated': translated, 
            'method': 'deepl',
            'source_lang': src_lang,
            'target_lang': dest_lang
        }
        return translated

    except Exception as e:
        logging.error(f"DeepL перевод ошибка: {e}")
        return f"[ОШИБКА ПЕРЕВОДА: {text}]"


def get_supported_languages():
    """Получить список поддерживаемых языков"""
    return {
        'source_languages': DEEPL_SOURCE_LANGUAGES,
        'target_languages': DEEPL_TARGET_LANGUAGES
    }


# Маппинг языковых кодов на TTS модели и метаданные
LANGUAGE_TTS_MAPPING = {
    'ar': {'tts_lang': 'ar', 'name': 'Arabic', 'iso': 'ara'},
    'bg': {'tts_lang': 'bg', 'name': 'Bulgarian', 'iso': 'bul'},
    'cs': {'tts_lang': 'cs', 'name': 'Czech', 'iso': 'ces'},
    'da': {'tts_lang': 'da', 'name': 'Danish', 'iso': 'dan'},
    'de': {'tts_lang': 'de', 'name': 'German', 'iso': 'deu'},
    'el': {'tts_lang': 'el', 'name': 'Greek', 'iso': 'ell'},
    'en': {'tts_lang': 'en', 'name': 'English', 'iso': 'eng'},
    'en-gb': {'tts_lang': 'en', 'name': 'English (British)', 'iso': 'eng'},
    'en-us': {'tts_lang': 'en', 'name': 'English (American)', 'iso': 'eng'},
    'es': {'tts_lang': 'es', 'name': 'Spanish', 'iso': 'spa'},
    'es-419': {'tts_lang': 'es', 'name': 'Spanish (Latin American)', 'iso': 'spa'},
    'et': {'tts_lang': 'et', 'name': 'Estonian', 'iso': 'est'},
    'fi': {'tts_lang': 'fi', 'name': 'Finnish', 'iso': 'fin'},
    'fr': {'tts_lang': 'fr', 'name': 'French', 'iso': 'fra'},
    'he': {'tts_lang': 'he', 'name': 'Hebrew', 'iso': 'heb'},
    'hu': {'tts_lang': 'hu', 'name': 'Hungarian', 'iso': 'hun'},
    'id': {'tts_lang': 'id', 'name': 'Indonesian', 'iso': 'ind'},
    'it': {'tts_lang': 'it', 'name': 'Italian', 'iso': 'ita'},
    'ja': {'tts_lang': 'ja', 'name': 'Japanese', 'iso': 'jpn'},
    'ko': {'tts_lang': 'ko', 'name': 'Korean', 'iso': 'kor'},
    'lt': {'tts_lang': 'lt', 'name': 'Lithuanian', 'iso': 'lit'},
    'lv': {'tts_lang': 'lv', 'name': 'Latvian', 'iso': 'lav'},
    'nb': {'tts_lang': 'no', 'name': 'Norwegian (Bokmål)', 'iso': 'nor'},
    'nl': {'tts_lang': 'nl', 'name': 'Dutch', 'iso': 'nld'},
    'pl': {'tts_lang': 'pl', 'name': 'Polish', 'iso': 'pol'},
    'pt': {'tts_lang': 'pt', 'name': 'Portuguese', 'iso': 'por'},
    'pt-br': {'tts_lang': 'pt', 'name': 'Portuguese (Brazilian)', 'iso': 'por'},
    'pt-pt': {'tts_lang': 'pt', 'name': 'Portuguese (European)', 'iso': 'por'},
    'ro': {'tts_lang': 'ro', 'name': 'Romanian', 'iso': 'ron'},
    'ru': {'tts_lang': 'ru', 'name': 'Russian', 'iso': 'rus'},
    'sk': {'tts_lang': 'sk', 'name': 'Slovak', 'iso': 'slk'},
    'sl': {'tts_lang': 'sl', 'name': 'Slovenian', 'iso': 'slv'},
    'sv': {'tts_lang': 'sv', 'name': 'Swedish', 'iso': 'swe'},
    'th': {'tts_lang': 'th', 'name': 'Thai', 'iso': 'tha'},
    'tr': {'tts_lang': 'tr', 'name': 'Turkish', 'iso': 'tur'},
    'uk': {'tts_lang': 'uk', 'name': 'Ukrainian', 'iso': 'ukr'},
    'vi': {'tts_lang': 'vi', 'name': 'Vietnamese', 'iso': 'vie'},
    'zh': {'tts_lang': 'zh', 'name': 'Chinese', 'iso': 'zho'},
    'zh-hans': {'tts_lang': 'zh', 'name': 'Chinese (Simplified)', 'iso': 'zho'},
    'zh-hant': {'tts_lang': 'zh-tw', 'name': 'Chinese (Traditional)', 'iso': 'zho'},
}


def get_language_info(lang_code):
    """Получить информацию о языке для TTS и метаданных"""
    lang_lower = lang_code.lower().strip()
    return LANGUAGE_TTS_MAPPING.get(lang_lower, {
        'tts_lang': lang_lower,
        'name': lang_code.upper(),
        'iso': lang_lower[:3]
    })


def get_translator_status():
    """Получить статус DeepL переводчика"""
    return {
        'type': 'deepl',
        'working': translator_instance is not None,
        'description': 'DeepL API - премиум качество перевода' if translator_instance else 'DeepL недоступен',
        'last_translation': _last_translation
    }