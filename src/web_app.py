#!/usr/bin/env python3
"""
Flask веб-приложение для Video-Translator
Веб-интерфейс для загрузки и перевода видео
"""

import time
import uuid
import threading
from pathlib import Path
from typing import Dict, Optional

from flask import Flask, request, render_template, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Локальные модули
from config import config
from video_translator import VideoTranslator


class TranslationTask:
    """Модель задачи перевода"""

    def __init__(self, task_id: str, input_file: str, original_filename: str = ""):
        self.task_id = task_id
        self.input_file = input_file
        self.original_filename = original_filename
        self.status = 'pending'  # pending, processing, completed, error
        self.progress = 0
        self.current_stage = 'Инициализация'
        self.output_file: Optional[str] = None
        self.error_message: Optional[str] = None
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.file_info: Dict = {}
        # Новые параметры пользователя
        self.speech_engine: str = 'auto'
        self.output_format: str = 'TRANSLATION_ONLY'

    def to_dict(self) -> Dict:
        """Преобразование в словарь для JSON ответа"""
        data = {
            'task_id': self.task_id,
            'status': self.status,
            'progress': self.progress,
            'current_stage': self.current_stage,
            'elapsed_time': int(time.time() - self.start_time),
            'original_filename': self.original_filename,
            'file_info': self.file_info,
            'settings': {
                'speech_engine': self.speech_engine,
                'output_format': self.output_format
            }
        }

        if self.status == 'completed':
            data['output_file'] = self.output_file
            if self.end_time:
                data['total_time'] = int(self.end_time - self.start_time)
        elif self.status == 'error':
            data['error_message'] = self.error_message

        return data


class VideoTranslatorApp:
    """Flask приложение для Video-Translator"""

    def __init__(self):
        self.app = Flask(__name__,
                         template_folder=str(config.TEMPLATES_FOLDER),
                         static_folder=str(config.STATIC_FOLDER))
        self.config = config
        self.setup_app()
        self.video_translator = VideoTranslator()
        self.active_tasks: Dict[str, TranslationTask] = {}
        self.setup_routes()

        print(f"Flask приложение инициализировано")
        print(f"Templates: {config.TEMPLATES_FOLDER}")
        print(f"Static: {config.STATIC_FOLDER}")

    def setup_app(self):
        """Настройка Flask приложения"""
        self.app.config.update(
            SECRET_KEY=self.config.SECRET_KEY,
            MAX_CONTENT_LENGTH=self.config.MAX_CONTENT_LENGTH,
            UPLOAD_FOLDER=str(self.config.UPLOAD_FOLDER),
            OUTPUT_FOLDER=str(self.config.OUTPUT_FOLDER)
        )
        CORS(self.app)

    def setup_routes(self):
        """Настройка маршрутов"""

        @self.app.route('/')
        def index():
            """Главная страница"""
            translator_status = self.video_translator.get_translator_status()
            return render_template('index.html',
                                   max_file_size=self.config.MAX_FILE_SIZE_MB,
                                   allowed_extensions=list(self.config.ALLOWED_EXTENSIONS),
                                   translator_status=translator_status)

        @self.app.route('/api/upload', methods=['POST'])
        def upload_video():
            """Загрузка и обработка видео с настройками"""
            try:
                # Проверка наличия файла
                if 'video' not in request.files:
                    return jsonify({'error': 'Файл не найден в запросе'}), 400

                file = request.files['video']
                if file.filename == '':
                    return jsonify({'error': 'Файл не выбран'}), 400

                # Получение настроек пользователя
                speech_engine = request.form.get('speech_engine', 'auto')
                output_format = request.form.get('output_format', 'TRANSLATION_ONLY')
                
                self.app.logger.info(f"📋 Настройки пользователя: engine={speech_engine}, format={output_format}")

                # Валидация имени файла
                if not self.config.is_allowed_file(file.filename):
                    return jsonify({
                        'error': f'Неподдерживаемый формат файла. Разрешены: {", ".join(self.config.ALLOWED_EXTENSIONS)}'
                    }), 400

                # Генерация ID задачи и безопасного имени файла
                task_id = str(uuid.uuid4())
                original_filename = file.filename
                safe_filename = secure_filename(file.filename)

                # Создание уникального имени файла
                file_extension = Path(safe_filename).suffix
                unique_filename = f"{task_id}_{safe_filename}"
                input_path = self.config.UPLOAD_FOLDER / unique_filename

                # Сохранение файла
                file.save(str(input_path))

                # Валидация загруженного файла
                validation = self.video_translator.validate_video_file(str(input_path))
                if not validation['valid']:
                    # Удаляем невалидный файл
                    input_path.unlink(missing_ok=True)
                    return jsonify({
                        'error': 'Ошибка валидации файла',
                        'details': validation['errors']
                    }), 400

                # ИСПРАВЛЕНО: НЕ меняем speech_engine='auto' на конкретный движок!
                # Пусть VideoTranslator сам разберется с автоматическим выбором всех движков
                file_size_mb = file.content_length / 1024 / 1024 if file.content_length else 0
                
                if speech_engine == 'auto':
                    self.app.logger.info(f"🤖 Автоматический режим: VideoTranslator попробует все движки для файла {file_size_mb:.1f}MB")
                else:
                    self.app.logger.info(f"🎯 Ручной выбор движка: {speech_engine} для файла {file_size_mb:.1f}MB")

                # Создание задачи
                task = TranslationTask(task_id, str(input_path), original_filename)
                task.file_info = validation['info']
                task.speech_engine = speech_engine
                task.output_format = output_format
                self.active_tasks[task_id] = task

                # Запуск обработки в отдельном потоке
                thread = threading.Thread(target=self.process_video_async, args=(task,))
                thread.daemon = True
                thread.start()

                return jsonify({
                    'task_id': task_id,
                    'status': 'uploaded',
                    'message': 'Файл загружен, начинается обработка',
                    'file_info': validation['info'],
                    'settings': {
                        'speech_engine': speech_engine,
                        'output_format': output_format
                    }
                })

            except Exception as e:
                self.app.logger.error(f"Ошибка загрузки файла: {e}")
                return jsonify({'error': f'Ошибка загрузки: {str(e)}'}), 500

        @self.app.route('/api/status/<task_id>')
        def get_status(task_id):
            """Получение статуса задачи"""
            if task_id not in self.active_tasks:
                return jsonify({'error': 'Задача не найдена'}), 404

            task = self.active_tasks[task_id]
            return jsonify(task.to_dict())

        @self.app.route('/api/download/<task_id>')
        def download_result(task_id):
            """Скачивание результата"""
            if task_id not in self.active_tasks:
                return jsonify({'error': 'Задача не найдена'}), 404

            task = self.active_tasks[task_id]

            if task.status != 'completed' or not task.output_file:
                return jsonify({'error': 'Файл не готов к скачиванию'}), 400

            output_path = Path(task.output_file)
            if not output_path.exists():
                return jsonify({'error': 'Файл результата не найден'}), 404

            # Генерируем имя для скачивания
            original_name = Path(task.original_filename).stem
            download_name = f'{original_name}_translated.mp4'

            return send_file(
                str(output_path),
                as_attachment=True,
                download_name=download_name,
                mimetype='video/mp4'
            )

        @self.app.route('/api/tasks')
        def list_tasks():
            """Получение списка всех задач"""
            tasks_data = {}
            for task_id, task in self.active_tasks.items():
                tasks_data[task_id] = task.to_dict()

            return jsonify({
                'total_tasks': len(tasks_data),
                'tasks': tasks_data
            })

        @self.app.route('/api/delete/<task_id>', methods=['DELETE'])
        def delete_task(task_id):
            """Удаление задачи и связанных файлов"""
            if task_id not in self.active_tasks:
                return jsonify({'error': 'Задача не найдена'}), 404

            task = self.active_tasks[task_id]

            # Можно удалять только завершенные или ошибочные задачи
            if task.status in ['processing']:
                return jsonify({'error': 'Нельзя удалить задачу в процессе обработки'}), 400

            try:
                # Удаление файлов
                if task.input_file and Path(task.input_file).exists():
                    Path(task.input_file).unlink()

                if task.output_file and Path(task.output_file).exists():
                    Path(task.output_file).unlink()

                # Удаление из памяти
                del self.active_tasks[task_id]

                return jsonify({'message': 'Задача удалена'})

            except Exception as e:
                self.app.logger.error(f"Ошибка удаления задачи {task_id}: {e}")
                return jsonify({'error': 'Ошибка удаления задачи'}), 500

        @self.app.route('/api/translator/status')
        def translator_status():
            """Получение статуса переводчика"""
            status = self.video_translator.get_translator_status()
            return jsonify(status)

        @self.app.route('/health')
        def health_check():
            """Проверка здоровья приложения"""
            return jsonify({
                'status': 'healthy',
                'timestamp': time.time(),
                'active_tasks': len(self.active_tasks),
                'translator': self.video_translator.get_translator_status()['type']
            })

        # API для управления настройками распознавания
        @self.app.route('/api/recognition/models')
        def get_recognition_models():
            """Получение доступных моделей распознавания"""
            try:
                speech_recognizer = self.video_translator.speech_recognizer
                
                return jsonify({
                    'available_models': speech_recognizer.get_available_models(),
                    'current_settings': speech_recognizer.get_current_settings(),
                    'engine_status': speech_recognizer.get_engine_status()
                })
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/recognition/whisper/model', methods=['POST'])
        def set_whisper_model():
            """Установка модели Whisper"""
            try:
                data = request.get_json()
                if not data or 'model' not in data:
                    return jsonify({'error': 'Модель не указана'}), 400

                model = data['model']
                speech_recognizer = self.video_translator.speech_recognizer
                
                success = speech_recognizer.set_whisper_model(model)
                
                if success:
                    return jsonify({
                        'status': 'success',
                        'message': f'Модель Whisper установлена: {model}',
                        'current_settings': speech_recognizer.get_current_settings()
                    })
                else:
                    return jsonify({'error': f'Не удалось установить модель: {model}'}), 400
                    
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/recognition/engine', methods=['POST'])
        def set_recognition_engine():
            """Установка предпочтительного движка распознавания"""
            try:
                data = request.get_json()
                if not data or 'engine' not in data:
                    return jsonify({'error': 'Движок не указан'}), 400

                engine = data['engine']
                speech_recognizer = self.video_translator.speech_recognizer
                
                success = speech_recognizer.set_preferred_engine(engine)
                
                if success:
                    return jsonify({
                        'status': 'success',
                        'message': f'Движок установлен: {engine}',
                        'current_settings': speech_recognizer.get_current_settings()
                    })
                else:
                    return jsonify({'error': f'Не удалось установить движок: {engine}'}), 400
                    
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        @self.app.route('/api/recognition/test', methods=['POST'])
        def test_recognition():
            """Тест распознавания с выбранным движком и моделью"""
            try:
                # Этот endpoint можно использовать для тестирования с коротким аудио
                data = request.get_json()
                engine = data.get('engine')
                model = data.get('model')
                
                speech_recognizer = self.video_translator.speech_recognizer
                
                # Возвращаем информацию о том, что будет использоваться
                return jsonify({
                    'test_settings': {
                        'engine': engine or speech_recognizer.preferred_engine,
                        'model': model or speech_recognizer.current_whisper_model,
                        'available': speech_recognizer.available_engines
                    },
                    'message': 'Настройки готовы для тестирования'
                })
                
            except Exception as e:
                return jsonify({'error': str(e)}), 500

        # Обработчики ошибок
        @self.app.errorhandler(413)
        def file_too_large(e):
            return jsonify({
                'error': f'Файл слишком большой. Максимальный размер: {self.config.MAX_FILE_SIZE_MB}MB'
            }), 413

        @self.app.errorhandler(404)
        def not_found(e):
            return jsonify({'error': 'Страница не найдена'}), 404

        @self.app.errorhandler(500)
        def internal_error(e):
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

    def process_video_async(self, task: TranslationTask):
        """Асинхронная обработка видео с таймаутом"""
        import threading
        import time
        
        # Флаг для отслеживания завершения
        processing_complete = threading.Event()
        timeout_occurred = threading.Event()
        
        def timeout_monitor():
            """Мониторинг таймаута в отдельном потоке"""
            if not processing_complete.wait(timeout=600):  # 10 минут
                timeout_occurred.set()
                self.app.logger.error(f"⏰ Таймаут задачи {task.task_id} (10 минут)")
                task.status = 'error'
                task.error_message = "Обработка видео превысила лимит времени (10 минут)"
        
        # Запускаем мониторинг таймаута
        timeout_thread = threading.Thread(target=timeout_monitor, daemon=True)
        timeout_thread.start()
        
        try:
            task.status = 'processing'
            self.app.logger.info(f"🚀 Начало обработки задачи {task.task_id} с таймаутом 10 мин")

            # Определение выходного файла
            output_filename = f"translated_{task.task_id}.mp4"
            output_path = self.config.OUTPUT_FOLDER / output_filename
            task.output_file = str(output_path)

            # Функция обновления прогресса с детальным логированием
            def update_progress(stage: str, progress: int):
                task.current_stage = stage
                task.progress = progress
                self.app.logger.info(f"📊 Задача {task.task_id}: {stage} ({progress}%)")

            # Запуск перевода с логированием
            self.app.logger.info(f"🎬 Запуск перевода: {task.input_file} -> {output_path}")
            
            # Проверяем таймаут перед запуском
            if timeout_occurred.is_set():
                raise TimeoutError("Обработка видео превысила лимит времени")
            
            success = self.video_translator.translate_video(
                video_path=task.input_file,
                output_path=str(output_path),
                progress_callback=update_progress,
                speech_engine=task.speech_engine,
                output_format=task.output_format
            )
            
            # Проверяем таймаут после завершения
            if timeout_occurred.is_set():
                raise TimeoutError("Обработка видео превысила лимит времени")
            
            self.app.logger.info(f"🏁 Перевод завершён, успех: {success}")

            if success:
                task.status = 'completed'
                task.progress = 100
                task.current_stage = 'Готово'
                self.app.logger.info(f"✅ Задача {task.task_id} завершена успешно")
            else:
                task.status = 'error'
                task.error_message = 'Ошибка при обработке видео'
                self.app.logger.error(f"❌ Задача {task.task_id} завершена с ошибкой")

            task.end_time = time.time()

        except TimeoutError as e:
            task.status = 'error'
            task.error_message = f"Таймаут: {str(e)}"
            task.end_time = time.time()
            self.app.logger.error(f"⏰ Задача {task.task_id} прервана по таймауту: {e}")
            
        except Exception as e:
            task.status = 'error'
            task.error_message = str(e)
            task.end_time = time.time()
            self.app.logger.error(f"💥 Критическая ошибка в задаче {task.task_id}: {e}")
            
        finally:
            # Сигнализируем о завершении обработки
            processing_complete.set()
            self.app.logger.info(f"🏁 Обработка задачи {task.task_id} завершена")

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Очистка старых задач"""
        current_time = time.time()
        tasks_to_remove = []

        for task_id, task in self.active_tasks.items():
            if task.status in ['completed', 'error']:
                age_hours = (current_time - task.start_time) / 3600
                if age_hours > max_age_hours:
                    tasks_to_remove.append(task_id)

        for task_id in tasks_to_remove:
            try:
                task = self.active_tasks[task_id]
                # Удаление файлов
                if task.input_file and Path(task.input_file).exists():
                    Path(task.input_file).unlink()
                if task.output_file and Path(task.output_file).exists():
                    Path(task.output_file).unlink()
                # Удаление из памяти
                del self.active_tasks[task_id]
                self.app.logger.info(f"Очищена старая задача {task_id}")
            except Exception as e:
                self.app.logger.error(f"Ошибка очистки задачи {task_id}: {e}")

    def get_app(self) -> Flask:
        """Получение экземпляра Flask приложения"""
        return self.app

    def run(self, host: str = '127.0.0.1', port: int = 5000, debug: bool = True):
        """Запуск приложения"""
        self.app.logger.info(f"Запуск Video-Translator на {host}:{port}")
        self.app.run(host=host, port=port, debug=debug, threaded=True)


def create_app() -> Flask:
    """Фабрика приложений Flask"""
    app_instance = VideoTranslatorApp()
    return app_instance.get_app()


if __name__ == "__main__":
    print("=== Тестирование Flask приложения ===")

    app = VideoTranslatorApp()
    print(f"Приложение создано")
    print(f"Активных задач: {len(app.active_tasks)}")
    print(f"Конфигурация загружена: {app.config}")

    # Тестовый запуск
    print("Запуск тестового сервера...")
    app.run(debug=True)