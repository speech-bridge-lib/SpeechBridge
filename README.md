# SpeechBridge

**Modular Python framework for video translation with AI-powered speech synthesis and subtitle generation.**

[![PyPI version](https://badge.fury.io/py/speechbridge.svg)](https://pypi.org/project/speechbridge/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![DOI](https://zenodo.org/badge/1099076527.svg)](https://doi.org/10.5281/zenodo.17650387)
<!-- Общее количество скачиваний -->
![PyPI - Downloads](https://img.shields.io/pypi/dm/speechbridge?style=flat-square&color=green))



## Features

- **Automatic Speech Recognition**: OpenAI Whisper integration for accurate transcription
- **Translation**: DeepL API support for high-quality translations (30+ languages)
- **Text-to-Speech**: Edge TTS for natural-sounding voice synthesis
- **Audio Synchronization**: Preserves original speech timing and pauses
- **Subtitle Generation**: Creates and embeds SRT/VTT subtitles
- **Video Processing**: FFmpeg-based video/audio manipulation
- **Modular Architecture**: Easy to extend and customize components
- **Command-Line Interface**: Simple CLI for quick translations
- **Web Application**: Flask-based UI with drag-and-drop support

## Installation

### Requirements

- Python 3.10 or higher
- FFmpeg (for video processing)

### Install FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**Windows:**
Download from [ffmpeg.org](https://ffmpeg.org/download.html)

### Install SpeechBridge

```bash
# Clone the repository
git clone https://github.com/yourusername/speechbridge.git
cd speechbridge

# Install dependencies
pip install -r requirements.txt

# Optional: Install in development mode
pip install -e .
```

## Quick Start

### Command Line

```bash
# Set your DeepL API key
export DEEPL_API_KEY="your-api-key-here"

# Translate a video to Russian with subtitles
python3 -m speechbridge.cli translate input.mp4 output.mp4 \
  -t ru \
  --model tiny \
  --sync \
  --subtitles \
  --embed-subtitles

# Get DeepL API key at: https://www.deepl.com/pro-api
```

### Python API

```python
from speechbridge.core.builder import PipelineBuilder

# Build translation pipeline
pipeline = (PipelineBuilder()
    .with_whisper(model='tiny', language='auto')
    .with_deepl(api_key='your-api-key', target_lang='ru')
    .with_edge_tts()
    .with_ffmpeg()
    .with_temp_dir('temp')
    .build())

# Configure options
pipeline.config.sync_audio = True
pipeline.config.generate_subtitles = True
pipeline.config.embed_subtitles = True

# Translate video
result = pipeline.process_video('input.mp4', 'output.mp4')

if result['success']:
    print(f"Translation completed: {result['output_path']}")
else:
    print(f"Errors: {result['errors']}")
```

### Web Application

```bash
# Navigate to webapp directory
cd webapp

# Set DeepL API key
export DEEPL_API_KEY="your-api-key"

# Run the web app
python3 app.py
```

Then open http://localhost:5000 in your browser.

See [webapp/README.md](webapp/README.md) for detailed web app documentation.

## CLI Options

```
python3 -m speechbridge.cli translate INPUT OUTPUT [OPTIONS]

Arguments:
  INPUT                 Input video file path
  OUTPUT                Output video file path

Options:
  -t, --target-lang     Target language code (ru, en, es, de, etc.)
  --model              Whisper model size (tiny, base, small, medium, large)
  --sync               Enable audio synchronization with original timing
  --subtitles          Generate subtitle files (.srt)
  --embed-subtitles    Embed subtitles into video
  --subtitle-only      Generate subtitles only (no audio translation)
  --keep-temp          Keep temporary files for debugging
  -h, --help           Show help message
```

## Supported Languages

Arabic (ar), Bulgarian (bg), Chinese (zh), Czech (cs), Danish (da), Dutch (nl), English (en), Estonian (et), Finnish (fi), French (fr), German (de), Greek (el), Hungarian (hu), Indonesian (id), Italian (it), Japanese (ja), Korean (ko), Latvian (lv), Lithuanian (lt), Norwegian (nb), Polish (pl), Portuguese (pt), Romanian (ro), Russian (ru), Slovak (sk), Slovenian (sl), Spanish (es), Swedish (sv), Turkish (tr), Ukrainian (uk)

Full list: [DeepL Supported Languages](https://www.deepl.com/docs-api/translate-text/)

## Architecture

```
speechbridge/
├── cli/                      # Command-line interface
│   ├── __main__.py          # Entry point for CLI
│   └── main.py              # CLI argument parsing
├── components/              # Modular components
│   ├── audio/
│   │   └── sync.py          # Audio synchronization
│   ├── speech/
│   │   ├── base.py          # Base speech recognition
│   │   └── whisper.py       # Whisper integration
│   ├── translation/
│   │   ├── base.py          # Base translator
│   │   └── deepl.py         # DeepL integration
│   ├── tts/
│   │   ├── base.py          # Base TTS
│   │   └── edge_tts.py      # Edge TTS integration
│   ├── video/
│   │   ├── base.py          # Base video processor
│   │   └── processor.py     # FFmpeg processor
│   └── subtitles/
│       └── generator.py     # Subtitle generation
├── core/                    # Core framework
│   ├── builder.py           # Pipeline builder (Fluent API)
│   ├── pipeline.py          # Main pipeline orchestrator
│   ├── types.py             # Type definitions
│   ├── exceptions.py        # Custom exceptions
│   └── gpu.py               # GPU detection
├── utils/                   # Utilities
│   └── logging.py           # Logging configuration
└── tests/                   # Unit tests

webapp/                      # Web application
├── app.py                   # Flask application
├── templates/               # HTML templates
├── static/                  # CSS/JS assets
└── README.md                # Web app documentation
```

## Key Features Explained

### Audio Synchronization

SpeechBridge automatically preserves the original video's speech timing:

- **Initial silence detection**: Maintains silence before first speech segment
- **Inter-segment pauses**: Preserves gaps between speech segments
- **Duration matching**: Adjusts translated speech speed to match original timing

Implementation: `speechbridge/components/audio/sync.py`

### Modular Design

All components implement base interfaces and can be easily replaced:

```python
# Use different components
builder = (PipelineBuilder()
    .with_whisper(model='large')      # Swap Whisper model
    .with_deepl(target_lang='es')     # Change target language
    .with_edge_tts()                   # Use Edge TTS
    .with_ffmpeg()                     # Use FFmpeg processor
    .build())
```

### Pipeline Builder

Fluent API for constructing translation pipelines:

```python
pipeline = (PipelineBuilder()
    .with_whisper(model='tiny', language='auto')
    .with_deepl(api_key=key, target_lang='ru')
    .with_edge_tts()
    .with_ffmpeg()
    .with_temp_dir('temp')
    .keep_temporary_files(False)
    .build())

# Configure pipeline options
pipeline.config.sync_audio = True
pipeline.config.generate_subtitles = True
pipeline.config.embed_subtitles = True
pipeline.config.subtitle_only = False
```

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run all tests
pytest speechbridge/tests/

# Run with coverage
pytest --cov=speechbridge speechbridge/tests/
```

### Project Structure Guidelines

- `speechbridge/` - Core framework code (for PyPI)
- `webapp/` - Web application example
- Keep commercial/production code separate (not in repo)
- Follow modular component architecture

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Roadmap

- [x] Register on PyPI
- [ ] Support for additional TTS providers (Google TTS, ElevenLabs)
- [ ] Voice cloning capabilities
- [ ] Batch processing multiple videos
- [ ] GPU acceleration for Whisper
- [ ] Real-time progress tracking
- [ ] Docker containerization
- [ ] API rate limiting and quota management
- [ ] Multi-speaker detection and voice mapping

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) - Automatic speech recognition
- [DeepL API](https://www.deepl.com/pro-api) - High-quality translation
- [Edge TTS](https://github.com/rany2/edge-tts) - Text-to-speech synthesis
- [FFmpeg](https://ffmpeg.org/) - Video/audio processing

## Support

For issues, questions, or feature requests, please open an issue on GitHub.

## Authors

- Andrey Kolpakov - [@andreykolpakov](https://github.com/andreykolpakov)

---

**Note**: This framework is designed for legal use only. Ensure you have proper rights and permissions for any content you translate.
