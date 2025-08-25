#!/usr/bin/env python3
"""
Video-Translator: Основное приложение
Переводчик видео с английского на русский
"""

import os
import sys
import time
import uuid
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List

# Flask для веб-интерфейса
from flask import Flask, request, render_template, jsonify, send_file, redirect, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename
import threading

# Обработка видео и аудио
from moviepy.editor import VideoFileClip, AudioFileClip
from pydub import AudioSegment
from pydub.silence import split_on_silence

# API для распознавания, перевода и синтеза
import speech_recognition as sr
from translator_compat import translate_text, get_translator_status
from gtts import gTTS


# Утилиты
import logging
from datetime import datetime
from dotenv import load_dotenv
import json

# Загружаем переменные окружения
load_dotenv()


class VideoTranslator:
    """Основной класс для перевода видео"""

    def __init__(self):
        self.setup_logging()
        self.recognizer = sr.Recognizer()
        # self.translator заменен на translator_compat

        # Настройки из переменных окружения
        self.upload_folder = os.getenv('UPLOAD_FOLDER', 'uploads')
        self.output_folder = os.getenv('OUTPUT_FOLDER', 'outputs')
        self.max_file_size = int(os.getenv('MAX_FILE_SIZE_MB', '500')) * 1024 * 1024

        # Создание директорий
        os.makedirs(self.upload_folder, exist_ok=True)
        os.makedirs(self.output_folder, exist_ok=True)
        os.makedirs('temp', exist_ok=True)
        os.makedirs('logs', exist_ok=True)

        self.logger.info("VideoTranslator инициализирован")

    def setup_logging(self):
        """Настройка логирования"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('../logs/video_translator.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)

    def extract_audio(self, video_path: str) -> Optional[str]:
        """Извлечение аудио из видео"""
        try:
            self.logger.info(f"Извлечение аудио из {video_path}")

            # Загрузка видео
            video = VideoFileClip(video_path)
            audio = video.audio

            # Временный файл для аудио
            temp_audio_path = f"temp/audio_{uuid.uuid4().hex}.wav"

            # Сохранение аудио в формате WAV для лучшей совместимости
            audio.write_audiofile(
                temp_audio_path,
                codec='pcm_s16le',
                ffmpeg_params=['-ac', '1', '-ar', '16000']  # Моно, 16kHz
            )

            # Закрытие объектов для освобождения памяти
            audio.close()
            video.close()

            self.logger.info(f"Аудио извлечено: {temp_audio_path}")
            return temp_audio_path

        except Exception as e:
            self.logger.error(f"Ошибка извлечения аудио: {e}")
            return None

    def segment_audio(self, audio_path: str, min_silence_len: int = 1000, silence_thresh: int = -40) -> List[Dict]:
        """Сегментация аудио по паузам"""
        try:
            self.logger.info(f"Сегментация аудио: {audio_path}")

            # Загрузка аудио
            audio = AudioSegment.from_wav(audio_path)

            # Разделение по паузам
            chunks = split_on_silence(
                audio,
                min_silence_len=min_silence_len,
                silence_thresh=silence_thresh,
                keep_silence=500
            )

            segments = []
            current_time = 0

            for i, chunk in enumerate(chunks):
                if len(chunk) > 100:  # Игнорируем очень короткие фрагменты
                    # Сохранение сегмента
                    segment_path = f"temp/segment_{uuid.uuid4().hex}.wav"
                    chunk.export(segment_path, format="wav")

                    segments.append({
                        'id': i,
                        'path': segment_path,
                        'start_time': current_time / 1000.0,
                        'end_time': (current_time + len(chunk)) / 1000.0,
                        'duration': len(chunk) / 1000.0
                    })

                current_time += len(chunk)

            self.logger.info(f"Создано {len(segments)} сегментов")
            return segments

        except Exception as e:
            self.logger.error(f"Ошибка сегментации аудио: {e}")
            return []

    def transcribe_segment(self, segment_path: str, language: str = 'en-US') -> str:
        """Распознавание речи в сегменте"""
        try:
            with sr.AudioFile(segment_path) as source:
                # Настройка распознавателя
                self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                audio_data = self.recognizer.record(source)

                # Распознавание через Google Speech Recognition
                text = self.recognizer.recognize_google(audio_data, language=language)
                return text.strip()

        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            self.logger.error(f"Ошибка API распознавания речи: {e}")
            return ""
        except Exception as e:
            self.logger.error(f"Ошибка распознавания сегмента: {e}")
            return ""

    def translate_text(self, text: str, src_lang: str = 'en', dest_lang: str = 'ru') -> str:
        """Перевод текста через универсальный переводчик"""
        try:
            from translator_compat import translate_text as translate_func
            result = translate_func(text, src_lang, dest_lang)
            self.logger.info(f"Переведено: '{text[:50]}...' -> '{result[:50]}...'")
            return result
        except Exception as e:
            self.logger.error(f"Ошибка перевода: {e}")
            return text

    def synthesize_speech(self, text: str, lang: str = 'ru', slow: bool = False) -> Optional[str]:
        """Синтез речи из текста"""
        try:
            if not text.strip():
                return None

            # Создание TTS объекта
            tts = gTTS(text=text, lang=lang, slow=slow)

            # Временный файл для синтезированной речи
            temp_tts_path = f"temp/tts_{uuid.uuid4().hex}.mp3"
            tts.save(temp_tts_path)

            return temp_tts_path

        except Exception as e:
            self.logger.error(f"Ошибка синтеза речи: {e}")
            return None

    def adjust_audio_duration(self, audio_path: str, target_duration: float) -> str:
        """Подгонка длительности аудио под целевую"""
        try:
            audio = AudioSegment.from_file(audio_path)
            current_duration = len(audio) / 1000.0

            if abs(current_duration - target_duration) < 0.1:
                return audio_path  # Длительность уже подходит

            if current_duration > target_duration:
                # Ускоряем аудио
                speed_factor = current_duration / target_duration
                # Ограничиваем ускорение до разумных пределов
                speed_factor = min(speed_factor, 1.5)
                adjusted_audio = audio.speedup(playback_speed=speed_factor)
            else:
                # Добавляем тишину в конец
                silence_duration = int((target_duration - current_duration) * 1000)
                silence = AudioSegment.silent(duration=silence_duration)
                adjusted_audio = audio + silence

            # Сохранение подогнанного аудио
            adjusted_path = f"temp/adjusted_{uuid.uuid4().hex}.wav"
            adjusted_audio.export(adjusted_path, format="wav")

            return adjusted_path

        except Exception as e:
            self.logger.error(f"Ошибка подгонки длительности аудио: {e}")
            return audio_path

    def create_final_video(self, original_video_path: str, translated_audio_segments: List[Dict],
                           output_path: str) -> bool:
        """Создание финального видео с переведенным аудио"""
        try:
            self.logger.info("Создание финального видео...")

            # Загрузка оригинального видео
            video = VideoFileClip(original_video_path)

            # Объединение всех переведенных аудио сегментов
            combined_audio = AudioSegment.empty()

            for segment in translated_audio_segments:
                if segment.get('translated_audio_path'):
                    segment_audio = AudioSegment.from_file(segment['translated_audio_path'])
                    combined_audio += segment_audio
                else:
                    # Добавляем тишину если сегмент не переведен
                    silence_duration = int(segment['duration'] * 1000)
                    combined_audio += AudioSegment.silent(duration=silence_duration)

            # Сохранение объединенного аудио
            temp_combined_path = f"temp/combined_{uuid.uuid4().hex}.wav"
            combined_audio.export(temp_combined_path, format="wav")

            # Загрузка нового аудио
            new_audio = AudioFileClip(temp_combined_path)

            # Подгонка длительности аудио под видео
            if new_audio.duration > video.duration:
                new_audio = new_audio.subclip(0, video.duration)
            elif new_audio.duration < video.duration:
                # Добавление тишины в конец
                silence_duration = video.duration - new_audio.duration
                silence_audio = AudioSegment.silent(duration=int(silence_duration * 1000))
                silence_path = f"temp/silence_{uuid.uuid4().hex}.wav"
                silence_audio.export(silence_path, format="wav")

                silence_clip = AudioFileClip(silence_path)
                from moviepy.editor import concatenate_audioclips
                new_audio = concatenate_audioclips([new_audio, silence_clip])

            # Создание финального видео
            final_video = video.set_audio(new_audio)
            final_video.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                temp_audiofile='temp/temp_audio.m4a',
                remove_temp=True
            )

            # Закрытие объектов
            video.close()
            new_audio.close()
            final_video.close()

            self.logger.info(f"Финальное видео создано: {output_path}")
            return True

        except Exception as e:
            self.logger.error(f"Ошибка создания финального видео: {e}")
            return False

    def translate_video(self, video_path: str, output_path: str, progress_callback=None) -> bool:
        """Основная функция перевода видео"""
        try:
            self.logger.info(f"Начало перевода видео: {video_path}")

            # Обновление прогресса
            if progress_callback:
                progress_callback("Извлечение аудио из видео", 10)

            # 1. Извлечение аудио
            audio_path = self.extract_audio(video_path)
            if not audio_path:
                return False

            if progress_callback:
                progress_callback("Сегментация аудио", 20)

            # 2. Сегментация аудио
            segments = self.segment_audio(audio_path)
            if not segments:
                return False

            # 3. Обработка каждого сегмента
            translated_segments = []
            total_segments = len(segments)

            for i, segment in enumerate(segments):
                try:
                    # Обновление прогресса
                    progress = 20 + (i / total_segments) * 60
                    if progress_callback:
                        progress_callback(f"Обработка сегмента {i + 1}/{total_segments}", int(progress))

                    self.logger.info(f"Обработка сегмента {i + 1}/{total_segments}")

                    # Распознавание речи
                    original_text = self.transcribe_segment(segment['path'])
                    if not original_text:
                        self.logger.warning(f"Сегмент {i + 1}: речь не распознана")
                        translated_segments.append({
                            **segment,
                            'original_text': '',
                            'translated_text': '',
                            'translated_audio_path': None
                        })
                        continue

                    self.logger.info(f"Сегмент {i + 1} распознан: {original_text[:100]}...")

                    # Перевод текста
                    translated_text = self.translate_text(original_text)
                    self.logger.info(f"Сегмент {i + 1} переведен: {translated_text[:100]}...")

                    # Синтез речи
                    tts_path = self.synthesize_speech(translated_text)
                    if tts_path:
                        # Подгонка длительности
                        adjusted_tts_path = self.adjust_audio_duration(tts_path, segment['duration'])
                        tts_path = adjusted_tts_path

                    translated_segments.append({
                        **segment,
                        'original_text': original_text,
                        'translated_text': translated_text,
                        'translated_audio_path': tts_path
                    })

                except Exception as e:
                    self.logger.error(f"Ошибка обработки сегмента {i + 1}: {e}")
                    translated_segments.append({
                        **segment,
                        'original_text': '',
                        'translated_text': '',
                        'translated_audio_path': None
                    })

            if progress_callback:
                progress_callback("Создание финального видео", 85)

            # 4. Создание финального видео
            success = self.create_final_video(video_path, translated_segments, output_path)

            if progress_callback:
                progress_callback("Завершено" if success else "Ошибка", 100 if success else 0)

            # 5. Очистка временных файлов
            self.cleanup_temp_files([audio_path] + [seg['path'] for seg in segments] +
                                    [seg.get('translated_audio_path') for seg in translated_segments if
                                     seg.get('translated_audio_path')])

            self.logger.info(f"Перевод видео завершен: {'успешно' if success else 'с ошибкой'}")
            return success

        except Exception as e:
            self.logger.error(f"Критическая ошибка перевода видео: {e}")
            return False

    def cleanup_temp_files(self, file_list: List[str]):
        """Очистка временных файлов"""
        for file_path in file_list:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                self.logger.warning(f"Не удалось удалить временный файл {file_path}: {e}")


# Глобальные переменные для Flask приложения
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB
CORS(app)

# Инициализация переводчика
video_translator = VideoTranslator()

# Хранилище активных задач
active_tasks = {}


class TranslationTask:
    def __init__(self, task_id: str, input_file: str):
        self.task_id = task_id
        self.input_file = input_file
        self.status = 'pending'
        self.progress = 0
        self.current_stage = 'Инициализация'
        self.output_file = None
        self.error_message = None
        self.start_time = time.time()
        self.end_time = None


@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_video():
    """Загрузка и обработка видео"""
    try:
        if 'video' not in request.files:
            return jsonify({'error': 'Файл не найден'}), 400

        file = request.files['video']
        if file.filename == '':
            return jsonify({'error': 'Файл не выбран'}), 400

        # Проверка расширения файла
        allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({'error': f'Неподдерживаемый формат файла: {file_ext}'}), 400

        # Генерация ID задачи
        task_id = str(uuid.uuid4())

        # Сохранение файла
        filename = secure_filename(file.filename)
        input_path = os.path.join(video_translator.upload_folder, f"{task_id}_{filename}")
        file.save(input_path)

        # Создание задачи
        task = TranslationTask(task_id, input_path)
        active_tasks[task_id] = task

        # Запуск обработки в отдельном потоке
        thread = threading.Thread(target=process_video_async, args=(task,))
        thread.daemon = True
        thread.start()

        return jsonify({
            'task_id': task_id,
            'status': 'uploaded',
            'message': 'Файл загружен, начинается обработка'
        })

    except Exception as e:
        return jsonify({'error': f'Ошибка загрузки: {str(e)}'}), 500


@app.route('/status/<task_id>')
def get_status(task_id):
    """Получение статуса задачи"""
    if task_id not in active_tasks:
        return jsonify({'error': 'Задача не найдена'}), 404

    task = active_tasks[task_id]

    response = {
        'task_id': task_id,
        'status': task.status,
        'progress': task.progress,
        'current_stage': task.current_stage,
        'elapsed_time': int(time.time() - task.start_time)
    }

    if task.status == 'completed':
        response['output_file'] = task.output_file
        if task.end_time:
            response['total_time'] = int(task.end_time - task.start_time)
    elif task.status == 'error':
        response['error_message'] = task.error_message

    return jsonify(response)


@app.route('/download/<task_id>')
def download_result(task_id):
    """Скачивание результата"""
    if task_id not in active_tasks:
        return jsonify({'error': 'Задача не найдена'}), 404

    task = active_tasks[task_id]

    if task.status != 'completed' or not task.output_file:
        return jsonify({'error': 'Файл не готов'}), 400

    if not os.path.exists(task.output_file):
        return jsonify({'error': 'Файл не найден'}), 404

    return send_file(task.output_file, as_attachment=True,
                     download_name=f'translated_{task_id}.mp4')


def process_video_async(task: TranslationTask):
    """Асинхронная обработка видео"""
    try:
        task.status = 'processing'

        # Определение выходного файла
        output_filename = f"translated_{task.task_id}.mp4"
        output_path = os.path.join(video_translator.output_folder, output_filename)

        # Функция обновления прогресса
        def update_progress(stage: str, progress: int):
            task.current_stage = stage
            task.progress = progress

        # Запуск перевода
        success = video_translator.translate_video(
            video_path=task.input_file,
            output_path=output_path,
            progress_callback=update_progress
        )

        if success:
            task.status = 'completed'
            task.output_file = output_path
            task.progress = 100
            task.current_stage = 'Готово'
        else:
            task.status = 'error'
            task.error_message = 'Ошибка при обработке видео'

        task.end_time = time.time()

    except Exception as e:
        task.status = 'error'
        task.error_message = str(e)
        task.end_time = time.time()
        video_translator.logger.error(f"Ошибка асинхронной обработки: {e}")


if __name__ == '__main__':
    print("🚀 Запуск Video-Translator...")
    print(f"📂 Uploads: {video_translator.upload_folder}")
    print(f"📂 Outputs: {video_translator.output_folder}")
    print("🌐 Открываете http://127.0.0.1:5000")

    app.run(
        host='127.0.0.1',
        port=5000,
        debug=True,
        threaded=True
    )