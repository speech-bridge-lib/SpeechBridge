#!/usr/bin/env python3
"""
VideoTranslator: Обновленный основной класс для перевода видео
Использует модульную архитектуру core компонентов + сохранение текстов
"""

import logging
import time
from typing import Optional, Dict, List, Callable
import json
from datetime import datetime
from pathlib import Path

# Core модули
from core import VideoProcessor, AudioProcessor, SpeechRecognizer, SpeechSynthesizer
from translator_compat import translate_text, get_translator_status
from config import config


class VideoTranslator:
    """Основной класс для перевода видео с модульной архитектурой"""

    def __init__(self):
        self.config = config
        self.setup_logging()

        # Инициализация core компонентов
        self.video_processor = VideoProcessor()
        self.audio_processor = AudioProcessor()
        self.speech_recognizer = SpeechRecognizer()
        self.speech_synthesizer = SpeechSynthesizer()

        # Создание рабочих директорий
        self.config.create_directories()

        self.logger.info("VideoTranslator инициализирован с модульной архитектурой")
        self._log_component_status()

    def setup_logging(self):
        """Настройка логирования"""
        logging.basicConfig(
            level=getattr(logging, self.config.LOG_LEVEL),
            format=self.config.LOG_FORMAT,
            handlers=[
                logging.FileHandler(self.config.LOG_FILE),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _log_component_status(self):
        """Логирование статуса всех компонентов"""
        # Статус переводчика
        translator_status = get_translator_status()
        self.logger.info(f"Переводчик: {translator_status['type']} - {translator_status['description']}")

        # Статус TTS движков
        tts_engines = self.speech_synthesizer.test_tts_engines()
        available_tts = [name for name, available in tts_engines.items() if available]
        self.logger.info(f"Доступные TTS движки: {', '.join(available_tts) if available_tts else 'Нет'}")

        # Статус движков распознавания речи
        sr_engines = self.speech_recognizer.test_recognition_engines()
        available_sr = [name for name, available in sr_engines.items() if available]
        self.logger.info(f"Доступные SR движки: {', '.join(available_sr) if available_sr else 'Нет'}")

    def _format_time(self, seconds: float) -> str:
        """Форматирование времени в MM:SS или HH:MM:SS"""
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"

    def save_recognition_results(self, video_path: str, segments: List[Dict], output_dir: str = None) -> str:
        """
        Сохранение результатов распознавания речи

        Args:
            video_path: путь к исходному видео
            segments: список сегментов с распознанным текстом
            output_dir: директория для сохранения (по умолчанию outputs/)

        Returns:
            str: путь к сохраненному файлу
        """
        try:
            if output_dir is None:
                output_dir = self.config.OUTPUT_FOLDER

            # Создание имени файла на основе видео
            video_name = Path(video_path).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = Path(output_dir) / f"{video_name}_recognition_{timestamp}.txt"

            # Подготовка данных для сохранения
            recognition_data = {
                'source_video': str(Path(video_path).name),
                'processing_date': datetime.now().isoformat(),
                'total_segments': len(segments),
                'segments': []
            }

            # Текстовый вывод для удобного чтения
            text_content = []
            text_content.append(f"РАСПОЗНАВАНИЕ РЕЧИ")
            text_content.append(f"Видео: {Path(video_path).name}")
            text_content.append(f"Дата обработки: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
            text_content.append(f"Всего сегментов: {len(segments)}")
            text_content.append("=" * 60)
            text_content.append("")

            for segment in segments:
                segment_info = {
                    'id': segment.get('id', 0),
                    'start_time': segment.get('start_time', 0),
                    'end_time': segment.get('end_time', 0),
                    'duration': segment.get('duration', 0),
                    'text': segment.get('original_text', ''),
                    'status': 'recognized' if segment.get('original_text') else 'no_speech'
                }
                recognition_data['segments'].append(segment_info)

                # Форматированный текстовый вывод
                start_time = segment.get('start_time', 0)
                end_time = segment.get('end_time', 0)
                original_text = segment.get('original_text', '[речь не распознана]')

                text_content.append(f"[{self._format_time(start_time)} - {self._format_time(end_time)}]")
                text_content.append(f"{original_text}")
                text_content.append("")

            # Сохранение текстового файла
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(text_content))

            # Сохранение JSON файла для программного доступа
            json_file = output_file.with_suffix('.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(recognition_data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"Результаты распознавания сохранены: {output_file}")
            return str(output_file)

        except Exception as e:
            self.logger.error(f"Ошибка сохранения результатов распознавания: {e}")
            return ""

    def save_translation_results(self, video_path: str, segments: List[Dict], output_dir: str = None) -> str:
        """
        Сохранение результатов перевода

        Args:
            video_path: путь к исходному видео
            segments: список сегментов с переведенным текстом
            output_dir: директория для сохранения (по умолчанию outputs/)

        Returns:
            str: путь к сохраненному файлу
        """
        try:
            if output_dir is None:
                output_dir = self.config.OUTPUT_FOLDER

            # Создание имени файла
            video_name = Path(video_path).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = Path(output_dir) / f"{video_name}_translation_{timestamp}.txt"

            # Подготовка данных
            translation_data = {
                'source_video': str(Path(video_path).name),
                'processing_date': datetime.now().isoformat(),
                'source_language': self.config.SOURCE_LANGUAGE,
                'target_language': self.config.TARGET_LANGUAGE,
                'translator_type': self.get_translator_status()['type'],
                'total_segments': len(segments),
                'segments': []
            }

            # Текстовый вывод
            text_content = []
            text_content.append(f"ПЕРЕВОД ТЕКСТА")
            text_content.append(f"Видео: {Path(video_path).name}")
            text_content.append(f"Дата обработки: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
            text_content.append(f"Направление перевода: {self.config.SOURCE_LANGUAGE} → {self.config.TARGET_LANGUAGE}")
            text_content.append(f"Переводчик: {self.get_translator_status()['type']}")
            text_content.append(f"Всего сегментов: {len(segments)}")
            text_content.append("=" * 60)
            text_content.append("")

            for segment in segments:
                segment_info = {
                    'id': segment.get('id', 0),
                    'start_time': segment.get('start_time', 0),
                    'end_time': segment.get('end_time', 0),
                    'duration': segment.get('duration', 0),
                    'original_text': segment.get('original_text', ''),
                    'translated_text': segment.get('translated_text', ''),
                    'status': segment.get('status', 'unknown')
                }
                translation_data['segments'].append(segment_info)

                # Форматированный вывод
                start_time = segment.get('start_time', 0)
                end_time = segment.get('end_time', 0)
                original_text = segment.get('original_text', '[нет текста]')
                translated_text = segment.get('translated_text', '[нет перевода]')

                text_content.append(f"[{self._format_time(start_time)} - {self._format_time(end_time)}]")
                text_content.append(f"EN: {original_text}")
                text_content.append(f"RU: {translated_text}")
                text_content.append("")

            # Сохранение файлов
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(text_content))

            json_file = output_file.with_suffix('.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(translation_data, f, ensure_ascii=False, indent=2)

            self.logger.info(f"Результаты перевода сохранены: {output_file}")
            return str(output_file)

        except Exception as e:
            self.logger.error(f"Ошибка сохранения результатов перевода: {e}")
            return ""

    def save_complete_transcript(self, video_path: str, segments: List[Dict], output_dir: str = None) -> str:
        """
        Сохранение полного транскрипта (оригинал + перевод + временные метки)

        Args:
            video_path: путь к исходному видео
            segments: список сегментов с полной информацией
            output_dir: директория для сохранения

        Returns:
            str: путь к сохраненному файлу
        """
        try:
            if output_dir is None:
                output_dir = self.config.OUTPUT_FOLDER

            video_name = Path(video_path).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = Path(output_dir) / f"{video_name}_complete_{timestamp}.txt"

            # Статистика
            total_segments = len(segments)
            successful_segments = sum(1 for s in segments if s.get('original_text'))
            translated_segments = sum(1 for s in segments if s.get('translated_text'))

            text_content = []
            text_content.append(f"ПОЛНЫЙ ТРАНСКРИПТ И ПЕРЕВОД")
            text_content.append(f"Видео: {Path(video_path).name}")
            text_content.append(f"Дата обработки: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
            text_content.append(
                f"Общая длительность: {self._format_time(segments[-1].get('end_time', 0)) if segments else '0:00'}")
            text_content.append(f"Всего сегментов: {total_segments}")
            text_content.append(
                f"Распознано: {successful_segments} ({successful_segments / total_segments * 100:.1f}%)")
            text_content.append(
                f"Переведено: {translated_segments} ({translated_segments / total_segments * 100:.1f}%)")
            text_content.append("=" * 80)
            text_content.append("")

            for i, segment in enumerate(segments, 1):
                start_time = segment.get('start_time', 0)
                end_time = segment.get('end_time', 0)
                duration = segment.get('duration', 0)
                original_text = segment.get('original_text', '')
                translated_text = segment.get('translated_text', '')
                status = segment.get('status', 'unknown')

                text_content.append(f"СЕГМЕНТ {i}")
                text_content.append(
                    f"Время: {self._format_time(start_time)} - {self._format_time(end_time)} ({duration:.1f}s)")
                text_content.append(f"Статус: {status}")

                if original_text:
                    text_content.append(f"EN: {original_text}")
                else:
                    text_content.append(f"EN: [речь не распознана]")

                if translated_text:
                    text_content.append(f"RU: {translated_text}")
                else:
                    text_content.append(f"RU: [нет перевода]")

                text_content.append("-" * 40)
                text_content.append("")

            # Сохранение
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(text_content))

            self.logger.info(f"Полный транскрипт сохранен: {output_file}")
            return str(output_file)

        except Exception as e:
            self.logger.error(f"Ошибка сохранения полного транскрипта: {e}")
            return ""

    def translate_video(self, video_path: str, output_path: str, progress_callback: Callable = None,
                        save_texts: bool = True) -> bool:
        """
        Основная функция перевода видео с сохранением текстов

        Args:
            video_path: путь к исходному видео
            output_path: путь для сохранения результата
            progress_callback: функция для отслеживания прогресса
            save_texts: сохранять ли текстовые результаты

        Returns:
            bool: True при успехе, False при ошибке
        """
        start_time = time.time()

        try:
            self.logger.info(f"Начало перевода видео: {video_path} -> {output_path}")

            # Валидация входного файла
            validation = self.video_processor.validate_video_file(video_path)
            if not validation['valid']:
                error_msg = f"Валидация файла неудачна: {', '.join(validation['errors'])}"
                self.logger.error(error_msg)
                if progress_callback:
                    progress_callback("Ошибка валидации файла", 0)
                return False

            video_info = validation['info']
            self.logger.info(f"Видео информация: {video_info['duration']:.1f}s, "
                             f"{video_info['size']}, {video_info['file_size_mb']:.1f}MB")

            # 1. Извлечение аудио
            if progress_callback:
                progress_callback("Извлечение аудио из видео", 10)

            audio_path = self.video_processor.extract_audio(video_path)
            if not audio_path:
                if progress_callback:
                    progress_callback("Ошибка извлечения аудио", 0)
                return False

            # 2. Сегментация аудио
            if progress_callback:
                progress_callback("Сегментация аудио по паузам", 20)

            segments = self.audio_processor.segment_audio(audio_path)
            if not segments:
                if progress_callback:
                    progress_callback("Ошибка сегментации аудио", 0)
                return False

            self.logger.info(f"Создано {len(segments)} аудио сегментов")

            # 3. Обработка каждого сегмента
            translated_segments = []
            total_segments = len(segments)
            successful_segments = 0

            for i, segment in enumerate(segments):
                try:
                    # Обновление прогресса
                    progress = 20 + (i / total_segments) * 50
                    if progress_callback:
                        progress_callback(f"Обработка сегмента {i + 1}/{total_segments}", int(progress))

                    segment_start_time = time.time()
                    self.logger.debug(f"Обработка сегмента {i + 1}/{total_segments}")

                    # 3a. Распознавание речи
                    original_text = self.speech_recognizer.transcribe_audio(segment['path'])

                    if not original_text:
                        self.logger.warning(f"Сегмент {i + 1}: речь не распознана")
                        translated_segments.append({
                            **segment,
                            'original_text': '',
                            'translated_text': '',
                            'translated_audio_path': None,
                            'processing_time': time.time() - segment_start_time,
                            'status': 'no_speech'
                        })
                        continue

                    self.logger.debug(
                        f"Сегмент {i + 1} распознан ({len(original_text)} символов): {original_text[:100]}...")

                    # 3b. Перевод текста
                    translated_text = translate_text(
                        original_text,
                        self.config.SOURCE_LANGUAGE,
                        self.config.TARGET_LANGUAGE
                    )

                    if not translated_text:
                        translated_text = original_text  # Fallback на оригинальный текст

                    self.logger.debug(
                        f"Сегмент {i + 1} переведен ({len(translated_text)} символов): {translated_text[:100]}...")

                    # 3c. Синтез речи
                    tts_path = self.speech_synthesizer.synthesize_speech(
                        translated_text,
                        self.config.TTS_LANGUAGE
                    )

                    if tts_path:
                        # 3d. Подгонка длительности
                        adjusted_tts_path = self.audio_processor.adjust_audio_duration(
                            tts_path,
                            segment['duration']
                        )
                        tts_path = adjusted_tts_path

                    processing_time = time.time() - segment_start_time
                    successful_segments += 1

                    translated_segments.append({
                        **segment,
                        'original_text': original_text,
                        'translated_text': translated_text,
                        'translated_audio_path': tts_path,
                        'processing_time': processing_time,
                        'status': 'success' if tts_path else 'tts_failed'
                    })

                except Exception as e:
                    self.logger.error(f"Ошибка обработки сегмента {i + 1}: {e}")
                    translated_segments.append({
                        **segment,
                        'original_text': '',
                        'translated_text': '',
                        'translated_audio_path': None,
                        'processing_time': time.time() - segment_start_time if 'segment_start_time' in locals() else 0,
                        'status': 'error',
                        'error': str(e)
                    })

            # Статистика обработки
            self.logger.info(f"Обработка сегментов завершена: {successful_segments}/{total_segments} успешно")

            # 4. Сохранение текстовых результатов
            if save_texts and progress_callback:
                progress_callback("Сохранение текстовых результатов", 75)

            saved_files = []
            if save_texts:
                try:
                    # Сохранение результатов распознавания
                    recognition_file = self.save_recognition_results(video_path, translated_segments)
                    if recognition_file:
                        saved_files.append(('recognition', recognition_file))

                    # Сохранение результатов перевода
                    translation_file = self.save_translation_results(video_path, translated_segments)
                    if translation_file:
                        saved_files.append(('translation', translation_file))

                    # Сохранение полного транскрипта
                    transcript_file = self.save_complete_transcript(video_path, translated_segments)
                    if transcript_file:
                        saved_files.append(('transcript', transcript_file))

                except Exception as e:
                    self.logger.error(f"Ошибка сохранения текстовых файлов: {e}")

            if progress_callback:
                progress_callback("Создание финального видео", 85)

            # 5. Создание финального видео
            success = self.video_processor.create_final_video(video_path, translated_segments, output_path)

            if progress_callback:
                progress_callback("Завершено" if success else "Ошибка создания видео", 100 if success else 0)

            # 6. Очистка временных файлов
            self._cleanup_translation_files(audio_path, segments, translated_segments)

            # Финальная статистика
            total_time = time.time() - start_time
            self.logger.info(f"Перевод видео завершен за {total_time:.1f}s: {'успешно' if success else 'с ошибкой'}")

            if success and save_texts:
                self.logger.info(f"Сохранены текстовые файлы:")
                for file_type, file_path in saved_files:
                    self.logger.info(f"  - {file_type.title()}: {Path(file_path).name}")

            return success

        except Exception as e:
            total_time = time.time() - start_time
            self.logger.error(f"Критическая ошибка перевода видео за {total_time:.1f}s: {e}")
            if progress_callback:
                progress_callback("Критическая ошибка", 0)
            return False

    def _cleanup_translation_files(self, audio_path: str, segments: List[Dict], translated_segments: List[Dict]):
        """Очистка всех временных файлов после перевода"""
        files_to_cleanup = []

        # Основной аудио файл
        if audio_path:
            files_to_cleanup.append(audio_path)

        # Файлы сегментов
        for segment in segments:
            if segment.get('path'):
                files_to_cleanup.append(segment['path'])

        # Переведенные аудио файлы
        for segment in translated_segments:
            if segment.get('translated_audio_path'):
                files_to_cleanup.append(segment['translated_audio_path'])

        # Очистка через AudioProcessor
        segment_dicts = [{'path': path} for path in files_to_cleanup if path]
        self.audio_processor.cleanup_temp_segments(segment_dicts)

    def get_system_status(self) -> Dict:
        """Получение подробного статуса системы"""
        return {
            'translator': get_translator_status(),
            'speech_recognition_engines': self.speech_recognizer.test_recognition_engines(),
            'tts_engines': self.speech_synthesizer.test_tts_engines(),
            'available_voices': self.speech_synthesizer.get_available_voices(),
            'config': {
                'max_file_size_mb': self.config.MAX_FILE_SIZE_MB,
                'max_duration_minutes': self.config.MAX_DURATION_MINUTES,
                'allowed_extensions': list(self.config.ALLOWED_EXTENSIONS),
                'audio_sample_rate': self.config.AUDIO_SAMPLE_RATE,
                'video_codec': self.config.VIDEO_CODEC,
                'audio_codec': self.config.AUDIO_CODEC
            }
        }

    def validate_video_file(self, file_path: str) -> Dict[str, any]:
        """Валидация видео файла (делегирование к VideoProcessor)"""
        return self.video_processor.validate_video_file(file_path)

    def get_processing_estimate(self, video_path: str) -> Dict[str, float]:
        """
        Оценка времени обработки видео

        Args:
            video_path: путь к видео файлу

        Returns:
            dict: оценки времени для каждого этапа
        """
        try:
            video_info = self.video_processor.get_video_info(video_path)
            if not video_info:
                return {}

            duration = video_info['duration']

            # Примерные коэффициенты времени обработки
            estimates = {
                'audio_extraction': duration * 0.1,  # 10% от длительности видео
                'segmentation': duration * 0.05,  # 5% от длительности
                'speech_recognition': duration * 0.5,  # 50% (зависит от API)
                'translation': duration * 0.1,  # 10% (быстрый перевод)
                'speech_synthesis': duration * 0.3,  # 30% (зависит от TTS)
                'video_creation': duration * 0.2,  # 20% от длительности
            }

            estimates['total'] = sum(estimates.values())
            estimates['video_duration'] = duration

            return estimates

        except Exception as e:
            self.logger.error(f"Ошибка оценки времени обработки: {e}")
            return {}

    def get_translator_status(self) -> Dict:
        """Получение статуса переводчика"""
        return get_translator_status()

    def create_translation_report(self, segments: List[Dict]) -> Dict:
        """
        Создание отчета о переводе

        Args:
            segments: обработанные сегменты

        Returns:
            dict: детальный отчет о переводе
        """
        report = {
            'total_segments': len(segments),
            'successful_segments': 0,
            'failed_segments': 0,
            'empty_segments': 0,
            'total_text_length': 0,
            'total_translated_length': 0,
            'processing_times': [],
            'errors': []
        }

        for segment in segments:
            status = segment.get('status', 'unknown')

            if status == 'success':
                report['successful_segments'] += 1
            elif status == 'no_speech':
                report['empty_segments'] += 1
            else:
                report['failed_segments'] += 1
                if segment.get('error'):
                    report['errors'].append(segment['error'])

            # Статистика текста
            original_text = segment.get('original_text', '')
            translated_text = segment.get('translated_text', '')

            report['total_text_length'] += len(original_text)
            report['total_translated_length'] += len(translated_text)

            # Время обработки
            processing_time = segment.get('processing_time', 0)
            if processing_time > 0:
                report['processing_times'].append(processing_time)

        # Расчет статистики
        if report['processing_times']:
            report['average_processing_time'] = sum(report['processing_times']) / len(report['processing_times'])
            report['total_processing_time'] = sum(report['processing_times'])
        else:
            report['average_processing_time'] = 0
            report['total_processing_time'] = 0

        report['success_rate'] = (report['successful_segments'] / report['total_segments'] * 100) if report[
                                                                                                         'total_segments'] > 0 else 0

        return report


# Функции для обратной совместимости с существующим кодом
def extract_audio(video_path: str) -> Optional[str]:
    """Обратная совместимость: извлечение аудио"""
    translator = VideoTranslator()
    return translator.video_processor.extract_audio(video_path)


def segment_audio(audio_path: str) -> List[Dict]:
    """Обратная совместимость: сегментация аудио"""
    translator = VideoTranslator()
    return translator.audio_processor.segment_audio(audio_path)


def transcribe_segment(segment_path: str, language: str = 'en-US') -> str:
    """Обратная совместимость: распознавание речи"""
    translator = VideoTranslator()
    return translator.speech_recognizer.transcribe_audio(segment_path, language)


def synthesize_speech(text: str, lang: str = 'ru', slow: bool = False) -> Optional[str]:
    """Обратная совместимость: синтез речи"""
    translator = VideoTranslator()
    return translator.speech_synthesizer.synthesize_speech(text, lang)


if __name__ == "__main__":
    # Тестирование модуля
    print("=== Тестирование VideoTranslator (модульная версия) ===")

    translator = VideoTranslator()
    print("VideoTranslator инициализирован")

    # Статус системы
    status = translator.get_system_status()
    print(f"  Переводчик: {status['translator']['type']}")
    print(f"  SR движки: {[k for k, v in status['speech_recognition_engines'].items() if v]}")
    print(f"  TTS движки: {[k for k, v in status['tts_engines'].items() if v]}")

    # Тест с реальным файлом
    test_file = "test.mp4"
    if Path(test_file).exists():
        validation = translator.validate_video_file(test_file)
        print(f"Валидация {test_file}: {validation}")

        if validation['valid']:
            estimates = translator.get_processing_estimate(test_file)
            print(f"Оценка времени обработки: {estimates.get('total', 0):.1f}s")
    else:
        print(f"Тестовый файл {test_file} не найден")

    print("Тестирование завершено")
    print(f"Статус системы:")
    print(f"  Переводчик: {status['translator']['type']}")
    print(f"  SR движки: {[k for k, v in status['speech_recognition_engines'].items() if v]}")
    print(f"  TTS движки: {[k for k, v in status['tts_engines'].items() if v]}")

    # Тест с реальным файлом
    test_file = "test.mp4"
    if Path(test_file).exists():
        validation = translator.validate_video_file(test_file)
        print(f"Валидация {test_file}: {validation}")

        if validation['valid']:
            estimates = translator.get_processing_estimate(test_file)
            print(f"Оценка времени обработки: {estimates.get('total', 0):.1f}s")
    else:
        print(f"Тестовый файл {test_file} не найден")

print("Тестирование завершено")