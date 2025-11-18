# Video Translation Web Application

Web application for video translation with AI speech synthesis and subtitles.

## Features

- Upload videos via browser (drag & drop)
- Support for 30+ languages (via DeepL API)
- AI speech synthesis (Edge TTS)
- Subtitle generation and embedding
- Audio synchronization with original timing
- Real-time progress tracking
- Download translated videos

## Installation

### 1. Install Flask dependencies:

```bash
pip install -r webapp/requirements.txt
```

### 2. Install main project dependencies:

```bash
pip install -r requirements.txt
```

### 3. Configure DeepL API key:

**Important for security:** Do not store API keys in code!

**Option 1 (recommended): Using .env file**

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your API key
# DEEPL_API_KEY=your-actual-api-key-here
```

**Option 2: Environment variable**

```bash
export DEEPL_API_KEY="your-deepl-api-key-here"
```

**Get API key:** https://www.deepl.com/pro-api

> **Note:** The `.env` file is already added to `.gitignore` and will not be uploaded to GitHub

## Running

### Simple run:

```bash
cd webapp
export DEEPL_API_KEY="your-api-key"
python app.py
```

The application will be available at: **http://localhost:5000**

### Production run (with Gunicorn):

```bash
pip install gunicorn
export DEEPL_API_KEY="your-api-key"
cd webapp
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Usage

1. **Open browser** and go to http://localhost:5000

2. **Upload video**:
   - Click on the upload area or drag and drop a file
   - Supported formats: MP4, MOV, AVI, MKV, WebM, FLV, WMV
   - Maximum size: 500 MB

3. **Configure parameters**:
   - **Target Language**: Target translation language (Russian by default)
   - **Whisper Model**: Speech recognition model (tiny/base/small/medium/large)
     - `tiny` - fast but less accurate
     - `large` - slow but most accurate

   **Options**:
   - **Sync Audio**: Synchronize translated speech duration with original
   - **Generate Subtitles**: Create subtitle files (.srt)
   - **Embed Subtitles**: Embed subtitles in video
   - **Subtitle Only**: Subtitles only (no audio translation)

4. **Start translation**:
   - Click "Start Translation"
   - Track progress in real-time
   - Download result when complete

## Project Structure

```
webapp/
├── app.py                 # Flask application (backend)
├── requirements.txt       # Python dependencies
├── README.md             # Documentation
├── static/
│   ├── css/
│   │   └── style.css     # Interface styles
│   └── js/
│       └── app.js        # Frontend logic
├── templates/
│   └── index.html        # HTML template
├── uploads/              # Uploaded videos (created automatically)
└── outputs/              # Translated videos (created automatically)
```

## API Endpoints

### POST /upload
Upload video and start translation.

**Form Data**:
- `video`: Video file
- `target_lang`: Target language (e.g., "ru")
- `whisper_model`: Whisper model ("tiny", "base", "small", "medium", "large")
- `sync_audio`: "true" or "false"
- `generate_subtitles`: "true" or "false"
- `embed_subtitles`: "true" or "false"
- `subtitle_only`: "true" or "false"

**Response**:
```json
{
  "job_id": "uuid",
  "message": "Translation started",
  "status": "queued"
}
```

### GET /status/<job_id>
Check translation status.

**Response**:
```json
{
  "status": "processing",
  "progress": "Transcribing video...",
  "result": null,
  "error": null
}
```

### GET /download/<job_id>
Download translated video.

### GET /jobs
List all translations.

**Response**:
```json
{
  "jobs": [
    {
      "job_id": "uuid",
      "status": "completed",
      "input_file": "video.mp4",
      "config": {...}
    }
  ]
}
```

## Supported Languages

Arabic, Bulgarian, Czech, Danish, German, Greek, English, Spanish, Estonian,
Finnish, French, Hungarian, Indonesian, Italian, Japanese, Korean, Lithuanian,
Latvian, Norwegian, Dutch, Polish, Portuguese, Romanian, Russian, Slovak,
Slovenian, Swedish, Turkish, Ukrainian, Chinese

## Technologies

- **Backend**: Flask, Python 3.10+
- **Frontend**: Vanilla JavaScript, HTML5, CSS3
- **AI/ML**:
  - OpenAI Whisper (transcription)
  - DeepL API (translation)
  - Edge TTS (speech synthesis)
- **Video**: FFmpeg

## Notes

- Translation process may take several minutes depending on video length and selected Whisper model
- For long videos, it is recommended to use the `tiny` or `base` model
- Make sure you have enough disk space for uploaded and translated videos
- Translated videos are stored in the `outputs/` folder
- Translation history is lost on server restart (jobs are stored in memory)

## Future Improvements

- [ ] Database for storing translation history
- [ ] User authentication
- [ ] WebSocket for real-time progress updates
- [ ] Support for batch processing of multiple videos
- [ ] Video preview in browser
- [ ] Job queue management
- [ ] Automatic cleanup of old files
- [ ] Docker containerization
- [ ] API rate limiting
- [ ] Logging and monitoring

## License

MIT License

## Support

For questions and suggestions, create issues in the project repository.
