"""
Стратегии для различных форматов вывода видео
SOLID: Strategy Pattern + Open/Closed Principle
"""

import logging
import time
from pathlib import Path
from typing import List, Dict, Any

from ..interfaces.video_output_interface import (
    IVideoOutputStrategy,
    VideoOutputFormat,
    VideoOutputConfig,
    ProcessedVideo,
    ISubtitleGenerator
)


class SubtitleGenerator(ISubtitleGenerator):
    """
    Генератор субтитров в различных форматах
    SOLID: Single Responsibility - только генерация субтитров
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def generate_srt(self, segments: List[Dict[str, Any]], output_path: str, language: str = "ru") -> str:
        """Генерирует SRT файл"""
        srt_path = output_path.replace('.mp4', f'_{language}_subtitles.srt')
        
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments, 1):
                start_time = self._format_srt_time(segment.get('start_time', 0))
                end_time = self._format_srt_time(segment.get('end_time', 0))
                text = segment.get('translated_text' if language == 'ru' else 'original_text', '')
                
                f.write(f"{i}\\n")
                f.write(f"{start_time} --> {end_time}\\n")
                f.write(f"{text}\\n\\n")
        
        self.logger.info(f"SRT субтитры созданы: {srt_path}")
        return srt_path
    
    def generate_vtt(self, segments: List[Dict[str, Any]], output_path: str, language: str = "ru") -> str:
        """Генерирует VTT файл"""
        vtt_path = output_path.replace('.mp4', f'_{language}_subtitles.vtt')
        
        with open(vtt_path, 'w', encoding='utf-8') as f:
            f.write("WEBVTT\\n\\n")
            
            for i, segment in enumerate(segments, 1):
                start_time = self._format_vtt_time(segment.get('start_time', 0))
                end_time = self._format_vtt_time(segment.get('end_time', 0))
                text = segment.get('translated_text' if language == 'ru' else 'original_text', '')
                
                f.write(f"{start_time} --> {end_time}\\n")
                f.write(f"{text}\\n\\n")
        
        self.logger.info(f"VTT субтитры созданы: {vtt_path}")
        return vtt_path
    
    def _format_srt_time(self, seconds: float) -> str:
        """Форматирует время для SRT (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def _format_vtt_time(self, seconds: float) -> str:
        """Форматирует время для VTT (HH:MM:SS.mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millisecs:03d}"


class TranslationOnlyStrategy(IVideoOutputStrategy):
    """
    Стратегия для создания видео только с переводом (без субтитров)
    SOLID: Strategy Pattern - конкретная стратегия
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)
    
    def get_supported_format(self) -> VideoOutputFormat:
        return VideoOutputFormat.TRANSLATION_ONLY
    
    def create_output(self, 
                     input_video_path: str, 
                     translated_segments: List[Dict[str, Any]], 
                     output_path: str,
                     config: VideoOutputConfig) -> ProcessedVideo:
        """Создает видео только с переводом аудио"""
        start_time = time.time()
        
        self.logger.info("🎬 Создание видео с переводом (без субтитров)")
        
        try:
            # Импортируем moviepy для обработки видео
            import moviepy.editor as mp
            from pydub import AudioSegment
            
            # Загружаем оригинальное видео
            video = mp.VideoFileClip(input_video_path)
            original_duration = video.duration
            
            # Создаем финальное аудио из переведенных сегментов
            final_audio = AudioSegment.silent(duration=int(original_duration * 1000))
            
            for segment in translated_segments:
                if segment.get('translated_audio_path'):
                    segment_audio = AudioSegment.from_file(segment['translated_audio_path'])
                    start_ms = int(segment.get('start_time', 0) * 1000)
                    final_audio = final_audio.overlay(segment_audio, position=start_ms)
            
            # Сохраняем финальное аудио
            temp_audio_path = output_path.replace('.mp4', '_temp_audio.wav')
            final_audio.export(temp_audio_path, format='wav')
            
            # Заменяем аудио в видео
            final_audio_clip = mp.AudioFileClip(temp_audio_path)
            final_video = video.set_audio(final_audio_clip)
            
            # Сохраняем результат
            final_video.write_videofile(
                output_path,
                verbose=False,
                logger=None,
                codec='libx264',
                audio_codec='aac'
            )
            
            # Очистка
            video.close()
            final_audio_clip.close() 
            final_video.close()
            Path(temp_audio_path).unlink(missing_ok=True)
            
            processing_time = time.time() - start_time
            file_size = Path(output_path).stat().st_size / (1024 * 1024)  # MB
            
            result = ProcessedVideo(
                output_path=output_path,
                original_path=input_video_path,
                output_format=VideoOutputFormat.TRANSLATION_ONLY,
                duration=original_duration,
                file_size_mb=file_size,
                has_audio=True,
                has_subtitles=False,
                subtitle_files=[],
                processing_time=processing_time,
                metadata={
                    "segments_processed": len(translated_segments),
                    "translation_only": True
                }
            )
            
            self.logger.info(f"✅ Видео с переводом создано: {output_path} ({file_size:.1f}MB)")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка создания видео с переводом: {e}")
            raise


class SubtitlesOnlyStrategy(IVideoOutputStrategy):
    """
    Стратегия для создания видео только с субтитрами (оригинальное аудио)
    SOLID: Strategy Pattern - конкретная стратегия
    """
    
    def __init__(self, subtitle_generator: ISubtitleGenerator = None, logger: logging.Logger = None):
        self.subtitle_generator = subtitle_generator or SubtitleGenerator()
        self.logger = logger or logging.getLogger(__name__)
    
    def get_supported_format(self) -> VideoOutputFormat:
        return VideoOutputFormat.SUBTITLES_ONLY
    
    def create_output(self, 
                     input_video_path: str, 
                     translated_segments: List[Dict[str, Any]], 
                     output_path: str,
                     config: VideoOutputConfig) -> ProcessedVideo:
        """Создает видео с оригинальным аудио + субтитрами"""
        start_time = time.time()
        
        self.logger.info("📝 Создание видео с субтитрами (оригинальное аудио)")
        
        try:
            import moviepy.editor as mp
            
            # Копируем оригинальное видео (или просто ссылаемся на него)
            video = mp.VideoFileClip(input_video_path)
            original_duration = video.duration
            
            # Создаем субтитры
            subtitle_files = []
            
            # Русские субтитры
            srt_ru = self.subtitle_generator.generate_srt(
                translated_segments, output_path, language="ru"
            )
            subtitle_files.append(srt_ru)
            
            # Английские субтитры (оригинал)  
            srt_en = self.subtitle_generator.generate_srt(
                translated_segments, output_path, language="en"
            )
            subtitle_files.append(srt_en)
            
            # VTT файлы для веб-совместимости
            vtt_ru = self.subtitle_generator.generate_vtt(
                translated_segments, output_path, language="ru"
            )
            subtitle_files.append(vtt_ru)
            
            # Сохраняем видео без изменений (или с встроенными субтитрами если нужно)
            if config.subtitle_style.get('embed_subtitles', False):
                # Встраиваем субтитры в видео (опционально)
                self._embed_subtitles(video, srt_ru, output_path, config)
            else:
                # Просто копируем оригинальное видео
                video.write_videofile(
                    output_path,
                    verbose=False,
                    logger=None,
                    codec='libx264',
                    audio_codec='aac'
                )
            
            video.close()
            
            processing_time = time.time() - start_time
            file_size = Path(output_path).stat().st_size / (1024 * 1024)  # MB
            
            result = ProcessedVideo(
                output_path=output_path,
                original_path=input_video_path,
                output_format=VideoOutputFormat.SUBTITLES_ONLY,
                duration=original_duration,
                file_size_mb=file_size,
                has_audio=True,
                has_subtitles=True,
                subtitle_files=subtitle_files,
                processing_time=processing_time,
                metadata={
                    "segments_processed": len(translated_segments),
                    "subtitles_only": True,
                    "subtitle_formats": ["srt", "vtt"]
                }
            )
            
            self.logger.info(f"✅ Видео с субтитрами создано: {output_path} ({len(subtitle_files)} файлов субтитров)")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка создания видео с субтитрами: {e}")
            raise
    
    def _embed_subtitles(self, video, srt_path: str, output_path: str, config: VideoOutputConfig):
        """Встраивает субтитры в видео (опционально)"""
        try:
            # Можно использовать ffmpeg для встраивания субтитров
            # Пока оставляем заглушку
            video.write_videofile(output_path, verbose=False, logger=None)
        except Exception as e:
            self.logger.warning(f"Не удалось встроить субтитры: {e}")
            video.write_videofile(output_path, verbose=False, logger=None)


class TranslationWithSubtitlesStrategy(IVideoOutputStrategy):
    """
    Стратегия для создания видео с переводом И субтитрами
    SOLID: Strategy Pattern - композиция других стратегий
    """
    
    def __init__(self, 
                 translation_strategy: TranslationOnlyStrategy = None,
                 subtitles_strategy: SubtitlesOnlyStrategy = None,
                 logger: logging.Logger = None):
        self.translation_strategy = translation_strategy or TranslationOnlyStrategy()
        self.subtitles_strategy = subtitles_strategy or SubtitlesOnlyStrategy()
        self.logger = logger or logging.getLogger(__name__)
    
    def get_supported_format(self) -> VideoOutputFormat:
        return VideoOutputFormat.TRANSLATION_WITH_SUBTITLES
    
    def create_output(self, 
                     input_video_path: str, 
                     translated_segments: List[Dict[str, Any]], 
                     output_path: str,
                     config: VideoOutputConfig) -> ProcessedVideo:
        """Создает видео с переводом аудио И субтитрами"""
        start_time = time.time()
        
        self.logger.info("🎬📝 Создание видео с переводом и субтитрами")
        
        try:
            # Создаем временный файл для видео с переводом
            temp_translated_path = output_path.replace('.mp4', '_temp_translated.mp4')
            
            # 1. Сначала создаем видео с переводом
            translation_result = self.translation_strategy.create_output(
                input_video_path, translated_segments, temp_translated_path, config
            )
            
            # 2. Затем добавляем субтитры к переведенному видео
            subtitles_result = self.subtitles_strategy.create_output(
                temp_translated_path, translated_segments, output_path, config
            )
            
            # Очистка временного файла
            Path(temp_translated_path).unlink(missing_ok=True)
            
            processing_time = time.time() - start_time
            file_size = Path(output_path).stat().st_size / (1024 * 1024)  # MB
            
            result = ProcessedVideo(
                output_path=output_path,
                original_path=input_video_path,
                output_format=VideoOutputFormat.TRANSLATION_WITH_SUBTITLES,
                duration=subtitles_result.duration,
                file_size_mb=file_size,
                has_audio=True,
                has_subtitles=True,
                subtitle_files=subtitles_result.subtitle_files,
                processing_time=processing_time,
                metadata={
                    "segments_processed": len(translated_segments),
                    "translation_and_subtitles": True,
                    "subtitle_formats": ["srt", "vtt"]
                }
            )
            
            self.logger.info(f"✅ Видео с переводом и субтитрами создано: {output_path}")
            return result
            
        except Exception as e:
            self.logger.error(f"❌ Ошибка создания видео с переводом и субтитрами: {e}")
            # Очистка при ошибке
            Path(output_path.replace('.mp4', '_temp_translated.mp4')).unlink(missing_ok=True)
            raise