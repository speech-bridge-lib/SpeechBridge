# Создайте простой тест в папке src
# test_pyttsx3.py
import pyttsx3
from pathlib import Path


def test_pyttsx3_direct():
    try:
        engine = pyttsx3.init()

        # Показать доступные голоса
        voices = engine.getProperty('voices')
        print(f"Доступно голосов: {len(voices)}")
        for i, voice in enumerate(voices[:5]):  # первые 5
            print(f"  {i}: {voice.name} - {voice.id}")

        # Тест синтеза
        text = "Привет мир, это тест русской речи"
        output_file = "test_tts.wav"

        engine.save_to_file(text, output_file)
        engine.runAndWait()

        if Path(output_file).exists():
            size = Path(output_file).stat().st_size
            print(f"Файл создан: {output_file} ({size} bytes)")
            return True
        else:
            print("Файл не создан")
            return False

    except Exception as e:
        print(f"Ошибка: {e}")
        return False


if __name__ == "__main__":
    test_pyttsx3_direct()