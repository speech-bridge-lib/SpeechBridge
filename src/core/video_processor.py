#!/usr/bin/env python3
"""
VideoProcessor: Модуль обработки видео файлов
Извлечение аудио, создание финального видео с переведенной аудиодорожкой
"""

import os
import logging
import tempfile
from pathlib import Path
from typing import Optional, Tuple, List

# Fix для multiprocessing и MoviePy на macOS
os.environ['IMAGEIO_FFMPEG_EXE'] = '/usr/local/bin/ffmpeg'  # Правильный путь к ffmpeg
os.environ['FFMPEG_BINARY'] = 'ffmpeg'  # Общий fallback

import moviepy.editor as mp
from pydub import AudioSegment
import uuid

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Улучшенный процессор видео с правильным сохранением аудио"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Временные файлы для отслеживания
        self.temp_files = []

    def extract_audio(self, video_path: str) -> Tuple[Optional[str], dict]:
        """
        Извлекает аудио из видео файла

        Returns:
            tuple: (путь к аудио файлу, информация о видео)
        """
        try:
            if not Path(video_path).exists():
                raise FileNotFoundError(f"Видео файл не найден: {video_path}")

            self.logger.info(f"Извлечение аудио из {video_path}")

            # Загружаем видео
            video = mp.VideoFileClip(video_path)

            # Получаем информацию о видео
            video_info = {
                "duration": video.duration,
                "fps": video.fps,
                "size": video.size,
                "has_audio": video.audio is not None,
                "file_size": Path(video_path).stat().st_size
            }

            if not video.audio:
                self.logger.error("Видео не содержит аудио дорожку")
                video.close()
                return None, video_info

            # Создаем уникальный временный файл для аудио
            audio_filename = f"audio_{uuid.uuid4().hex}.wav"
            temp_dir = Path(__file__).parent.parent / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            audio_path = temp_dir / audio_filename

            # Извлекаем аудио в оптимальном качестве для распознавания речи
            video.audio.write_audiofile(
                str(audio_path),
                codec='pcm_s16le',  # 16-bit PCM
                ffmpeg_params=['-ac', '1', '-ar', '16000'],  # моно, 16kHz
                verbose=False,
                logger=None
            )

            # Добавляем в список для очистки
            self.temp_files.append(str(audio_path))

            video.close()
            self.logger.info(f"Аудио успешно извлечено: {audio_path}")

            return str(audio_path), video_info

        except Exception as e:
            self.logger.error(f"Ошибка извлечения аудио: {e}")
            if 'video' in locals():
                video.close()
            return None, {}

    def create_final_video(self, original_video_path: str, translated_audio_segments: List[dict],
                           output_path: str, preserve_original_audio: bool = False) -> bool:
        """
        Создает финальное видео с переведенной аудио дорожкой

        Args:
            original_video_path: путь к оригинальному видео
            translated_audio_segments: список сегментов с переведенным аудио
            output_path: путь для сохранения
            preserve_original_audio: сохранить оригинальное аудио как фон

        Returns:
            bool: успех операции
        """
        video = None
        final_audio_path = None

        try:
            self.logger.info("=== СОЗДАНИЕ ФИНАЛЬНОГО ВИДЕО ===")
            self.logger.info("Загрузка оригинального видео...")

            # СНАЧАЛА загружаем оригинальное видео
            video = mp.VideoFileClip(original_video_path)

            # ТЕПЕРЬ можем проводить диагностику с использованием video
            self.logger.info(f"Получено сегментов: {len(translated_audio_segments)}")
            self.logger.info(f"Длительность видео: {video.duration:.2f}s")

            # Диагностика полученных сегментов
            segments_with_audio = 0
            for i, segment in enumerate(translated_audio_segments):
                audio_path = segment.get('translated_audio_path')
                if audio_path and Path(audio_path).exists():
                    segments_with_audio += 1
                    file_size = Path(audio_path).stat().st_size
                    self.logger.info(f"Сегмент {i}: ЕСТЬ аудио файл ({file_size} байт) - {audio_path}")
                else:
                    self.logger.warning(f"Сегмент {i}: НЕТ аудио файла - {audio_path}")

            self.logger.info(f"Сегментов с аудио файлами: {segments_with_audio}/{len(translated_audio_segments)}")

            # Проверка наличия сегментов с аудио
            if not translated_audio_segments or segments_with_audio == 0:
                self.logger.warning("Нет переведенных аудио сегментов, создаем видео без звука")
                final_video = video.without_audio()
            else:
                self.logger.info("Переходим к объединению аудио сегментов...")

                # Создаем финальную аудио дорожку
                final_audio_path = self._combine_translated_audio(
                    translated_audio_segments,
                    video.duration,
                    preserve_original_audio,
                    video.audio if preserve_original_audio else None
                )

                if final_audio_path and Path(final_audio_path).exists():
                    self.logger.info(f"✓ Переведенное аудио создано: {final_audio_path}")

                    # Проверим размер файла
                    file_size = Path(final_audio_path).stat().st_size
                    self.logger.info(f"  Размер файла: {file_size} байт")
                    #***************************************************************
                    if file_size > 1000:  # Минимум 1KB
                        # Используем FFmpeg напрямую для избежания проблем с MoviePy
                        try:
                            import subprocess

                            self.logger.info("Использование FFmpeg для объединения видео и аудио")

                            # Создаем временное видео без звука
                            temp_video_path = output_path.replace('.mp4', '_temp_silent.mp4')
                            silent_video = video.without_audio()
                            silent_video.write_videofile(
                                temp_video_path,
                                codec='libx264',
                                verbose=False,
                                logger=None
                            )
                            silent_video.close()

                            # Объединяем через FFmpeg
                            cmd = [
                                'ffmpeg', '-y',
                                '-i', temp_video_path,  # видео без звука
                                '-i', final_audio_path,  # аудио дорожка
                                '-c:v', 'copy',  # копируем видео
                                '-c:a', 'aac',  # кодируем аудио в AAC
                                '-shortest',  # обрезаем по короткому
                                output_path
                            ]

                            result = subprocess.run(cmd, capture_output=True, text=True)

                            if result.returncode == 0:
                                self.logger.info("✓ Видео и аудио объединены через FFmpeg")

                                # Удаляем временный файл
                                Path(temp_video_path).unlink()

                                # Пропускаем стандартную процедуру экспорта
                                video.close()

                                # Проверяем результат
                                if Path(output_path).exists():
                                    output_size = Path(output_path).stat().st_size
                                    self.logger.info(f"✓ Финальное видео создано: {output_path}")
                                    self.logger.info(f"  Размер файла: {output_size / (1024 * 1024):.1f} MB")

                                    # Проверяем наличие аудио
                                    try:
                                        test_video = mp.VideoFileClip(output_path)
                                        has_audio = test_video.audio is not None
                                        self.logger.info(f"  Содержит аудио: {has_audio}")
                                        if has_audio:
                                            self.logger.info(f"  Длительность аудио: {test_video.audio.duration:.2f}s")
                                        test_video.close()
                                    except Exception as e:
                                        self.logger.warning(f"Не удалось проверить аудио в результате: {e}")

                                    return True
                                else:
                                    self.logger.error("Файл не создан после FFmpeg")

                            else:
                                self.logger.error(f"FFmpeg ошибка: {result.stderr}")
                                self.logger.warning("Создаем видео без звука как fallback")
                                # Переименовываем временное видео в финальное
                                Path(temp_video_path).rename(output_path)
                                video.close()
                                return True

                        except Exception as ffmpeg_error:
                            self.logger.error(f"Ошибка FFmpeg: {ffmpeg_error}")
                            self.logger.warning("Создаем видео без звука")
                            final_video = video.without_audio()

                    else:
                        self.logger.warning("Аудио файл слишком маленький, создаем без звука")
                        final_video = video.without_audio()

                    # if file_size > 1000:  # Минимум 1KB
                    #     # Загружаем переведенное аудио
                    #     translated_audio = mp.AudioFileClip(final_audio_path)
                    #
                    #
                    #     # Проверяем длительность
                    #     self.logger.info(f"  Длительность аудио: {translated_audio.duration:.2f}s")
                    #     self.logger.info(f"  Длительность видео: {video.duration:.2f}s")
                    #
                    #     # Создаем финальное видео с переведенным аудио
                    #     final_video = video.set_audio(translated_audio)
                    #     translated_audio.close()
                    #
                    #     self.logger.info("✓ Видео объединено с переведенным аудио")
                    # else:
                    #     self.logger.warning("Аудио файл слишком маленький, создаем без звука")
                    #     final_video = video.without_audio()
                else:
                    self.logger.warning("Не удалось создать переведенное аудио, создаем без звука")
                    final_video = video.without_audio()

            # Сохраняем финальное видео
            self.logger.info("Экспорт финального видео...")
            final_video.write_videofile(
                output_path,
                codec='libx264',
                audio_codec='aac',
                remove_temp=True,
                verbose=False,
                logger=None
            )

            # Закрываем все клипы
            final_video.close()
            video.close()

            # Проверяем результат
            if Path(output_path).exists():
                output_size = Path(output_path).stat().st_size
                self.logger.info(f"✓ Финальное видео создано: {output_path}")
                self.logger.info(f"  Размер файла: {output_size / (1024 * 1024):.1f} MB")

                # Быстрая проверка наличия аудио в результате
                try:
                    test_video = mp.VideoFileClip(output_path)
                    has_audio = test_video.audio is not None
                    self.logger.info(f"  Содержит аудио: {has_audio}")
                    if has_audio:
                        self.logger.info(f"  Длительность аудио: {test_video.audio.duration:.2f}s")
                    test_video.close()
                except Exception as e:
                    self.logger.warning(f"Не удалось проверить аудио в результате: {e}")
            else:
                self.logger.error("✗ Финальное видео не создано!")
                return False

            # Очистка временных файлов
            if final_audio_path and Path(final_audio_path).exists():
                try:
                    Path(final_audio_path).unlink()
                    self.logger.debug(f"Удален временный аудио файл: {final_audio_path}")
                except Exception as e:
                    self.logger.warning(f"Ошибка удаления временного файла: {e}")

            return True

        except Exception as e:
            self.logger.error(f"КРИТИЧЕСКАЯ ОШИБКА создания финального видео: {e}")
            import traceback
            self.logger.error(f"Трассировка:\n{traceback.format_exc()}")

            # Закрытие ресурсов в случае ошибки
            if video:
                try:
                    video.close()
                except Exception as cleanup_e:
                    self.logger.warning(f"Ошибка закрытия видео: {cleanup_e}")

            # Очистка временных файлов
            if final_audio_path and Path(final_audio_path).exists():
                try:
                    Path(final_audio_path).unlink()
                except Exception as cleanup_e:
                    self.logger.warning(f"Ошибка удаления временного файла: {cleanup_e}")

            return False

    def _combine_translated_audio(self, segments: List[dict], video_duration: float,
                                  preserve_original: bool = False, original_audio=None) -> Optional[str]:
        """
        Объединяет переведенные аудио сегменты в единую дорожку

        Args:
            segments: список сегментов с переведенным аудио
            video_duration: длительность оригинального видео
            preserve_original: микшировать с оригинальным аудио
            original_audio: оригинальная аудио дорожка

        Returns:
            str: путь к объединенному аудио файлу
        """
        try:
            self.logger.info(f"=== ДИАГНОСТИКА ВХОДНЫХ СЕГМЕНТОВ ===")
            for i, segment in enumerate(segments):
                self.logger.info(f"Сегмент {i}: success={segment.get('success')}, "
                                 f"status={segment.get('status')}, "
                                 f"audio_path={segment.get('translated_audio_path')}")
                if segment.get('translated_audio_path'):
                    exists = Path(segment['translated_audio_path']).exists()
                    self.logger.info(f"  Файл существует: {exists}")
            #         ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
            # Создаем базовую тишину длиной как оригинальное видео
            final_audio = AudioSegment.silent(duration=int(video_duration * 1000))

            self.logger.info(f"Объединение {len(segments)} аудио сегментов...")

            successful_segments = 0
            for segment in segments:
                try:
                    # Более надежная проверка сегмента
                    audio_path = segment.get('translated_audio_path')
                    success = segment.get('success')
                    status = segment.get('status')

                    # Проверяем наличие аудио файла и успешность обработки
                    if not audio_path:
                        self.logger.debug(f"Пропуск сегмента: нет translated_audio_path")
                        continue

                    if not Path(audio_path).exists():
                        self.logger.warning(f"Пропуск сегмента: файл не найден {audio_path}")
                        continue

                    # Проверяем статус успешности (более гибко)
                    if success is False or status == 'error' or status == 'no_speech':
                        self.logger.debug(f"Пропуск сегмента: success={success}, status={status}")
                        continue

                    self.logger.debug(f"Обработка валидного сегмента: {audio_path}")

                    # if not segment.get('translated_audio_path') or not segment.get('success', False):
                    #     continue

                    audio_path = segment['translated_audio_path']
                    if not Path(audio_path).exists():
                        self.logger.warning(f"Переведенный аудио файл не найден: {audio_path}")
                        continue

                    # Загружаем переведенный сегмент
                    segment_audio = AudioSegment.from_file(audio_path)
                    self.logger.debug(f"Загружен сегмент аудио: длительность={len(segment_audio)}ms, громкость={segment_audio.dBFS:.1f}dBFS")

                    # Получаем временные метки
                    start_time = segment.get('start_time', 0) * 1000  # в миллисекундах
                    end_time = segment.get('end_time', start_time / 1000 + len(segment_audio) / 1000) * 1000

                    # Обрезаем если нужно
                    max_duration = end_time - start_time
                    if len(segment_audio) > max_duration:
                        segment_audio = segment_audio[:int(max_duration)]

                    # Нормализуем сегмент перед добавлением, если он очень тихий
                    if segment_audio.dBFS < -50:
                        segment_audio = segment_audio.normalize(headroom=20.0)
                        self.logger.info(f"Сегмент нормализован: {segment_audio.dBFS:.1f}dBFS")

                    # Заменяем участок тишины на аудио (более надежно чем overlay)
                    try:
                        # Разбиваем финальное аудио на три части: до, вместо, после
                        before = final_audio[:int(start_time)]
                        after = final_audio[int(end_time):]
                        
                        # Собираем финальное аудио
                        final_audio = before + segment_audio + after
                        successful_segments += 1
                        
                        self.logger.debug(f"Сегмент заменен: {start_time / 1000:.1f}-{end_time / 1000:.1f}s, итоговая громкость={final_audio.dBFS:.1f}dBFS")
                    except Exception as overlay_error:
                        # Fallback на старый метод
                        self.logger.warning(f"Замена не удалась, используем overlay: {overlay_error}")
                        final_audio = final_audio.overlay(segment_audio, position=int(start_time))
                        successful_segments += 1

                except Exception as e:
                    self.logger.warning(f"Ошибка обработки сегмента: {e}")
                    continue

            if successful_segments == 0:
                self.logger.warning("Ни один сегмент не был успешно добавлен")
                return None

            # Микширование с оригинальным аудио если нужно
            if preserve_original and original_audio:
                try:
                    # Сохраняем оригинальное аудио во временный файл
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_orig:
                        original_audio.write_audiofile(tmp_orig.name, verbose=False, logger=None)
                        original_segment = AudioSegment.from_file(tmp_orig.name)

                        # Понижаем громкость оригинала и микшируем
                        original_segment = original_segment - 15  # -15 dB
                        final_audio = final_audio.overlay(original_segment)

                        # Удаляем временный файл
                        Path(tmp_orig.name).unlink()

                    self.logger.info("Оригинальное аудио добавлено как фон")
                except Exception as e:
                    self.logger.warning(f"Ошибка микширования с оригиналом: {e}")

            # Финальная нормализация громкости
            current_dBFS = final_audio.dBFS
            self.logger.info(f"Громкость до финальной нормализации: {current_dBFS:.1f} dBFS")
            
            if current_dBFS < -30:
                # Для любого тихого аудио применяем полную нормализацию
                final_audio = final_audio.normalize(headroom=20.0)
                self.logger.info(f"Применена полная нормализация аудио")

            # Сохраняем финальное аудио
            final_audio_filename = f"final_audio_{uuid.uuid4().hex}.wav"
            temp_dir = Path(__file__).parent.parent / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            final_audio_path = temp_dir / final_audio_filename
            # Сохраняем финальное аудио
            # final_audio_filename = f"final_audio_{uuid.uuid4().hex}.wav"
            # temp_dir = Path("src/temp")
            # temp_dir.mkdir(exist_ok=True)
            # final_audio_path = temp_dir / final_audio_filename

            final_audio.export(str(final_audio_path), format="wav")
            
            # Диагностика финального аудио
            final_dBFS = final_audio.dBFS
            self.logger.info(f"Финальная громкость аудио: {final_dBFS:.1f} dBFS")

            # Добавляем в список для очистки
            self.temp_files.append(str(final_audio_path))

            self.logger.info(f"Финальное аудио создано: {final_audio_path} ({successful_segments} сегментов)")
            return str(final_audio_path)

        except Exception as e:
            self.logger.error(f"Ошибка объединения аудио сегментов: {e}")
            return None

    def cleanup_temp_files(self):
        """Очистка временных файлов"""
        for temp_file in self.temp_files:
            try:
                if Path(temp_file).exists():
                    Path(temp_file).unlink()
                    self.logger.debug(f"Удален временный файл: {temp_file}")
            except Exception as e:
                self.logger.warning(f"Ошибка удаления {temp_file}: {e}")

        self.temp_files.clear()

    def validate_video_file(self, video_path: str) -> dict:
        """
        Проверка видео файла

        Returns:
            dict: результат валидации с детальной информацией
        """
        result = {
            "valid": False,
            "error": None,
            "info": {},
            "recommendations": []
        }

        try:
            if not Path(video_path).exists():
                result["error"] = "file_not_found"
                return result

            # Проверка размера файла
            file_size = Path(video_path).stat().st_size
            if file_size == 0:
                result["error"] = "empty_file"
                return result

            if file_size > 500 * 1024 * 1024:  # 500MB
                result["recommendations"].append("large_file_warning")

            # Загрузка и анализ видео
            video = mp.VideoFileClip(video_path)

            result["info"] = {
                "duration": video.duration,
                "fps": video.fps,
                "size": video.size,
                "has_audio": video.audio is not None,
                "file_size_mb": file_size / (1024 * 1024)
            }

            # Проверки и рекомендации
            if not video.audio:
                result["error"] = "no_audio"
                video.close()
                return result

            if video.duration > 300:  # 5 минут
                result["recommendations"].append("long_video_warning")

            if video.duration < 1:
                result["recommendations"].append("very_short_video")

            video.close()
            result["valid"] = True

        except Exception as e:
            result["error"] = f"validation_error: {str(e)}"

        return result

    def get_video_info(self, video_path: str) -> dict:
        """Получение подробной информации о видео файле"""
        try:
            video = mp.VideoFileClip(video_path)

            info = {
                "file_path": video_path,
                "file_size_bytes": Path(video_path).stat().st_size,
                "file_size_mb": Path(video_path).stat().st_size / (1024 * 1024),
                "duration_seconds": video.duration,
                "fps": video.fps,
                "resolution": video.size,
                "has_audio": video.audio is not None,
                "estimated_frames": int(video.duration * video.fps) if video.fps else 0
            }

            if video.audio:
                # Дополнительная информация об аудио
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                    video.audio.write_audiofile(tmp_file.name, verbose=False, logger=None)
                    audio_segment = AudioSegment.from_file(tmp_file.name)

                    info["audio_info"] = {
                        "sample_rate": audio_segment.frame_rate,
                        "channels": audio_segment.channels,
                        "sample_width": audio_segment.sample_width,
                        "duration_ms": len(audio_segment),
                        "loudness_dbfs": audio_segment.dBFS
                    }

                    # Удаляем временный файл
                    Path(tmp_file.name).unlink()

            video.close()
            return info

        except Exception as e:
            self.logger.error(f"Ошибка получения информации о видео: {e}")
            return {"error": str(e)}

    def __del__(self):
        """Деструктор для очистки временных файлов"""
        self.cleanup_temp_files()


# Функция для тестирования модуля
def test_video_processor():
    """Тестирование VideoProcessor"""
    processor = VideoProcessor()

    # Пример использования
    print("=== Тестирование VideoProcessor ===")

    test_video = "test_video.mp4"
    if Path(test_video).exists():
        # Валидация видео
        validation = processor.validate_video_file(test_video)
        print(f"Валидация: {validation}")

        # Информация о видео
        info = processor.get_video_info(test_video)
        print(f"Информация о видео: {info}")

        # Извлечение аудио
        audio_path, video_info = processor.extract_audio(test_video)
        if audio_path:
            print(f"Аудио извлечено: {audio_path}")

        # Очистка
        processor.cleanup_temp_files()
    else:
        print(f"Для тестирования поместите видео файл: {test_video}")


if __name__ == "__main__":
    test_video_processor()