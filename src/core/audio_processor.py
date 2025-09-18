#!/usr/bin/env python3
"""
AudioProcessor: Модуль обработки аудио файлов
Сегментация аудио по паузам, подгонка длительности сегментов
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional

from pydub import AudioSegment
from pydub.silence import split_on_silence

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from config import config


class AudioProcessor:
    """Класс для обработки аудио файлов"""
    
    def __init__(self):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def segment_audio(
        self, 
        audio_path: str, 
        min_silence_len: Optional[int] = None,
        silence_thresh: Optional[int] = None,
        keep_silence: Optional[int] = None
    ) -> List[Dict]:
        """
        Сегментация аудио по паузам
        
        Args:
            audio_path: путь к аудио файлу
            min_silence_len: минимальная длительность паузы (мс)
            silence_thresh: порог тишины (дБ)
            keep_silence: сколько тишины оставлять (мс)
            
        Returns:
            list: список сегментов с метаданными
        """
        try:
            self.logger.info(f"Сегментация аудио: {audio_path}")
            
            # Проверка существования файла
            if not Path(audio_path).exists():
                raise FileNotFoundError(f"Аудио файл не найден: {audio_path}")
            
            # Использование параметров из конфигурации если не указаны
            min_silence_len = min_silence_len or self.config.MIN_SILENCE_LEN
            silence_thresh = silence_thresh or self.config.SILENCE_THRESH
            keep_silence = keep_silence or self.config.KEEP_SILENCE
            
            # Загрузка аудио
            audio = AudioSegment.from_wav(audio_path)
            original_duration = len(audio)
            
            self.logger.debug(f"Оригинальная длительность: {original_duration/1000:.2f}s")
            self.logger.debug(f"Параметры сегментации: min_silence={min_silence_len}ms, "
                            f"thresh={silence_thresh}dB, keep={keep_silence}ms")
            
            # Обнаруживаем начальную тишину перед первым речевым сегментом
            self.logger.debug("🔍 Определяем начальную тишину...")
            
            # Находим первый не тихий сегмент
            silence_segments = self._detect_silence_ranges(audio, min_silence_len, silence_thresh)
            initial_silence_duration = 0
            
            if silence_segments:
                # Если есть тишина в начале файла (начинается с 0)
                first_silence = silence_segments[0]
                if first_silence['start_time'] <= 0.05:  # Погрешность 50мс
                    initial_silence_duration = first_silence['duration'] * 1000  # в миллисекундах
                    self.logger.debug(f"📍 Найдена начальная тишина: {initial_silence_duration/1000:.2f}s")
            
            # Разделение по паузам
            chunks = split_on_silence(
                audio,
                min_silence_len=min_silence_len,
                silence_thresh=silence_thresh,
                keep_silence=keep_silence
            )
            
            segments = []
            # Начинаем отсчет с учетом начальной тишины
            current_time = initial_silence_duration
            
            for i, chunk in enumerate(chunks):
                chunk_duration = len(chunk)
                
                # Игнорируем очень короткие фрагменты
                if chunk_duration < 100:  # меньше 0.1 секунды
                    current_time += chunk_duration
                    continue
                
                # Создание временного файла для сегмента
                segment_path = self.config.get_temp_filename(f"segment_{i}", ".wav")
                chunk.export(str(segment_path), format="wav")
                
                # Учитываем начальную тишину в таймингах
                actual_start_time = current_time / 1000.0
                actual_end_time = (current_time + chunk_duration) / 1000.0
                
                segment_info = {
                    'id': i,
                    'path': str(segment_path),
                    'start_time': actual_start_time,
                    'end_time': actual_end_time,
                    'duration': chunk_duration / 1000.0,
                    'size_bytes': Path(segment_path).stat().st_size,
                    'sample_rate': chunk.frame_rate,
                    'channels': chunk.channels,
                    'has_initial_silence': initial_silence_duration > 0,
                    'initial_silence_duration': initial_silence_duration / 1000.0
                }
                
                segments.append(segment_info)
                current_time += chunk_duration
            
            self.logger.info(f"Создано {len(segments)} сегментов из аудио длительностью {original_duration/1000:.2f}s")
            
            if initial_silence_duration > 0:
                self.logger.info(f"✅ Учтена начальная тишина: {initial_silence_duration/1000:.2f}s")
                if segments:
                    self.logger.debug(f"📍 Первый речевой сегмент начинается с {segments[0]['start_time']:.2f}s (вместо 0.0s)")
            
            return segments
            
        except Exception as e:
            self.logger.error(f"Ошибка сегментации аудио: {e}")
            return []
    
    def adjust_audio_duration(
        self, 
        audio_path: str, 
        target_duration: float,
        method: str = 'auto'
    ) -> Optional[str]:
        """
        Подгонка длительности аудио под целевое значение
        
        Args:
            audio_path: путь к аудио файлу
            target_duration: целевая длительность в секундах
            method: метод подгонки ('speed', 'pad', 'auto')
            
        Returns:
            str: путь к подогнанному аудио файлу или None при ошибке
        """
        try:
            if not Path(audio_path).exists():
                raise FileNotFoundError(f"Аудио файл не найден: {audio_path}")
            
            # Загрузка аудио с проверкой совместимости
            try:
                audio = AudioSegment.from_file(audio_path)
                current_duration = len(audio) / 1000.0
                current_dBFS = audio.dBFS
            except Exception as e:
                self.logger.error(f"Ошибка загрузки через pydub: {e}")
                return audio_path
                
            self.logger.info(f"Подгонка аудио: {audio_path}")
            self.logger.info(f"  Исходная длительность: {current_duration:.2f}s")
            self.logger.info(f"  Целевая длительность: {target_duration:.2f}s") 
            self.logger.info(f"  Исходная громкость: {current_dBFS:.1f}dBFS")
            
            # Файлы голоса Milena работают идеально, пропускаем обработку
            audio_path_str = str(audio_path).lower()
            is_milena_converted = ("milena_converted" in audio_path_str or 
                                 "milena" in audio_path_str or
                                 current_duration > 60.0)  # Длинные аудио обычно из TTS
            
            # ОТЛАДКА: проверяем детекцию файлов Milena
            self.logger.info(f"🔍 Проверка файла TTS: path='{audio_path}', is_milena={is_milena_converted}, duration={current_duration:.1f}s")
            
            if is_milena_converted:
                self.logger.info("✅ Обнаружен файл голоса TTS - используем как есть без обработки")
                return audio_path
            
            # Проверка на проблемные файлы (только pyttsx3)
            is_pyttsx3_file = "pyttsx3" in str(audio_path)
            if current_duration == 0 or current_dBFS == float('-inf') or is_pyttsx3_file:
                if is_pyttsx3_file:
                    self.logger.info("Обнаружен pyttsx3 файл - используем прямую обработку FFmpeg...")
                else:
                    self.logger.warning("Обнаружен несовместимый файл! Используем прямую обработку FFmpeg...")
                
                # ПОЛНОСТЬЮ ОБХОДИМ PYDUB - работаем только с FFmpeg
                try:
                    import subprocess
                    
                    # Создаем исправленный файл с точной длительностью
                    adjusted_path = self.config.get_temp_filename("ffmpeg_adjusted", ".wav")
                    
                    # Интеллектуальная обработка длительности без потери смысла
                    if target_duration > 0:
                        duration_diff = target_duration - current_duration
                        
                        if abs(duration_diff) < 0.1:
                            # Различие меньше 100мс - используем без обрезки
                            self.logger.debug(f"🔧 Различие длительности минимально ({duration_diff:.3f}s), сохраняем без изменений")
                            cmd = [
                                'ffmpeg', '-f', 'aiff', '-i', audio_path,
                                '-af', 'loudnorm',  # только нормализация
                                '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '1',
                                '-y', str(adjusted_path)
                            ]
                        elif duration_diff > 0:
                            # Аудио короче целевой длительности - добавляем тишину
                            self.logger.debug(f"🔧 Добавляем {duration_diff:.2f}s тишины в конец")
                            cmd = [
                                'ffmpeg', '-f', 'aiff', '-i', audio_path,
                                '-af', f'loudnorm,apad=pad_dur={target_duration}',
                                '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '1',
                                '-y', str(adjusted_path)
                            ]
                        else:
                            # Аудио длиннее целевой длительности - предупреждение и сохранение смысла
                            self.logger.warning(f"⚠️ Аудио на {abs(duration_diff):.2f}s длиннее целевой длительности!")
                            self.logger.warning(f"💡 СОХРАНЯЕМ ВСЕ АУДИО для избежания потери смысла")
                            
                            # Сохраняем полное аудио с предупреждением
                            cmd = [
                                'ffmpeg', '-f', 'aiff', '-i', audio_path,
                                '-af', 'loudnorm',  # только нормализация, БЕЗ обрезки
                                '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '1',
                                '-y', str(adjusted_path)
                            ]
                    else:
                        # Если целевая длительность 0, просто нормализуем
                        cmd = [
                            'ffmpeg', '-f', 'aiff', '-i', audio_path,  # принудительно указываем AIFF формат
                            '-af', 'loudnorm',  # используем loudnorm для нормализации
                            '-acodec', 'pcm_s16le', 
                            '-ar', '44100',
                            '-ac', '1',
                            '-y', str(adjusted_path)
                        ]
                    
                    self.logger.info(f"Аудио процессор FFmpeg команда: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        self.logger.info(f"Файл обработан через FFmpeg: {adjusted_path}")
                        # Проверяем результат
                        try:
                            test_audio = AudioSegment.from_file(adjusted_path)
                            final_duration = len(test_audio) / 1000.0
                            final_dBFS = test_audio.dBFS
                            self.logger.info(f"  FFmpeg результат: длительность={final_duration:.2f}s, громкость={final_dBFS:.1f}dBFS")
                        except:
                            self.logger.info(f"  FFmpeg результат создан (проверка через pydub не удалась)")
                        
                        return str(adjusted_path)
                    else:
                        self.logger.error(f"FFmpeg обработка неудачна: {result.stderr}")
                        return audio_path
                        
                except Exception as ffmpeg_error:
                    self.logger.error(f"Ошибка FFmpeg обработки: {ffmpeg_error}")
                    return audio_path
            
            # Если длительности почти равны, ничего не делаем
            if abs(current_duration - target_duration) < 0.1:
                self.logger.debug(f"Длительность уже подходящая: {current_duration:.2f}s")
                return audio_path
            
            self.logger.debug(f"Подгонка длительности: {current_duration:.2f}s -> {target_duration:.2f}s")
            
            if method == 'auto':
                # Автоматический выбор метода
                ratio = current_duration / target_duration
                if 0.8 <= ratio <= 1.3:
                    method = 'speed'  # Изменение скорости в разумных пределах
                else:
                    method = 'pad'    # Обрезка или дополнение тишиной
            
            if method == 'speed' and current_duration > target_duration:
                # Ускорение аудио
                speed_factor = current_duration / target_duration
                # Ограничиваем ускорение до разумных пределов
                speed_factor = min(speed_factor, 1.5)
                adjusted_audio = audio.speedup(playback_speed=speed_factor)
                
            elif method == 'speed' and current_duration < target_duration:
                # Замедление аудио
                speed_factor = current_duration / target_duration
                # Ограничиваем замедление до разумных пределов
                speed_factor = max(speed_factor, 0.7)
                adjusted_audio = audio.speedup(playback_speed=speed_factor)
                
            elif current_duration > target_duration:
                # ЗАЩИТА: НЕ обрезаем аудио если различие значительное - сохраняем смысл
                duration_diff = current_duration - target_duration
                if duration_diff > 5.0:  # Если аудио длиннее на 5+ секунд
                    self.logger.warning(f"⚠️ КРИТИЧНО: Аудио на {duration_diff:.1f}s длиннее целевой длительности!")
                    self.logger.warning(f"💡 СОХРАНЯЕМ ВСЕ АУДИО для избежания потери смысла")
                    # Возвращаем исходное аудио без обрезки
                    adjusted_audio = audio
                else:
                    # Обрезка аудио только при небольших различиях
                    target_ms = int(target_duration * 1000)
                    adjusted_audio = audio[:target_ms]
                
            else:
                # Добавление тишины в конец
                silence_duration = int((target_duration - current_duration) * 1000)
                silence = AudioSegment.silent(duration=silence_duration)
                adjusted_audio = audio + silence
            
            # Диагностика после обработки
            adjusted_dBFS = adjusted_audio.dBFS
            self.logger.info(f"  После обработки: длительность={len(adjusted_audio) / 1000.0:.2f}s, громкость={adjusted_dBFS:.1f}dBFS")
            
            # Нормализация громкости перед сохранением
            if adjusted_dBFS < -50:  # Если аудио очень тихое
                target_dBFS = -20.0  # Нормальная громкость
                volume_change = target_dBFS - adjusted_dBFS
                adjusted_audio = adjusted_audio + volume_change
                self.logger.info(f"Нормализация громкости: {adjusted_dBFS:.1f}dBFS -> {target_dBFS:.1f}dBFS")
            
            # Сохранение подогнанного аудио
            adjusted_path = self.config.get_temp_filename("adjusted", ".wav")
            adjusted_audio.export(str(adjusted_path), format="wav")
            
            # Финальная диагностика
            final_duration = len(adjusted_audio) / 1000.0
            final_dBFS = adjusted_audio.dBFS
            self.logger.info(f"  Финальный результат: {adjusted_path}")
            self.logger.info(f"  Финальные параметры: длительность={final_duration:.2f}s, громкость={final_dBFS:.1f}dBFS")
            
            return str(adjusted_path)
            
        except Exception as e:
            self.logger.error(f"Ошибка подгонки длительности аудио: {e}")
            return audio_path
    
    def normalize_audio_volume(self, audio_path: str, target_dBFS: float = -20.0) -> Optional[str]:
        """
        Нормализация громкости аудио
        
        Args:
            audio_path: путь к аудио файлу
            target_dBFS: целевая громкость в dBFS
            
        Returns:
            str: путь к нормализованному аудио файлу
        """
        try:
            if not Path(audio_path).exists():
                raise FileNotFoundError(f"Аудио файл не найден: {audio_path}")
            
            audio = AudioSegment.from_file(audio_path)
            current_dBFS = audio.dBFS
            
            # Вычисление необходимого изменения громкости
            volume_change = target_dBFS - current_dBFS
            
            # Применение изменения громкости
            normalized_audio = audio + volume_change
            
            # Сохранение нормализованного аудио
            normalized_path = self.config.get_temp_filename("normalized", ".wav")
            normalized_audio.export(str(normalized_path), format="wav")
            
            self.logger.debug(f"Нормализация громкости: {current_dBFS:.1f}dBFS -> {target_dBFS:.1f}dBFS")
            return str(normalized_path)
            
        except Exception as e:
            self.logger.error(f"Ошибка нормализации громкости: {e}")
            return audio_path
    
    def apply_audio_effects(
        self, 
        audio_path: str, 
        effects: Dict[str, any] = None
    ) -> Optional[str]:
        """
        Применение аудио эффектов
        
        Args:
            audio_path: путь к аудио файлу
            effects: словарь с эффектами и их параметрами
            
        Returns:
            str: путь к обработанному аудио файлу
        """
        try:
            if not Path(audio_path).exists():
                raise FileNotFoundError(f"Аудио файл не найден: {audio_path}")
            
            if not effects:
                return audio_path
            
            audio = AudioSegment.from_file(audio_path)
            
            # Применение эффектов
            if effects.get('fade_in'):
                fade_duration = int(effects['fade_in'] * 1000)  # в миллисекундах
                audio = audio.fade_in(fade_duration)
            
            if effects.get('fade_out'):
                fade_duration = int(effects['fade_out'] * 1000)
                audio = audio.fade_out(fade_duration)
            
            if effects.get('volume_boost'):
                audio = audio + effects['volume_boost']  # в dB
            
            if effects.get('low_pass_filter'):
                # Простая реализация low-pass фильтра через изменение sample rate
                pass  # Требует более сложной реализации с библиотеками DSP
            
            # Сохранение обработанного аудио
            processed_path = self.config.get_temp_filename("processed", ".wav")
            audio.export(str(processed_path), format="wav")
            
            self.logger.debug(f"Применены эффекты: {list(effects.keys())}")
            return str(processed_path)
            
        except Exception as e:
            self.logger.error(f"Ошибка применения аудио эффектов: {e}")
            return audio_path
    
    def get_audio_info(self, audio_path: str) -> Optional[Dict]:
        """
        Получение информации об аудио файле
        
        Args:
            audio_path: путь к аудио файлу
            
        Returns:
            dict: информация об аудио файле
        """
        try:
            if not Path(audio_path).exists():
                return None
            
            audio = AudioSegment.from_file(audio_path)
            
            info = {
                'duration': len(audio) / 1000.0,  # в секундах
                'duration_ms': len(audio),
                'sample_rate': audio.frame_rate,
                'channels': audio.channels,
                'sample_width': audio.sample_width,
                'frame_count': audio.frame_count(),
                'dBFS': audio.dBFS,
                'max_dBFS': audio.max_dBFS,
                'file_size': Path(audio_path).stat().st_size,
                'file_format': Path(audio_path).suffix[1:].upper()
            }
            
            return info
            
        except Exception as e:
            self.logger.error(f"Ошибка получения информации об аудио: {e}")
            return None
    
    def detect_silence_segments(
        self, 
        audio_path: str,
        min_silence_len: int = 500,
        silence_thresh: int = -40
    ) -> List[Dict]:
        """
        Обнаружение сегментов тишины в аудио
        
        Args:
            audio_path: путь к аудио файлу
            min_silence_len: минимальная длительность тишины (мс)
            silence_thresh: порог тишины (дБ)
            
        Returns:
            list: список сегментов тишины
        """
        try:
            if not Path(audio_path).exists():
                raise FileNotFoundError(f"Аудио файл не найден: {audio_path}")
            
            from pydub.silence import detect_silence
            
            audio = AudioSegment.from_file(audio_path)
            
            # Обнаружение сегментов тишины
            silence_segments = detect_silence(
                audio, 
                min_silence_len=min_silence_len, 
                silence_thresh=silence_thresh
            )
            
            # Преобразование в более удобный формат
            silence_info = []
            for start_ms, end_ms in silence_segments:
                silence_info.append({
                    'start_time': start_ms / 1000.0,
                    'end_time': end_ms / 1000.0,
                    'duration': (end_ms - start_ms) / 1000.0
                })
            
            self.logger.debug(f"Найдено {len(silence_info)} сегментов тишины")
            return silence_info
            
        except Exception as e:
            self.logger.error(f"Ошибка обнаружения тишины: {e}")
            return []
    
    def _detect_silence_ranges(self, audio_segment: AudioSegment, min_silence_len: int, silence_thresh: int) -> List[Dict]:
        """
        Вспомогательный метод для обнаружения сегментов тишины из AudioSegment
        
        Args:
            audio_segment: объект AudioSegment
            min_silence_len: минимальная длительность тишины (мс)
            silence_thresh: порог тишины (дБ)
            
        Returns:
            list: список сегментов тишины с информацией о времени и длительности
        """
        try:
            from pydub.silence import detect_silence
            
            # Обнаружение сегментов тишины
            silence_segments = detect_silence(
                audio_segment, 
                min_silence_len=min_silence_len, 
                silence_thresh=silence_thresh
            )
            
            # Преобразование в более удобный формат
            silence_info = []
            for start_ms, end_ms in silence_segments:
                silence_info.append({
                    'start_time': start_ms / 1000.0,
                    'end_time': end_ms / 1000.0,
                    'duration': (end_ms - start_ms) / 1000.0
                })
            
            return silence_info
            
        except Exception as e:
            self.logger.error(f"Ошибка обнаружения диапазонов тишины: {e}")
            return []
    
    def cleanup_temp_segments(self, segments: List[Dict]):
        """
        Очистка временных файлов сегментов
        
        Args:
            segments: список сегментов с путями к файлам
        """
        cleaned_count = 0
        for segment in segments:
            try:
                segment_path = segment.get('path')
                if segment_path and Path(segment_path).exists():
                    Path(segment_path).unlink()
                    cleaned_count += 1
            except Exception as e:
                self.logger.warning(f"Не удалось удалить сегмент {segment.get('path')}: {e}")
        
        self.logger.debug(f"Очищено {cleaned_count} временных аудио файлов")


if __name__ == "__main__":
    # Тестирование модуля
    print("=== Тестирование AudioProcessor ===")
    
    processor = AudioProcessor()
    print(f"AudioProcessor инициализирован")
    
    # Тест с фиктивным файлом
    test_file = "test.wav"
    if Path(test_file).exists():
        info = processor.get_audio_info(test_file)
        print(f"Информация об аудио: {info}")
    else:
        print(f"Тестовый файл {test_file} не найден")
