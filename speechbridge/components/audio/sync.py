"""
Audio Synchronization
=====================

Synchronize translated audio with original speech timing.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
import subprocess
import tempfile
from datetime import datetime

from speechbridge.core.exceptions import ComponentException


class AudioSynchronizer:
    """
    Audio synchronization for maintaining original speech timing

    Takes segmented transcription and creates synchronized translated audio
    that preserves original timing, including pauses and silences.
    """

    def __init__(self):
        """Initialize audio synchronizer"""
        self.logger = logging.getLogger('speechbridge.audiosync')

    def synchronize_segments(
        self,
        segments: List[Dict[str, Any]],
        translated_texts: List[str],
        output_dir: str,
        tts_engine,
        target_lang: str,
        total_duration: float,
        original_audio_path: Optional[str] = None
    ) -> tuple[str, List[Dict[str, Any]]]:
        """
        Synchronize translated audio segments with original timing

        Args:
            segments: Whisper segments with timing info
            translated_texts: Translated text for each segment
            output_dir: Directory for output files
            tts_engine: TTS engine instance
            target_lang: Target language code
            total_duration: Total video duration
            original_audio_path: Path to original audio for silence detection

        Returns:
            tuple: (Path to synchronized audio file, Corrected segments with adjusted timing)
        """
        if len(segments) != len(translated_texts):
            raise ComponentException(
                "Number of segments doesn't match translated texts",
                {'segments': len(segments), 'texts': len(translated_texts)}
            )

        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True, parents=True)

        self.logger.info(f"Synchronizing {len(segments)} audio segments")

        # Detect actual speech start time to correct Whisper timing
        actual_speech_start = 0.0
        if original_audio_path and segments:
            actual_speech_start = self._detect_speech_start(original_audio_path)

            # If first segment starts before actual speech, adjust it
            if segments[0]['start'] < actual_speech_start - 0.5:  # 500ms tolerance
                self.logger.info(
                    f"Detected silence at start: {actual_speech_start:.2f}s "
                    f"(Whisper reported: {segments[0]['start']:.2f}s)"
                )
                # Adjust first segment start time
                segments[0]['start'] = actual_speech_start

        # Step 1: Generate TTS for each segment
        segment_files = []
        for i, (seg, text) in enumerate(zip(segments, translated_texts)):
            segment_audio = output_path / f"segment_{i:04d}.wav"
            segment_audio_normalized = output_path / f"segment_norm_{i:04d}.wav"

            try:
                # Synthesize this segment
                tts_result = tts_engine.synthesize(
                    text,
                    str(segment_audio),
                    language=target_lang
                )

                original_duration = seg['end'] - seg['start']
                tts_duration = tts_result['duration']

                # Calculate speed adjustment needed
                speed_factor = tts_duration / original_duration if original_duration > 0 else 1.0

                # Always normalize and adjust to match original duration exactly
                if abs(speed_factor - 1.0) > 0.05:  # More than 5% difference
                    # Need to adjust speed to match timing
                    if speed_factor > 2.0:
                        # atempo has max limit of 2.0, need to chain filters
                        self.logger.debug(
                            f"Segment {i}: Large speed adjustment needed "
                            f"({tts_duration:.2f}s -> {original_duration:.2f}s, factor: {speed_factor:.2f}x)"
                        )
                        # Chain multiple atempo filters
                        atempo_filters = []
                        remaining_factor = speed_factor
                        while remaining_factor > 2.0:
                            atempo_filters.append('atempo=2.0')
                            remaining_factor /= 2.0
                        if remaining_factor > 0.5:  # atempo min is 0.5
                            atempo_filters.append(f'atempo={remaining_factor}')
                        filter_string = ','.join(atempo_filters)
                    elif speed_factor < 0.5:
                        # atempo has min limit of 0.5, need to chain
                        atempo_filters = []
                        remaining_factor = speed_factor
                        while remaining_factor < 0.5:
                            atempo_filters.append('atempo=0.5')
                            remaining_factor /= 0.5
                        if remaining_factor <= 2.0:
                            atempo_filters.append(f'atempo={remaining_factor}')
                        filter_string = ','.join(atempo_filters)
                    else:
                        # Single atempo filter is enough
                        filter_string = f'atempo={speed_factor}'

                    # Normalize format AND adjust speed to match original duration
                    normalize_cmd = [
                        'ffmpeg', '-y',
                        '-i', str(segment_audio),
                        '-filter:a', filter_string,
                        '-ac', '2',  # Stereo
                        '-ar', '44100',  # Sample rate
                        '-c:a', 'pcm_s16le',  # PCM format
                        str(segment_audio_normalized)
                    ]

                    self.logger.debug(
                        f"Segment {i}: Adjusting speed {tts_duration:.2f}s -> {original_duration:.2f}s (factor: {speed_factor:.2f}x)"
                    )
                else:
                    # Just normalize format, duration is close enough
                    normalize_cmd = [
                        'ffmpeg', '-y',
                        '-i', str(segment_audio),
                        '-ac', '2',  # Stereo
                        '-ar', '44100',  # Sample rate
                        '-c:a', 'pcm_s16le',  # PCM format
                        str(segment_audio_normalized)
                    ]

                subprocess.run(
                    normalize_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=60
                )

                # Use normalized file with adjusted duration
                used_file = str(segment_audio_normalized)
                used_duration = original_duration  # Now matches original exactly

                segment_info = {
                    'file': used_file,
                    'start': seg['start'],
                    'end': seg['end'],
                    'original_duration': original_duration,
                    'tts_duration': tts_duration,
                    'used_duration': used_duration,
                    'text': text
                }
                segment_files.append(segment_info)

                self.logger.debug(
                    f"Segment {i+1}/{len(segments)}: "
                    f"[{seg['start']:.2f}s - {seg['end']:.2f}s] "
                    f"TTS: {tts_duration:.2f}s -> {used_duration:.2f}s"
                )

            except Exception as e:
                self.logger.error(f"Failed to synthesize segment {i}: {e}")
                raise

        self.logger.info(f"Generated {len(segment_files)} TTS segments")

        # Step 2: Create timeline with silence padding
        timeline_file = output_path / f"timeline_{datetime.now().timestamp()}.txt"
        final_audio = output_path / f"synchronized_{datetime.now().timestamp()}.wav"

        self._create_synchronized_audio(
            segment_files,
            timeline_file,
            final_audio,
            total_duration
        )

        self.logger.info(f"Synchronized audio created: {final_audio}")

        return str(final_audio), segments

    def _create_synchronized_audio(
        self,
        segments: List[Dict[str, Any]],
        timeline_file: Path,
        output_file: Path,
        total_duration: float
    ) -> None:
        """
        Create synchronized audio using silence and concatenation

        Args:
            segments: List of segment info dicts
            timeline_file: Path to timeline file
            output_file: Path to output audio
            total_duration: Total duration in seconds
        """
        # Strategy: Create concat demuxer file with silence padding
        # This ensures segments don't overlap

        concat_file = timeline_file
        concat_entries = []

        current_time = 0.0
        temp_files = []

        for i, seg in enumerate(segments):
            # Add silence if needed before this segment
            if seg['start'] > current_time:
                silence_duration = seg['start'] - current_time
                silence_file = output_file.parent / f"silence_{i:04d}.wav"

                # Create silence using ffmpeg
                silence_cmd = [
                    'ffmpeg', '-y',
                    '-f', 'lavfi',
                    '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100',
                    '-t', str(silence_duration),
                    '-c:a', 'pcm_s16le',
                    str(silence_file)
                ]

                subprocess.run(
                    silence_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=60
                )

                concat_entries.append(f"file '{Path(silence_file).absolute()}'")
                temp_files.append(silence_file)
                current_time = seg['start']

            # Add the actual segment with EXACT duration control
            exact_duration = seg['end'] - seg['start']

            # Create segment file with exact duration
            exact_file = output_file.parent / f"exact_{i:04d}.wav"

            # Strategy:
            # 1. First trim segment to MAXIMUM exact_duration using -t flag (this ACTUALLY works)
            # 2. Check actual duration with ffprobe
            # 3. If shorter, pad to exact_duration with silence

            # Step 1: Trim to max duration (will cut if longer, pass through if shorter)
            trimmed_file = output_file.parent / f"trimmed_{i:04d}.wav"

            trim_cmd = [
                'ffmpeg', '-y',
                '-i', str(seg['file']),
                '-t', str(exact_duration),  # Hard limit - cuts at this duration
                '-c:a', 'pcm_s16le',
                str(trimmed_file)
            ]

            subprocess.run(
                trim_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60
            )

            # Step 2: Get actual duration
            probe_cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(trimmed_file)
            ]

            probe_result = subprocess.run(
                probe_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30
            )

            actual_duration = float(probe_result.stdout.strip())

            # Step 3: Pad if needed
            if actual_duration < exact_duration - 0.001:  # 1ms tolerance
                padding_needed = exact_duration - actual_duration

                # Create padding silence
                padding_file = output_file.parent / f"padding_{i:04d}.wav"

                pad_cmd = [
                    'ffmpeg', '-y',
                    '-f', 'lavfi',
                    '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100',
                    '-t', str(padding_needed),
                    '-c:a', 'pcm_s16le',
                    str(padding_file)
                ]

                subprocess.run(
                    pad_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=60
                )

                # Concatenate trimmed + padding
                concat_list_file = output_file.parent / f"concat_{i:04d}.txt"
                concat_list_file.write_text(
                    f"file '{trimmed_file.absolute()}'\n"
                    f"file '{padding_file.absolute()}'"
                )

                concat_cmd = [
                    'ffmpeg', '-y',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(concat_list_file),
                    '-c:a', 'pcm_s16le',
                    str(exact_file)
                ]

                subprocess.run(
                    concat_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=60
                )

                temp_files.extend([trimmed_file, padding_file, concat_list_file])
            else:
                # Duration is already exact (or close enough), just use trimmed file
                exact_file = trimmed_file

            concat_entries.append(f"file '{Path(exact_file).absolute()}'")
            temp_files.append(exact_file)

            # Update current_time to END of this segment (from original timing)
            # This ensures we track the timeline according to Whisper segments
            current_time = seg['end']

        # Calculate exact final silence needed to reach total_duration
        # current_time should be at the end of the last segment
        final_silence_needed = total_duration - current_time

        if final_silence_needed > 0.001:  # Add silence if needed (tolerance 1ms)
            final_silence_file = output_file.parent / "silence_final.wav"

            # Create exact silence duration using sample count for precision
            # 44100 samples/sec * duration = exact sample count
            sample_count = int(final_silence_needed * 44100)

            # Generate silence with exact sample count
            silence_cmd = [
                'ffmpeg', '-y',
                '-f', 'lavfi',
                '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100',
                '-t', str(final_silence_needed),
                '-c:a', 'pcm_s16le',
                str(final_silence_file)
            ]

            subprocess.run(
                silence_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60
            )

            concat_entries.append(f"file '{Path(final_silence_file).absolute()}'")
            temp_files.append(final_silence_file)

            self.logger.info(
                f"Added final silence: {final_silence_needed:.3f}s "
                f"to reach total duration {total_duration:.3f}s"
            )

        # Write concat file
        concat_file.write_text('\n'.join(concat_entries))

        # Build ffmpeg command using concat demuxer
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-ac', '2',  # Stereo
            '-ar', '44100',  # Sample rate
            str(output_file)
        ]

        self.logger.debug(f"Running ffmpeg with {len(segments)} inputs")

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.returncode != 0:
                self.logger.error(f"ffmpeg error: {result.stderr}")
                raise ComponentException(
                    "Failed to create synchronized audio",
                    {'error': result.stderr[:200]}
                )

            self.logger.info("Audio synchronization complete")

        except subprocess.TimeoutExpired:
            raise ComponentException("Audio synchronization timed out")
        except Exception as e:
            raise ComponentException(
                f"Audio synchronization failed: {e}"
            )

    def _detect_speech_start(self, audio_path: str) -> float:
        """
        Detect when speech actually starts in the audio

        Args:
            audio_path: Path to audio file

        Returns:
            float: Time in seconds when speech starts
        """
        try:
            # Use ffmpeg silencedetect to find when silence ends
            cmd = [
                'ffmpeg',
                '-i', audio_path,
                '-af', 'silencedetect=noise=-30dB:d=0.5',
                '-f', 'null',
                '-'
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60
            )

            # Parse output for first silence_end
            for line in result.stderr.split('\n'):
                if 'silence_end:' in line:
                    # Extract time: "silence_end: 8.14575 | silence_duration: 8.14575"
                    parts = line.split('silence_end:')[1].split('|')[0].strip()
                    speech_start = float(parts)
                    self.logger.debug(f"Detected speech start at {speech_start:.2f}s")
                    return speech_start

            # No silence detected at start, speech starts at 0
            return 0.0

        except Exception as e:
            self.logger.warning(f"Failed to detect speech start: {e}")
            return 0.0

    def translate_segments(
        self,
        segments: List[Dict[str, Any]],
        translator,
        source_lang: str,
        target_lang: str
    ) -> List[str]:
        """
        Translate each segment individually to preserve timing

        Args:
            segments: Whisper segments
            translator: Translator instance
            source_lang: Source language
            target_lang: Target language

        Returns:
            List[str]: Translated text for each segment
        """
        self.logger.info(f"Translating {len(segments)} segments")

        translated_texts = []

        for i, seg in enumerate(segments):
            text = seg['text'].strip()

            if not text:
                translated_texts.append("")
                continue

            try:
                result = translator.translate(
                    text,
                    source_lang=source_lang,
                    target_lang=target_lang
                )
                translated_texts.append(result['text'])

                self.logger.debug(
                    f"Segment {i+1}/{len(segments)}: "
                    f"{len(text)} -> {len(result['text'])} chars"
                )

            except Exception as e:
                self.logger.error(f"Failed to translate segment {i}: {e}")
                # Use original text as fallback
                translated_texts.append(text)

        self.logger.info(f"Translated {len(translated_texts)} segments")

        return translated_texts
