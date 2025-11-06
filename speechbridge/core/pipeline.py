"""
SpeechBridge Pipeline
=====================

Complete video translation pipeline orchestrator.
"""

from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
from datetime import datetime
import logging

from .types import ProcessingResult, TranscriptionResult, TranslationResult, TTSResult, VideoInfo
from .exceptions import ComponentException
from .gpu import GPUManager
from ..components.speech.base import BaseSpeechRecognizer
from ..components.translation.base import BaseTranslator
from ..components.tts.base import BaseTTS
from ..components.video.base import BaseVideoProcessor


class VideoTranslationPipeline:
    """
    Complete video translation pipeline

    Orchestrates the entire workflow:
    1. Extract audio from video
    2. Transcribe audio to text
    3. Translate text to target language
    4. Synthesize translated text to speech
    5. Merge synthesized audio with video
    """

    def __init__(
        self,
        speech_recognizer: BaseSpeechRecognizer,
        translator: BaseTranslator,
        tts_engine: BaseTTS,
        video_processor: BaseVideoProcessor,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize pipeline

        Args:
            speech_recognizer: Speech recognition component
            translator: Translation component
            tts_engine: Text-to-speech component
            video_processor: Video processing component
            config: Pipeline configuration:
                - temp_dir: Temporary files directory (default: 'temp')
                - keep_temp: Keep temporary files (default: False)
                - progress_callback: Progress callback function
                - sync_audio: Synchronize audio with original timing (default: True)
                - generate_subtitles: Generate subtitle files (default: False)
                - subtitle_format: 'srt', 'vtt', or 'both' (default: 'srt')
                - subtitle_only: Only generate subtitles, no audio translation (default: False)
                - export_text: Export text translation with timing (default: False)
                - embed_subtitles: Embed subtitles into video file (default: False)
        """
        self.speech_recognizer = speech_recognizer
        self.translator = translator
        self.tts_engine = tts_engine
        self.video_processor = video_processor

        self.config = config or {}
        self.temp_dir = Path(self.config.get('temp_dir', 'temp'))
        self.keep_temp = self.config.get('keep_temp', False)
        self.progress_callback = self.config.get('progress_callback')
        self.sync_audio = self.config.get('sync_audio', True)
        self.generate_subtitles = self.config.get('generate_subtitles', False)
        self.subtitle_format = self.config.get('subtitle_format', 'srt')
        self.subtitle_only = self.config.get('subtitle_only', False)
        self.export_text = self.config.get('export_text', False)
        self.embed_subtitles = self.config.get('embed_subtitles', False)

        self.gpu_manager = GPUManager()
        self.logger = logging.getLogger('speechbridge.pipeline')

        # Create temp directory
        self.temp_dir.mkdir(exist_ok=True, parents=True)

        # Initialize audio synchronizer if needed
        self.audio_sync = None
        if self.sync_audio:
            from ..components.audio.sync import AudioSynchronizer
            self.audio_sync = AudioSynchronizer()

    def process_video(
        self,
        video_path: str,
        output_path: str,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None
    ) -> ProcessingResult:
        """
        Process video through complete pipeline

        Args:
            video_path: Path to input video
            output_path: Path to save output video
            source_lang: Source language (overrides config)
            target_lang: Target language (overrides config)

        Returns:
            ProcessingResult: Complete processing result
        """
        self.logger.info("=" * 80)
        self.logger.info("Starting video translation pipeline")
        self.logger.info(f"Input: {video_path}")
        self.logger.info(f"Output: {output_path}")
        self.logger.info("=" * 80)

        result: ProcessingResult = {
            'success': False,
            'output_path': None,
            'errors': [],
            'warnings': [],
            'metadata': {
                'start_time': datetime.now().isoformat(),
                'gpu_info': self.gpu_manager.get_gpu_info()
            }
        }

        try:
            # Step 1: Get video info
            self._update_progress(0, "Getting video information")
            video_info = self.video_processor.get_video_info(video_path)
            result['metadata']['video_info'] = video_info
            self.logger.info(
                f"Video info: {video_info['width']}x{video_info['height']} "
                f"@ {video_info['fps']:.2f}fps, {video_info['duration']:.2f}s"
            )

            # Step 2: Extract audio
            self._update_progress(10, "Extracting audio from video")
            audio_path = self.temp_dir / f"audio_{datetime.now().timestamp()}.wav"
            extract_info = self.video_processor.extract_audio(
                video_path,
                str(audio_path)
            )
            self.logger.info(f"Audio extracted: {extract_info['duration']:.2f}s")

            # Step 3: Transcribe audio
            self._update_progress(30, "Transcribing audio to text")
            transcription = self.speech_recognizer.transcribe(str(audio_path))
            result['transcription'] = transcription
            self.logger.info(
                f"Transcription complete: {len(transcription['text'])} chars, "
                f"language: {transcription['language']}, "
                f"segments: {len(transcription.get('segments', []))}"
            )

            # Step 4: Translate text (with or without synchronization)
            self._update_progress(50, "Translating text")

            if self.sync_audio and transcription.get('segments'):
                # Translate segments individually for synchronization
                self.logger.info("Using synchronized translation mode")
                translated_texts = self.audio_sync.translate_segments(
                    transcription['segments'],
                    self.translator,
                    source_lang or transcription['language'],
                    target_lang or self.translator.target_lang
                )

                # Create combined translation result for metadata
                translation = {
                    'text': ' '.join(translated_texts),
                    'source_lang': source_lang or transcription['language'],
                    'target_lang': target_lang or self.translator.target_lang,
                    'segments': translated_texts
                }
            else:
                # Traditional full-text translation
                self.logger.info("Using standard translation mode")
                translation = self.translator.translate(
                    transcription['text'],
                    source_lang=source_lang or transcription['language'],
                    target_lang=target_lang
                )

            result['translation'] = translation
            self.logger.info(
                f"Translation complete: {len(translation['text'])} chars, "
                f"{translation['source_lang']} -> {translation['target_lang']}"
            )

            # Step 4.4: Correct segment timing for initial silence (if sync mode enabled)
            # This ensures subtitles and TTS use corrected timing
            if self.sync_audio and transcription.get('segments') and self.audio_sync:
                actual_speech_start = 0.0
                if audio_path.exists():
                    # Detect actual speech start time
                    import subprocess
                    try:
                        cmd = [
                            'ffmpeg',
                            '-i', str(audio_path),
                            '-af', 'silencedetect=noise=-30dB:d=0.5',
                            '-f', 'null',
                            '-'
                        ]
                        result_proc = subprocess.run(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            timeout=60
                        )

                        # Parse output for first silence_end
                        for line in result_proc.stderr.split('\n'):
                            if 'silence_end:' in line:
                                parts = line.split('silence_end:')[1].split('|')[0].strip()
                                actual_speech_start = float(parts)
                                break
                    except Exception as e:
                        self.logger.warning(f"Failed to detect speech start: {e}")

                # Correct first segment timing if needed
                if actual_speech_start > 0 and transcription['segments']:
                    if transcription['segments'][0]['start'] < actual_speech_start - 0.5:
                        self.logger.info(
                            f"Correcting initial silence: {actual_speech_start:.2f}s "
                            f"(Whisper reported: {transcription['segments'][0]['start']:.2f}s)"
                        )
                        # Adjust first segment start time
                        old_start = transcription['segments'][0]['start']
                        transcription['segments'][0]['start'] = actual_speech_start

                        # Log the correction
                        self.logger.debug(
                            f"First segment corrected: {old_start:.2f}s -> {actual_speech_start:.2f}s"
                        )

            # Step 4.5: Generate subtitles if requested
            subtitle_files = []
            if self.generate_subtitles or self.subtitle_only:
                self._update_progress(60, "Generating subtitles")

                if not transcription.get('segments'):
                    self.logger.warning("No segments available for subtitle generation")
                else:
                    from ..components.subtitles.generator import SubtitleGenerator
                    subtitle_gen = SubtitleGenerator()

                    # Get base name for subtitle files
                    output_base = Path(output_path).stem
                    output_dir = Path(output_path).parent

                    # Get original and translated texts
                    original_texts = [seg['text'] for seg in transcription['segments']]
                    if translation.get('segments'):
                        translated_texts = translation['segments']
                    else:
                        # If no segmented translation, use full text (less ideal)
                        translated_texts = [translation['text']]

                    # Generate subtitle formats
                    if self.subtitle_format in ['srt', 'both']:
                        srt_original = output_dir / f"{output_base}_original_{transcription['language']}.srt"
                        srt_translated = output_dir / f"{output_base}_translated_{translation['target_lang']}.srt"

                        subtitle_gen.generate_srt(
                            transcription['segments'],
                            original_texts,
                            str(srt_original)
                        )
                        subtitle_gen.generate_srt(
                            transcription['segments'],
                            translated_texts,
                            str(srt_translated)
                        )

                        subtitle_files.extend([str(srt_original), str(srt_translated)])
                        self.logger.info(f"Generated SRT subtitles: {srt_original.name}, {srt_translated.name}")

                    if self.subtitle_format in ['vtt', 'both']:
                        vtt_original = output_dir / f"{output_base}_original_{transcription['language']}.vtt"
                        vtt_translated = output_dir / f"{output_base}_translated_{translation['target_lang']}.vtt"

                        subtitle_gen.generate_vtt(
                            transcription['segments'],
                            original_texts,
                            str(vtt_original)
                        )
                        subtitle_gen.generate_vtt(
                            transcription['segments'],
                            translated_texts,
                            str(vtt_translated)
                        )

                        subtitle_files.extend([str(vtt_original), str(vtt_translated)])
                        self.logger.info(f"Generated VTT subtitles: {vtt_original.name}, {vtt_translated.name}")

                    result['subtitle_files'] = subtitle_files

            # Step 4.6: Export text with timing if requested
            if self.export_text:
                self._update_progress(65, "Exporting text with timing")

                output_base = Path(output_path).stem
                output_dir = Path(output_path).parent
                text_export_path = output_dir / f"{output_base}_translation_timing.json"

                import json
                export_data = {
                    'video': str(video_path),
                    'source_language': translation['source_lang'],
                    'target_language': translation['target_lang'],
                    'duration': video_info['duration'],
                    'segments': []
                }

                if transcription.get('segments'):
                    original_texts = [seg['text'] for seg in transcription['segments']]
                    translated_texts = translation.get('segments', [translation['text']])

                    for i, seg in enumerate(transcription['segments']):
                        export_data['segments'].append({
                            'index': i + 1,
                            'start': seg['start'],
                            'end': seg['end'],
                            'duration': seg['end'] - seg['start'],
                            'original_text': original_texts[i] if i < len(original_texts) else '',
                            'translated_text': translated_texts[i] if i < len(translated_texts) else ''
                        })

                with open(text_export_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)

                result['text_export'] = str(text_export_path)
                self.logger.info(f"Text export saved: {text_export_path.name}")

            # Step 5: Synthesize speech (skip if subtitle-only mode)
            if self.subtitle_only:
                self.logger.info("Subtitle-only mode: Skipping audio synthesis and merging")

                # Copy original video to output path
                import shutil
                shutil.copy2(video_path, output_path)

                # Embed subtitles if requested
                if self.embed_subtitles and subtitle_files:
                    self._update_progress(95, "Embedding subtitles into video")
                    embedded = self._embed_subtitles_into_video(
                        output_path,
                        subtitle_files,
                        output_path,
                        translation['source_lang'],
                        translation['target_lang']
                    )
                    if embedded:
                        result['metadata']['subtitles_embedded'] = True
                        self.logger.info("Subtitles embedded into video")
                    else:
                        result['warnings'].append("Failed to embed subtitles")

                result['success'] = True
                result['output_path'] = output_path
                result['metadata']['end_time'] = datetime.now().isoformat()
                result['metadata']['subtitle_only_mode'] = True

                self._update_progress(100, "Processing complete (subtitle-only mode)")
                self.logger.info("=" * 80)
                self.logger.info("Video translation pipeline completed successfully (subtitle-only mode)")
                self.logger.info("=" * 80)

                return result

            self._update_progress(70, "Synthesizing translated speech")
            translated_audio_path = self.temp_dir / f"translated_{datetime.now().timestamp()}.wav"

            if self.sync_audio and transcription.get('segments') and translation.get('segments'):
                # Synchronized TTS with original timing
                self.logger.info("Using synchronized TTS mode")
                sync_dir = self.temp_dir / f"sync_{datetime.now().timestamp()}"
                sync_dir.mkdir(exist_ok=True)

                synced_audio, corrected_segments = self.audio_sync.synchronize_segments(
                    transcription['segments'],
                    translation['segments'],
                    str(sync_dir),
                    self.tts_engine,
                    translation['target_lang'],
                    video_info['duration'],
                    original_audio_path=str(audio_path)  # Pass original audio for silence detection
                )

                # Update transcription segments with corrected timing for subtitle generation
                transcription['segments'] = corrected_segments

                # Copy synchronized audio to expected path
                import shutil
                shutil.copy2(synced_audio, str(translated_audio_path))

                # Get duration from synchronized audio
                import subprocess
                probe_result = subprocess.run(
                    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'default=noprint_wrappers=1:nokey=1', str(translated_audio_path)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                tts_duration = float(probe_result.stdout.strip()) if probe_result.returncode == 0 else 0.0

                tts_result = {
                    'audio_path': str(translated_audio_path),
                    'duration': tts_duration,
                    'synchronized': True
                }
            else:
                # Traditional full-text TTS
                self.logger.info("Using standard TTS mode")
                tts_result = self.tts_engine.synthesize(
                    translation['text'],
                    str(translated_audio_path),
                    language=translation['target_lang']
                )
                tts_result['synchronized'] = False

            result['tts'] = tts_result
            self.logger.info(f"Speech synthesis complete: {tts_result['duration']:.2f}s")

            # Step 6: Merge audio with video
            self._update_progress(90, "Merging audio with video")
            merge_info = self.video_processor.merge_audio(
                video_path,
                str(translated_audio_path),
                output_path,
                remove_original_audio=True
            )
            self.logger.info(f"Audio merged: {output_path}")

            # Step 7: Embed subtitles if requested
            if self.embed_subtitles and subtitle_files:
                self._update_progress(95, "Embedding subtitles into video")
                embedded = self._embed_subtitles_into_video(
                    output_path,
                    subtitle_files,
                    output_path,
                    translation['source_lang'],
                    translation['target_lang']
                )
                if embedded:
                    result['metadata']['subtitles_embedded'] = True
                    self.logger.info("Subtitles embedded into video")
                else:
                    result['warnings'].append("Failed to embed subtitles")
                    self.logger.warning("Failed to embed subtitles, but processing continues")

            # Success
            result['success'] = True
            result['output_path'] = output_path
            result['metadata']['end_time'] = datetime.now().isoformat()
            result['metadata']['total_duration'] = merge_info['duration']

            self._update_progress(100, "Processing complete")
            self.logger.info("=" * 80)
            self.logger.info("Video translation pipeline completed successfully")
            self.logger.info("=" * 80)

        except Exception as e:
            error_msg = f"Pipeline failed: {e}"
            self.logger.error(error_msg)
            result['errors'].append(error_msg)
            result['success'] = False

        finally:
            # Cleanup temporary files
            if not self.keep_temp:
                self._cleanup_temp_files()

        return result

    def process_video_batch(
        self,
        video_paths: List[str],
        output_dir: str,
        source_lang: Optional[str] = None,
        target_lang: Optional[str] = None
    ) -> List[ProcessingResult]:
        """
        Process multiple videos

        Args:
            video_paths: List of input video paths
            output_dir: Directory for output videos
            source_lang: Source language (overrides config)
            target_lang: Target language (overrides config)

        Returns:
            List[ProcessingResult]: Results for each video
        """
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True, parents=True)

        results = []
        total = len(video_paths)

        self.logger.info(f"Processing batch of {total} videos")

        for i, video_path in enumerate(video_paths):
            self.logger.info(f"Processing video {i+1}/{total}: {video_path}")

            # Generate output path
            input_name = Path(video_path).stem
            output_file = output_path / f"{input_name}_translated.mp4"

            # Process video
            result = self.process_video(
                video_path,
                str(output_file),
                source_lang,
                target_lang
            )

            results.append(result)

            # Log result
            if result['success']:
                self.logger.info(f"✓ Video {i+1}/{total} completed")
            else:
                self.logger.error(f"✗ Video {i+1}/{total} failed: {result['errors']}")

        self.logger.info(f"Batch processing complete: {sum(1 for r in results if r['success'])}/{total} succeeded")

        return results

    def validate_components(self) -> bool:
        """
        Validate all pipeline components

        Returns:
            bool: True if all components are valid
        """
        self.logger.info("Validating pipeline components...")

        components = [
            ('Speech Recognizer', self.speech_recognizer),
            ('Translator', self.translator),
            ('TTS Engine', self.tts_engine),
            ('Video Processor', self.video_processor)
        ]

        all_valid = True
        errors = []

        for name, component in components:
            try:
                # Initialize component
                if not component._initialized:
                    self.logger.info(f"Initializing {name}...")
                    component.initialize()
                    self.logger.info(f"✓ {name} initialized")

                # Validate config
                self.logger.info(f"Validating {name} configuration...")
                if not component.validate_config():
                    error_msg = f"{name} configuration is invalid"
                    self.logger.error(error_msg)
                    errors.append(error_msg)
                    all_valid = False
                else:
                    self.logger.info(f"✓ {name} validated")

            except Exception as e:
                error_msg = f"{name} validation failed: {e}"
                self.logger.error(error_msg)
                errors.append(error_msg)
                all_valid = False

        if not all_valid:
            self.logger.error("=" * 60)
            self.logger.error("VALIDATION ERRORS:")
            for error in errors:
                self.logger.error(f"  - {error}")
            self.logger.error("=" * 60)

        return all_valid

    def get_pipeline_info(self) -> Dict[str, Any]:
        """
        Get pipeline information

        Returns:
            Dict: Complete pipeline info
        """
        return {
            'speech_recognizer': self.speech_recognizer.get_info(),
            'translator': self.translator.get_info(),
            'tts_engine': self.tts_engine.get_info(),
            'video_processor': self.video_processor.get_info(),
            'gpu_info': self.gpu_manager.get_gpu_info(),
            'temp_dir': str(self.temp_dir),
            'keep_temp': self.keep_temp
        }

    def _update_progress(self, percent: int, message: str) -> None:
        """
        Update progress

        Args:
            percent: Progress percentage (0-100)
            message: Progress message
        """
        self.logger.info(f"[{percent}%] {message}")

        if self.progress_callback:
            try:
                self.progress_callback(percent, message)
            except Exception as e:
                self.logger.warning(f"Progress callback failed: {e}")

    def _embed_subtitles_into_video(
        self,
        video_path: str,
        subtitle_files: List[str],
        output_path: str,
        source_lang: str,
        target_lang: str
    ) -> bool:
        """
        Embed subtitle tracks into video file

        Args:
            video_path: Path to input video
            subtitle_files: List of subtitle file paths
            output_path: Path to save output video
            source_lang: Source language code (e.g., 'en')
            target_lang: Target language code (e.g., 'ru')

        Returns:
            bool: True if successful
        """
        import subprocess

        # Language code mapping (2-letter to 3-letter ISO 639-2)
        lang_map = {
            'en': 'eng', 'ru': 'rus', 'es': 'spa', 'fr': 'fra', 'de': 'deu',
            'zh': 'chi', 'ja': 'jpn', 'ko': 'kor', 'it': 'ita', 'pt': 'por',
            'ar': 'ara', 'hi': 'hin', 'tr': 'tur', 'nl': 'nld', 'pl': 'pol'
        }

        # Filter SRT files only (FFmpeg mov_text works best with SRT)
        srt_files = [f for f in subtitle_files if f.endswith('.srt')]

        if not srt_files:
            self.logger.warning("No SRT subtitle files to embed")
            return False

        self.logger.info(f"Embedding {len(srt_files)} subtitle tracks into video")

        # Build FFmpeg command
        cmd = ['ffmpeg', '-y', '-i', video_path]

        # Add subtitle inputs
        for sub_file in srt_files:
            cmd.extend(['-i', sub_file])

        # Map video and audio from original
        cmd.extend(['-map', '0:v', '-map', '0:a'])

        # Map each subtitle track
        for i in range(len(srt_files)):
            cmd.extend(['-map', f'{i+1}:s'])

        # Copy video and audio codecs
        cmd.extend(['-c:v', 'copy', '-c:a', 'copy'])

        # Set subtitle codec to mov_text (required for QuickTime/MP4)
        cmd.extend(['-c:s', 'mov_text'])

        # IMPORTANT: Don't use -shortest when embedding subtitles
        # We want to preserve the full video/audio duration
        # Subtitles that extend beyond video will just not display
        # This prevents cutting the video to subtitle length

        # Set metadata for each subtitle track
        subtitle_index = 0
        for sub_file in srt_files:
            filename = Path(sub_file).stem

            # Determine language and label
            if 'original' in filename:
                lang_code = lang_map.get(source_lang, source_lang)
                label = f"{source_lang.upper()} (Original)"
            elif 'translated' in filename:
                lang_code = lang_map.get(target_lang, target_lang)
                label = f"{target_lang.upper()} (Translated)"
            else:
                lang_code = 'und'  # undefined
                label = "Subtitles"

            cmd.extend([
                f'-metadata:s:s:{subtitle_index}', f'language={lang_code}',
                f'-metadata:s:s:{subtitle_index}', f'title={label}'
            ])
            subtitle_index += 1

            self.logger.info(f"  Track {subtitle_index}: {label} [{lang_code}]")

        # Create temp output with different name
        temp_output = str(Path(output_path).with_suffix('.tmp.mp4'))
        cmd.append(temp_output)

        # Execute FFmpeg
        try:
            self.logger.info("Running FFmpeg to embed subtitles...")
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )

            # Replace original with embedded version
            import shutil
            shutil.move(temp_output, output_path)

            self.logger.info("✓ Subtitles embedded successfully")
            return True

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to embed subtitles: {e}")
            self.logger.error(f"FFmpeg error: {e.stderr}")

            # Clean up temp file if it exists
            if Path(temp_output).exists():
                Path(temp_output).unlink()

            return False

    def _cleanup_temp_files(self) -> None:
        """
        Cleanup temporary files
        """
        try:
            if self.temp_dir.exists():
                for file in self.temp_dir.glob('*'):
                    if file.is_file():
                        file.unlink()
                self.logger.info("Temporary files cleaned up")
        except Exception as e:
            self.logger.warning(f"Failed to cleanup temp files: {e}")

    def __repr__(self) -> str:
        """String representation"""
        return (
            f"VideoTranslationPipeline("
            f"speech={self.speech_recognizer.__class__.__name__}, "
            f"translation={self.translator.__class__.__name__}, "
            f"tts={self.tts_engine.__class__.__name__}, "
            f"video={self.video_processor.__class__.__name__}"
            f")"
        )
