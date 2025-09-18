#!/usr/bin/env python3
"""
Утилита для создания SRT субтитров из существующих JSON файлов результатов
"""

import json
import sys
from pathlib import Path

def format_time_srt(seconds: float) -> str:
    """Форматирование времени для SRT"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"

def create_srt_from_json(recognition_json_path: str, translation_json_path: str, output_dir: str = None):
    """
    Создание SRT файлов из JSON файлов результатов
    
    Args:
        recognition_json_path: путь к JSON файлу с результатами распознавания
        translation_json_path: путь к JSON файлу с результатами перевода
        output_dir: директория для сохранения SRT файлов
    """
    try:
        # Загружаем JSON файлы
        with open(recognition_json_path, 'r', encoding='utf-8') as f:
            recognition_data = json.load(f)
        
        with open(translation_json_path, 'r', encoding='utf-8') as f:
            translation_data = json.load(f)
        
        # Объединяем данные
        combined_segments = []
        recognition_segments = recognition_data.get('segments', [])
        translation_segments = translation_data.get('segments', [])
        
        for i, recognition_segment in enumerate(recognition_segments):
            translation_segment = translation_segments[i] if i < len(translation_segments) else {}
            
            combined_segment = {
                'start_time': recognition_segment.get('start_time', 0),
                'end_time': recognition_segment.get('end_time', 0),
                'original_text': recognition_segment.get('text', ''),
                'translated_text': translation_segment.get('translated_text', '')
            }
            combined_segments.append(combined_segment)
        
        # Определяем выходную директорию
        if output_dir is None:
            output_dir = Path(recognition_json_path).parent
        
        base_name = Path(recognition_json_path).stem.replace('_recognition_', '_subtitles_')
        
        # Создаем разные типы SRT файлов
        create_srt_file(combined_segments, Path(output_dir) / f"{base_name}_original.srt", "original")
        create_srt_file(combined_segments, Path(output_dir) / f"{base_name}_translated.srt", "translated")
        create_srt_file(combined_segments, Path(output_dir) / f"{base_name}_dual.srt", "dual")
        
        print(f"✅ SRT субтитры созданы в директории: {output_dir}")
        print(f"  - {base_name}_original.srt")
        print(f"  - {base_name}_translated.srt")
        print(f"  - {base_name}_dual.srt")
        
    except Exception as e:
        print(f"❌ Ошибка создания SRT файлов: {e}")

def create_srt_file(segments, output_file: Path, subtitle_type: str):
    """Создание конкретного SRT файла"""
    srt_content = []
    subtitle_index = 1
    
    for segment in segments:
        start_time = segment.get('start_time', 0)
        end_time = segment.get('end_time', start_time + 1)
        
        original_text = segment.get('original_text', '')
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
        srt_content.append(f"{format_time_srt(start_time)} --> {format_time_srt(end_time)}")
        srt_content.append(subtitle_text)
        srt_content.append("")  # Пустая строка между субтитрами
        
        subtitle_index += 1
    
    # Сохраняем файл
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(srt_content))

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Использование:")
        print("  python create_subtitles_from_json.py recognition.json translation.json [output_dir]")
        print("")
        print("Пример:")
        print("  python create_subtitles_from_json.py outputs/video_recognition_20250915_203216.json outputs/video_translation_20250915_203216.json")
        sys.exit(1)
    
    recognition_json = sys.argv[1]
    translation_json = sys.argv[2]
    output_dir = sys.argv[3] if len(sys.argv) > 3 else None
    
    create_srt_from_json(recognition_json, translation_json, output_dir)