#!/usr/bin/env python3
"""
ПРОСТЕЙШИЙ переводчик видео БЕЗ веб-интерфейса
Только основная функциональность, ничего лишнего
"""

import os
import sys
import logging
from pathlib import Path

# Настройка детального логирования - файл полностью перезаписывается каждый раз
# Сначала удаляем старый лог-файл если существует
log_file = Path('translation_debug.log')
if log_file.exists():
    log_file.unlink()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('translation_debug.log', mode='w', encoding='utf-8')
    ],
    force=True  # Принудительно перенастраиваем логгер
)
logger = logging.getLogger(__name__)

# Загружаем .env файл
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    load_dotenv(env_path)
    logger.info(f"📋 .env файл загружен из: {env_path}")
    print(f"📋 .env файл загружен из: {env_path}")
except ImportError:
    print("⚠️ python-dotenv не установлен, пытаемся без .env")
    logger.warning("python-dotenv не установлен")

# Минимум переменных окружения
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['OMP_NUM_THREADS'] = '1'

def create_whisper_segments(audio_file, max_segment_duration=25.0):
    """
    Создает сегменты на основе Whisper word-level timestamps
    """
    logger.info("🎙️ Запускаем Whisper для получения word-level timestamps...")
    print("🎙️ Анализ речи через Whisper (это может занять время)...")
    
    try:
        import whisper
        import torch
        
        # Проверяем доступную память
        if torch.cuda.is_available():
            print(f"🔥 Используем CUDA GPU")
            device = "cuda"
        else:
            print(f"🖥️ Используем CPU")
            device = "cpu"
        
        # Загружаем модель Whisper (используем tiny для скорости и стабильности)
        logger.info("📦 Загружаем Whisper модель 'tiny'...")
        model = whisper.load_model("tiny", device=device)
        
        # Получаем результат с word-level timestamps
        logger.info("🔄 Запускаем Whisper transcribe...")
        print("⏳ Обработка речи... (может занять 1-2 минуты)")
        
        result = model.transcribe(
            audio_file, 
            word_timestamps=True,
            language="en",  # Указываем английский язык
            fp16=False,     # Отключаем FP16 для стабильности на CPU
            verbose=False,  # Отключаем подробный вывод для чистоты лога
            temperature=0.0,  # Детерминированный результат
            beam_size=1,      # Упрощаем для экономии памяти
            best_of=1         # Один проход для экономии времени
        )
        logger.info("✅ Whisper transcribe завершен успешно")
        
        segments = []
        current_segment_words = []
        current_start = None
        current_text = ""
        
        logger.info(f"🎵 Whisper обнаружил {len(result.get('segments', []))} сегментов речи")
        
        # Обрабатываем каждый сегмент Whisper
        for segment in result['segments']:
            words = segment.get('words', [])
            if not words:
                continue
            
            logger.info(f"📝 Сегмент: {segment['start']:.1f}s - {segment['end']:.1f}s")
            
            # Группируем слова в логические сегменты
            for word_info in words:
                word = word_info.get('word', '').strip()
                word_start = word_info.get('start', 0)
                word_end = word_info.get('end', 0)
                
                if current_start is None:
                    current_start = word_start
                
                current_segment_words.append(word)
                current_text = " ".join(current_segment_words).strip()
                
                # Проверяем длительность текущего сегмента
                current_duration = word_end - current_start
                
                # Создаем новый сегмент если:
                # 1. Достигнута максимальная длительность
                # 2. Найден естественный конец предложения (точка, вопрос, восклицание)
                # 3. Длинная пауза до следующего слова
                should_end_segment = False
                
                if current_duration >= max_segment_duration:
                    should_end_segment = True
                    logger.info(f"⏰ Сегмент завершен по времени: {current_duration:.1f}s")
                
                elif word.endswith(('.', '!', '?')):
                    should_end_segment = True
                    logger.info(f"📍 Сегмент завершен по пунктуации: '{word}'")
                
                if should_end_segment and current_text.strip():
                    segments.append({
                        'start_time': current_start,
                        'end_time': word_end,
                        'text': current_text,
                        'duration': word_end - current_start
                    })
                    
                    logger.info(f"✅ Создан сегмент: {current_start:.1f}s-{word_end:.1f}s ({len(current_text)} символов)")
                    
                    # Сброс для нового сегмента
                    current_segment_words = []
                    current_start = None
                    current_text = ""
        
        # Добавляем последний сегмент если есть
        if current_segment_words and current_start is not None:
            last_word = words[-1] if words else {'end': current_start}
            segments.append({
                'start_time': current_start,
                'end_time': last_word.get('end', current_start + 1),
                'text': current_text,
                'duration': last_word.get('end', current_start + 1) - current_start
            })
        
        logger.info(f"🎯 Whisper создал {len(segments)} оптимизированных сегментов")
        print(f"🎯 Создано {len(segments)} сегментов на основе анализа речи")
        
        return segments, result['text']  # Возвращаем сегменты и полный текст
        
    except ImportError as e:
        logger.error(f"❌ Библиотека whisper не найдена: {e}")
        print("❌ Ошибка: библиотека whisper не установлена")
        return None, None
    except RuntimeError as e:
        logger.error(f"❌ Ошибка выполнения Whisper: {e}")
        print(f"❌ Ошибка памяти или модели Whisper: {e}")
        return None, None
    except torch.cuda.OutOfMemoryError as e:
        logger.error(f"❌ Не хватает памяти GPU: {e}")
        print("❌ Недостаточно памяти GPU, попробуйте с CPU")
        return None, None
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка Whisper: {e}")
        print(f"❌ Ошибка при анализе речи: {e}")
        import traceback
        logger.error(f"Полная трассировка: {traceback.format_exc()}")
        return None, None

def main():
    print("🎬 ПРОСТОЙ ПЕРЕВОДЧИК ВИДЕО")
    print("=" * 50)
    logger.info("=" * 80)
    logger.info("🚀 НОВАЯ СЕССИЯ ПЕРЕВОДЧИКА ВИДЕО НАЧАТА")
    logger.info("=" * 80)
    
    # Проверяем аргументы
    if len(sys.argv) < 2:
        print("Использование: python simple_translator.py video.mp4")
        return
    
    video_path = sys.argv[1]
    if not Path(video_path).exists():
        print(f"❌ Файл не найден: {video_path}")
        return
    
    print(f"📹 Входной файл: {video_path}")
    
    try:
        # 1. Извлекаем аудио через moviepy
        print("1️⃣ Извлечение аудио...")
        import moviepy.editor as mp
        
        video = mp.VideoFileClip(video_path)
        temp_audio = "temp_audio.wav"
        video.audio.write_audiofile(temp_audio, verbose=False, logger=None)
        print(f"✅ Аудио сохранено: {temp_audio}")
        
        # 2. Сегментируем аудио - выбираем лучший метод
        print("2️⃣ Умная сегментация аудио...")
        from pydub import AudioSegment
        
        # Загружаем аудио через pydub для определения длительности
        audio_segment = AudioSegment.from_file(temp_audio)
        audio_duration = len(audio_segment) / 1000.0  # в секундах
        print(f"⏱️ Длительность аудио: {audio_duration:.1f} секунд")
        
        # Выбираем метод сегментации: временно отключаем Whisper для отладки
        use_whisper = False  # audio_duration > 120.0  # Whisper для длинных видео с разными спикерами
        
        print(f"🔧 Временно используем классическую сегментацию для отладки")
        
        if use_whisper:
            print("🎙️ Используем Whisper для точной сегментации речи...")
            whisper_segments, full_text = create_whisper_segments(temp_audio)
            
            if whisper_segments:
                # Конвертируем Whisper сегменты в нужный формат
                segments = []
                segment_timestamps = []
                
                for i, seg in enumerate(whisper_segments):
                    start_ms = int(seg['start_time'] * 1000)
                    end_ms = int(seg['end_time'] * 1000)
                    
                    # Извлекаем аудиосегмент
                    segment = audio_segment[start_ms:end_ms]
                    segments.append(segment)
                    segment_timestamps.append((seg['start_time'], seg['end_time']))
                    
                    logger.info(f"  📊 Whisper сегмент {i+1}: {seg['start_time']:.2f}s - {seg['end_time']:.2f}s (длина {seg['duration']:.2f}s)")
                    logger.info(f"      📝 Текст: '{seg['text'][:50]}...'")
                
                logger.info(f"🎯 Whisper создал {len(segments)} оптимизированных сегментов")
                print(f"🎯 Создано {len(segments)} сегментов на основе анализа речи")
            else:
                print("⚠️ Ошибка Whisper, переключаемся на обычную сегментацию...")
                use_whisper = False
        
        if not use_whisper:
            print("🔊 Используем улучшенную сегментацию с полным покрытием...")
            from pydub.silence import detect_nonsilent
            
            logger.info("🔍 Создаём непрерывное покрытие всего видео...")
            
            # КАРДИНАЛЬНОЕ ИСПРАВЛЕНИЕ: Создаём равномерные сегменты с полным покрытием
            segment_duration_sec = 20.0  # Оптимальная длина для хорошего распознавания
            overlap_sec = 0.5  # Небольшое перекрытие для continuity
            
            video_duration_ms = len(audio_segment)
            video_duration_sec = video_duration_ms / 1000.0
            
            logger.info(f"🎬 Видео: {video_duration_sec:.1f}s, сегменты по {segment_duration_sec}s")
            print(f"🎬 Создаём равномерные сегменты по {segment_duration_sec}s для полного покрытия")
            
            # СОЗДАЁМ РАВНОМЕРНУЮ СЕТКУ БЕЗ ПРОПУСКОВ
            nonsilent_ranges = []
            current_time = 0.0
            
            while current_time < video_duration_sec:
                # Рассчитываем границы сегмента
                start_sec = current_time
                end_sec = min(current_time + segment_duration_sec, video_duration_sec)
                
                # Конвертируем в миллисекунды
                start_ms = int(start_sec * 1000)
                end_ms = int(end_sec * 1000)
                
                # Добавляем сегмент только если он достаточно длинный
                if (end_ms - start_ms) >= 3000:  # Минимум 3 секунды
                    nonsilent_ranges.append((start_ms, end_ms))
                    logger.info(f"📊 Сегмент: {start_sec:.1f}s - {end_sec:.1f}s (длина {end_sec-start_sec:.1f}s)")
                
                # Переходим к следующему сегменту с учётом overlap
                current_time += segment_duration_sec - overlap_sec
            
            logger.info(f"🎯 ПОЛНОЕ ПОКРЫТИЕ: Создано {len(nonsilent_ranges)} равномерных сегментов")
            print(f"🎯 Создано {len(nonsilent_ranges)} сегментов с полным покрытием видео")
            
            # ДОПОЛНИТЕЛЬНО: Используем detect_nonsilent для анализа (но не заменяем основные сегменты)
            logger.info("🔍 Дополнительный анализ тишины для справки...")
            detected_ranges = detect_nonsilent(
                audio_segment,
                min_silence_len=1000,  # 1 секунда
                silence_thresh=-45
            )
            logger.info(f"📈 Детектор тишины нашёл {len(detected_ranges)} участков с речью")
            
            # Анализируем покрытие
            total_coverage = 0
            for start_ms, end_ms in nonsilent_ranges:
                total_coverage += (end_ms - start_ms) / 1000.0
            
            coverage_percent = (total_coverage / video_duration_sec) * 100
            logger.info(f"📊 Общее покрытие видео: {coverage_percent:.1f}% ({total_coverage:.1f}s из {video_duration_sec:.1f}s)")
            print(f"📊 Покрытие видео: {coverage_percent:.0f}% (без пропусков в начале и середине)")
            
            logger.info(f"🎵 Итого сегментов: {len(nonsilent_ranges)}")
            print(f"🎵 Итого сегментов: {len(nonsilent_ranges)}")
            
            # УПРОЩЕНО: Создаём сегменты напрямую (без дополнительного разбиения)
            segments = []
            segment_timestamps = []  # Храним реальные временные метки
            
            for i, (start_ms, end_ms) in enumerate(nonsilent_ranges):
                # Добавляем небольшие отступы для лучшего распознавания
                padding = 100  # Уменьшенный padding для точности
                padded_start = max(0, start_ms - padding)
                padded_end = min(len(audio_segment), end_ms + padding)
                
                segment = audio_segment[padded_start:padded_end]
                segments.append(segment)
                
                real_start_sec = start_ms / 1000.0
                real_end_sec = end_ms / 1000.0
                segment_timestamps.append((real_start_sec, real_end_sec))
                
                segment_duration_sec = (end_ms - start_ms) / 1000.0
                logger.info(f"  📊 Сегмент {len(segments)}: {real_start_sec:.2f}s - {real_end_sec:.2f}s (длина {segment_duration_sec:.2f}s)")
        
        print(f"📊 Создано {len(segments)} синхронизированных сегментов")
        
        # НОВОЕ: Сохраняем информацию о сегментах в файл для отладки
        with open("segments_timing.txt", "w", encoding='utf-8') as f:
            f.write("=== ИНФОРМАЦИЯ О СЕГМЕНТАХ ===\n")
            f.write(f"Общая длительность видео: {audio_duration:.1f} секунд\n")
            f.write(f"Всего сегментов: {len(segments)}\n\n")
            
            for i, (start_sec, end_sec) in enumerate(segment_timestamps):
                duration = end_sec - start_sec
                f.write(f"Сегмент {i+1:2d}: {start_sec:7.2f}s - {end_sec:7.2f}s (длина {duration:6.2f}s)\n")
        
        print(f"📄 Информация о сегментах сохранена в segments_timing.txt")
        
        # 3. Распознаём каждый сегмент с использованием точных временных меток
        if use_whisper and whisper_segments:
            print("3️⃣ Используем текст из Whisper...")
            logger.info(f"🎯 Используем готовый текст из {len(whisper_segments)} Whisper сегментов")
            
            segment_texts = []
            final_segment_times = []  # Финальные временные метки для размещения аудио
            
            for i, seg in enumerate(whisper_segments):
                segment_texts.append(seg['text'])
                final_segment_times.append((seg['start_time'], seg['end_time']))
                logger.info(f"   📝 Сегмент {i+1}: '{seg['text'][:80]}...'")
        else:
            print("3️⃣ Распознавание сегментов...")
            print("⏳ Это может занять время для длинного видео...")
            logger.info(f"🎯 Начинаем распознавание {len(segments)} сегментов")
            
            import speech_recognition as sr
            import tempfile
            import time
            
            recognizer = sr.Recognizer()
            if audio_duration > 60:
                recognizer.energy_threshold = 4000
            
            segment_texts = []
            final_segment_times = []  # Финальные временные метки для размещения аудио
            
            valid_segments = [seg for seg in segments if len(seg) >= 500]
            
            print(f"📊 Обрабатываем {len(valid_segments)} сегментов из {len(segments)}")
            logger.info(f"📊 Валидных сегментов: {len(valid_segments)}/{len(segments)}")
            
            processed_count = 0
            for i, segment in enumerate(segments):
                segment_start_time = time.time()
                
                if len(segment) < 500:  # Пропускаем слишком короткие сегменты
                    logger.info(f"   ⏭️ Сегмент {i+1}: пропущен (слишком короткий: {len(segment)}ms)")
                    continue
                
                processed_count += 1
                real_start_sec, real_end_sec = segment_timestamps[i]  # Используем реальные временные метки
            
                print(f"   🎯 Сегмент {processed_count}/{len(valid_segments)}: {real_start_sec:.1f}-{real_end_sec:.1f}s")
                logger.info(f"   🎯 Обрабатываем сегмент {i+1} ({processed_count}/{len(valid_segments)})")
                logger.info(f"      🕐 Реальные временные метки: {real_start_sec:.2f}s - {real_end_sec:.2f}s")
                
                # Сохраняем сегмент во временный файл
                logger.info(f"      💾 Экспортируем сегмент во временный файл...")
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                    segment.export(tmp_file.name, format="wav")
                    logger.info(f"      📁 Временный файл: {tmp_file.name}")
                
                try:
                    print(f"      🔄 Распознавание Google API...")
                    logger.info(f"      🔄 Начинаем распознавание через Google API...")
                    
                    with sr.AudioFile(tmp_file.name) as source:
                        audio_data = recognizer.record(source)
                    
                    # Добавим таймаут для Google API
                    import signal
                    def timeout_handler(signum, frame):
                        raise TimeoutError("Google API timeout")
                    
                    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(30)  # 30 секунд таймаут для API
                    
                    try:
                        text = recognizer.recognize_google(audio_data, language='en-US')
                    finally:
                        signal.alarm(0)
                        signal.signal(signal.SIGALRM, old_handler)
                    
                    # ИСПРАВЛЕНО: Используем точные временные метки из detect_nonsilent
                    segment_texts.append(text)
                    final_segment_times.append((real_start_sec, real_end_sec))
                    
                    processing_time = time.time() - segment_start_time
                    logger.info(f"      ✅ Временные метки (точные): {real_start_sec:.2f}s - {real_end_sec:.2f}s")
                    logger.info(f"      📝 Текст: '{text}'")
                    logger.info(f"      ⏱️ Время обработки: {processing_time:.1f}s")
                    print(f"      ✅ '{text[:50]}...' [{real_start_sec:.1f}-{real_end_sec:.1f}s] ({processing_time:.1f}s)")
                    
                except TimeoutError:
                    logger.error(f"      ⏰ Google API таймаут (30s)")
                    print(f"      ⏰ API таймаут")
                except (sr.RequestError, sr.UnknownValueError) as e:
                    logger.warning(f"      ⚠️ Первая попытка не удалась: {e}")
                    print(f"      ⚠️ Первая попытка не удалась, пробуем с другими настройками...")
                    
                    # Попытка 2: с другими настройками распознавания
                    try:
                        recognizer_backup = sr.Recognizer()
                        recognizer_backup.energy_threshold = 300  # Ниже порог
                        recognizer_backup.dynamic_energy_threshold = True
                        
                        with sr.AudioFile(tmp_file.name) as source:
                            recognizer_backup.adjust_for_ambient_noise(source, duration=0.5)
                            audio_data = recognizer_backup.record(source)
                        
                        text = recognizer_backup.recognize_google(audio_data, language='en-US')
                        logger.info(f"      ✅ Распознан со второй попытки: '{text}'")
                        print(f"      ✅ Распознан со второй попытки")
                        
                        segment_texts.append(text)
                        final_segment_times.append((real_start_sec, real_end_sec))
                        
                    except Exception as e2:
                        logger.warning(f"      ❌ Сегмент окончательно не распознан: {e2}")
                        print(f"      ❌ Сегмент пропущен")
                        # Не добавляем в segment_texts - сегмент будет пропущен
                    
                Path(tmp_file.name).unlink()
                logger.info(f"      🗑️ Временный файл удален")
        
        if not segment_texts:
            print("❌ Ни один сегмент не распознан")
            return
            
        # Объединяем все тексты
        full_text = " ".join(segment_texts)
        print(f"🎯 Общий текст ({len(full_text)} символов): {full_text[:100]}...")
        
        # 4. Переводим через DeepL
        print("4️⃣ Перевод текста...")
        import deepl
        
        api_key = os.getenv('DEEPL_API_KEY')
        print(f"🔑 DeepL ключ найден: {'Да' if api_key else 'Нет'}")
        if api_key:
            print(f"🔑 Ключ начинается с: {api_key[:10]}...")
        
        if not api_key:
            print("❌ Нужен DEEPL_API_KEY в .env")
            print(f"📁 Проверьте файл: {Path('.env').absolute()}")
            return
            
        translator = deepl.Translator(api_key)
        
        # Переводим каждый сегмент отдельно для лучшего качества
        print(f"📊 Переводим {len(segment_texts)} сегментов...")
        translated_segments = []
        for i, text in enumerate(segment_texts):
            try:
                print(f"   🔄 Перевод {i+1}/{len(segment_texts)}...")
                logger.info(f"   🌍 Переводим сегмент {i+1}: '{text}'")
                
                translated = translator.translate_text(text, target_lang="RU").text
                translated_segments.append(translated)
                logger.info(f"   ✅ Переведен: '{translated}'")
                print(f"   ✅ Сегмент {i+1}: '{translated[:50]}...'")
            except Exception as e:
                logger.error(f"   ❌ Ошибка перевода сегмента {i+1}: {e}")
                print(f"   ❌ Ошибка перевода сегмента {i+1}: {e}")
                translated_segments.append(text)  # Fallback к оригиналу
                
        full_translated = " ".join(translated_segments)
        print(f"🌍 Полный перевод: {full_translated[:100]}...")
        
        # 5. Создаём синхронизированное аудио
        print("5️⃣ Создание синхронизированного русского аудио...")
        import subprocess
        
        # Создаём базовую тишину длиной как оригинальное видео
        final_audio_segment = AudioSegment.silent(duration=int(audio_duration * 1000))
        print(f"🔇 Создана тишина длиной {audio_duration:.1f}s")
        
        # Создаём переведённое аудио для каждого сегмента и размещаем по временным меткам
        logger.info("🎵 === СОЗДАНИЕ СИНХРОНИЗИРОВАННОГО АУДИО ===")
        for i, (translated_text, (start_time, end_time)) in enumerate(zip(translated_segments, final_segment_times)):
            if not translated_text.strip():
                logger.info(f"   ⏭️ Сегмент {i+1}: пропущен (пустой текст)")
                continue
                
            logger.info(f"   🎤 СЕГМЕНТ {i+1}: {start_time:.2f}s - {end_time:.2f}s")
            logger.info(f"   📝 Текст: '{translated_text}'")
            print(f"   🎤 Сегмент {i+1}: {start_time:.1f}-{end_time:.1f}s")
            
            # Создаём аудио для этого сегмента
            segment_aiff = f"segment_{i}.aiff"
            cmd = ['say', '-v', 'Milena', '-o', segment_aiff, translated_text]
            subprocess.run(cmd, check=True)
            
            # Загружаем и обрабатываем
            segment_audio = AudioSegment.from_file(segment_aiff)
            original_duration = len(segment_audio) / 1000.0
            logger.info(f"   📊 TTS аудио создано: {original_duration:.2f}s, громкость {segment_audio.dBFS:.1f}dBFS")
            
            # Нормализуем если нужно
            if segment_audio.dBFS < -30:
                segment_audio = segment_audio.normalize(headroom=20.0)
                logger.info(f"   🔊 Нормализовано до {segment_audio.dBFS:.1f}dBFS")
            
            # Размещаем в правильном месте финального аудио с умным масштабированием
            start_ms = int(start_time * 1000)
            end_ms = int(end_time * 1000)
            available_duration_ms = end_ms - start_ms
            segment_duration_ms = len(segment_audio)
            
            logger.info(f"   ⏰ Позиция в видео: {start_ms}ms - {end_ms}ms (доступно {available_duration_ms}ms)")
            logger.info(f"   📏 TTS аудио: {segment_duration_ms}ms")
            
            # ИСПРАВЛЕНО: Простое размещение без агрессивного масштабирования
            duration_ratio = segment_duration_ms / available_duration_ms
            
            if duration_ratio > 1.15:  # ТОЛЬКО КРИТИЧЕСКИЕ СЛУЧАИ: TTS намного длиннее слота
                # Лёгкое ускорение только в критических случаях
                speed_factor = min(duration_ratio, 1.3)  # Максимум 1.3x
                segment_audio = segment_audio.speedup(playback_speed=speed_factor)
                logger.info(f"   ⏩ Лёгкое ускорение в {speed_factor:.2f}x (критический случай)")
                print(f"      ⏩ Ускорено в {speed_factor:.1f}x")
                    
            elif duration_ratio < 0.7:  # ТОЛЬКО если TTS значительно короче
                # Добавляем небольшую естественную паузу
                padding_ms = min(available_duration_ms - segment_duration_ms, 2000)  # Максимум 2 секунды
                
                if padding_ms > 200:  # Добавляем паузу только если есть смысл
                    silence_padding = AudioSegment.silent(duration=padding_ms)
                    segment_audio = segment_audio + silence_padding
                    logger.info(f"   🔇 Добавлена естественная пауза {padding_ms}ms")
                    print(f"      🔇 Добавлена пауза {padding_ms/1000:.1f}s")
            
            else:
                # НОРМАЛЬНЫЙ СЛУЧАЙ: TTS размещается как есть без изменений
                logger.info(f"   ✅ Размещение без изменений (соотношение {duration_ratio:.2f})")
                print(f"      ✅ Размещается как есть")
            
            # Накладываем сегмент на финальное аудио
            final_audio_segment = final_audio_segment.overlay(segment_audio, position=start_ms)
            logger.info(f"   ✅ Сегмент размещён на позиции {start_ms}ms (итоговая длина: {len(segment_audio)}ms)")
            
            # Удаляем временный файл
            Path(segment_aiff).unlink()
            print(f"      ✅ Размещён на позиции {start_time:.1f}s")
        
        # Сохраняем финальное синхронизированное аудио
        translated_audio_wav = "synchronized_audio.wav"
        final_audio_segment.export(translated_audio_wav, format="wav")
        print(f"🎵 Синхронизированное аудио готово: {translated_audio_wav}")
        
        # 6. Заменяем аудио в видео
        print("6️⃣ Создание финального видео...")
        final_audio = mp.AudioFileClip(translated_audio_wav)
        
        # Длительности уже должны совпадать, но проверяем на всякий случай
        if abs(final_audio.duration - video.duration) > 0.1:
            print(f"⚠️ Корректируем длительность: {final_audio.duration:.1f}s -> {video.duration:.1f}s")
            final_audio = final_audio.subclip(0, video.duration)
        else:
            print(f"✅ Длительности совпадают: {video.duration:.1f}s")
        
        final_video = video.set_audio(final_audio)
        
        # Создаём выходной файл с правильным расширением
        output_path = f"translated_{Path(video_path).stem}.mp4"
        
        print(f"💾 Сохраняем видео: {output_path}")
        final_video.write_videofile(
            output_path, 
            verbose=False, 
            logger=None,
            codec='libx264',      # Явно указываем видео кодек
            audio_codec='aac',    # Аудио кодек
            temp_audiofile='temp-audio.m4a',  # Временный аудио файл
            remove_temp=True      # Удаляем временные файлы
        )
        print(f"✅ Видео сохранено: {output_path}")
        
        # Очистка временных файлов
        Path(translated_audio_wav).unlink(missing_ok=True)
        
        print(f"🎉 ГОТОВО: {output_path}")
        logger.info(f"🎉 УСПЕШНО ЗАВЕРШЕНО: {output_path}")
        
        # НОВОЕ: Сохраняем подробную информацию в несколько файлов
        base_name = Path(video_path).stem
        
        # 1. Файл с оригинальным текстом и временными метками для анализа
        original_transcript_file = f"original_transcript_{base_name}.txt"
        with open(original_transcript_file, "w", encoding='utf-8') as f:
            f.write(f"=== ОРИГИНАЛЬНЫЙ ТЕКСТ С ВРЕМЕННЫМИ МЕТКАМИ ===\n")
            f.write(f"Видео: {video_path}\n")
            f.write(f"Длительность: {audio_duration:.1f} секунд\n")
            f.write(f"Сегментов: {len(segment_texts)}\n\n")
            
            # Форматируем как временные метки для удобного чтения
            for i, (text, (start, end)) in enumerate(zip(segment_texts, final_segment_times)):
                # Конвертируем секунды в минуты:секунды
                start_min, start_sec = divmod(int(start), 60)
                end_min, end_sec = divmod(int(end), 60)
                f.write(f"{start_min}:{start_sec:02d} - {end_min}:{end_sec:02d}  {text}\n")
            
            # Добавляем анализ пауз
            f.write(f"\n=== АНАЛИЗ ПАУЗ ===\n")
            for i in range(len(final_segment_times) - 1):
                current_end = final_segment_times[i][1]
                next_start = final_segment_times[i + 1][0]
                pause_duration = next_start - current_end
                
                if pause_duration > 0.5:  # Паузы больше 0.5 секунды
                    pause_min, pause_sec = divmod(int(current_end), 60)
                    f.write(f"{pause_min}:{pause_sec:02d} - ПАУЗА {pause_duration:.1f}s\n")
        
        print(f"📄 Оригинальный транскрипт сохранён в {original_transcript_file}")
        
        # 2. Полный файл с переводом
        full_transcript_file = f"full_transcript_{base_name}.txt"
        with open(full_transcript_file, "w", encoding='utf-8') as f:
            f.write("=== ПОЛНАЯ ИНФОРМАЦИЯ О ПЕРЕВОДЕ ===\n")
            f.write(f"Исходное видео: {video_path}\n")
            f.write(f"Результат: {output_path}\n")
            f.write(f"Длительность: {audio_duration:.1f} секунд\n")
            f.write(f"Сегментов обработано: {len(segment_texts)}\n\n")
            
            for i, (text, translated, (start, end)) in enumerate(zip(segment_texts, translated_segments, final_segment_times)):
                f.write(f"=== СЕГМЕНТ {i+1} ({start:.1f}s - {end:.1f}s) ===\n")
                f.write(f"EN: {text}\n")
                f.write(f"RU: {translated}\n\n")
        
        print(f"📄 Полный транскрипт сохранён в {full_transcript_file}")
        
        # 3. Краткий файл с временными метками для быстрого анализа
        timeline_file = f"timeline_{base_name}.txt"
        with open(timeline_file, "w", encoding='utf-8') as f:
            f.write(f"=== ВРЕМЕННАЯ ЛИНИЯ ВИДЕО ===\n")
            f.write(f"Видео: {base_name} ({audio_duration:.1f}s)\n\n")
            
            # Создаём временную линию с 10-секундными интервалами
            for t in range(0, int(audio_duration) + 10, 10):
                min_val, sec_val = divmod(t, 60)
                f.write(f"{min_val}:{sec_val:02d} |")
                
                # Находим сегменты в этом 10-секундном интервале
                segments_in_interval = []
                for i, (start, end) in enumerate(final_segment_times):
                    if start >= t and start < t + 10:
                        segments_in_interval.append(f"S{i+1}")
                
                if segments_in_interval:
                    f.write(f" {', '.join(segments_in_interval)}")
                else:
                    f.write(" ---")
                f.write("\n")
        
        print(f"📄 Временная линия сохранена в {timeline_file}")
        
        # Финальная очистка
        Path(temp_audio).unlink(missing_ok=True)
        logger.info("🧹 Временные файлы очищены")
        
        logger.info("=" * 80)
        logger.info("✅ СЕССИЯ ПЕРЕВОДЧИКА ВИДЕО ЗАВЕРШЕНА УСПЕШНО")
        logger.info("=" * 80)
        
    except Exception as e:
        print(f"❌ ОШИБКА: {e}")
        logger.error(f"💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        logger.error("Полная трассировка ошибки:")
        logger.error(traceback.format_exc())
        
        logger.info("=" * 80)
        logger.info("❌ СЕССИЯ ПЕРЕВОДЧИКА ВИДЕО ЗАВЕРШЕНА С ОШИБКОЙ")
        logger.info("=" * 80)

if __name__ == "__main__":
    main()