"""
Flask Web Application for Video Translation
"""
import os
import uuid
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, session
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import threading
import sys

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path to import speechbridge
sys.path.insert(0, str(Path(__file__).parent.parent))

from speechbridge.core.builder import PipelineBuilder

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['UPLOAD_FOLDER'] = Path(__file__).parent / 'uploads'
app.config['OUTPUT_FOLDER'] = Path(__file__).parent / 'outputs'

# Ensure folders exist
app.config['UPLOAD_FOLDER'].mkdir(exist_ok=True)
app.config['OUTPUT_FOLDER'].mkdir(exist_ok=True)

# Store translation jobs
translation_jobs = {}

ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm', 'flv', 'wmv'}
SUPPORTED_LANGUAGES = {
    'ar': 'Arabic',
    'bg': 'Bulgarian',
    'cs': 'Czech',
    'da': 'Danish',
    'de': 'German',
    'el': 'Greek',
    'en': 'English',
    'es': 'Spanish',
    'et': 'Estonian',
    'fi': 'Finnish',
    'fr': 'French',
    'hu': 'Hungarian',
    'id': 'Indonesian',
    'it': 'Italian',
    'ja': 'Japanese',
    'ko': 'Korean',
    'lt': 'Lithuanian',
    'lv': 'Latvian',
    'nb': 'Norwegian',
    'nl': 'Dutch',
    'pl': 'Polish',
    'pt': 'Portuguese',
    'ro': 'Romanian',
    'ru': 'Russian',
    'sk': 'Slovak',
    'sl': 'Slovenian',
    'sv': 'Swedish',
    'tr': 'Turkish',
    'uk': 'Ukrainian',
    'zh': 'Chinese'
}

WHISPER_MODELS = ['tiny', 'base', 'small', 'medium', 'large']


class SimpleConfig:
    """Simple configuration object for web app"""
    def __init__(self, target_lang, whisper_model, sync_audio, generate_subtitles, embed_subtitles, subtitle_only):
        self.target_lang = target_lang
        self.whisper_model = whisper_model
        self.sync_audio = sync_audio
        self.generate_subtitles = generate_subtitles
        self.embed_subtitles = embed_subtitles
        self.subtitle_only = subtitle_only


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def translate_video_background(job_id, input_path, output_path, config):
    """Background task for video translation"""
    try:
        translation_jobs[job_id]['status'] = 'processing'
        translation_jobs[job_id]['progress'] = 'Initializing translation pipeline...'

        # Build pipeline using PipelineBuilder
        deepl_api_key = os.getenv('DEEPL_API_KEY')

        builder = (PipelineBuilder()
                   .with_whisper(model=config.whisper_model, language='auto')
                   .with_deepl(api_key=deepl_api_key, target_lang=config.target_lang)
                   .with_edge_tts()
                   .with_ffmpeg()
                   .with_temp_dir('temp')
                   .keep_temporary_files(False))

        # Configure pipeline options
        builder._pipeline_config['sync_audio'] = config.sync_audio
        builder._pipeline_config['generate_subtitles'] = config.generate_subtitles
        builder._pipeline_config['embed_subtitles'] = config.embed_subtitles
        builder._pipeline_config['subtitle_only'] = config.subtitle_only
        builder._pipeline_config['subtitle_format'] = 'srt'

        pipeline = builder.build()

        # Run translation
        translation_jobs[job_id]['progress'] = 'Transcribing video...'
        result = pipeline.process_video(str(input_path), str(output_path))

        if result['success']:
            translation_jobs[job_id]['status'] = 'completed'
            translation_jobs[job_id]['progress'] = 'Translation completed successfully!'
            translation_jobs[job_id]['result'] = {
                'output_file': output_path.name,
                'message': 'Video translated successfully'
            }
        else:
            translation_jobs[job_id]['status'] = 'failed'
            translation_jobs[job_id]['progress'] = f"Error: {', '.join(result.get('errors', ['Unknown error']))}"
            translation_jobs[job_id]['error'] = ', '.join(result.get('errors', ['Unknown error']))

    except Exception as e:
        translation_jobs[job_id]['status'] = 'failed'
        translation_jobs[job_id]['progress'] = f'Error: {str(e)}'
        translation_jobs[job_id]['error'] = str(e)


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html',
                         languages=SUPPORTED_LANGUAGES,
                         models=WHISPER_MODELS)


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and start translation"""
    try:
        # Check if file is present
        if 'video' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['video']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Supported: ' + ', '.join(ALLOWED_EXTENSIONS)}), 400

        # Get form parameters
        target_lang = request.form.get('target_lang', 'ru')
        whisper_model = request.form.get('whisper_model', 'tiny')
        sync_audio = request.form.get('sync_audio') == 'true'
        generate_subtitles = request.form.get('generate_subtitles') == 'true'
        embed_subtitles = request.form.get('embed_subtitles') == 'true'
        subtitle_only = request.form.get('subtitle_only') == 'true'

        # Create unique job ID
        job_id = str(uuid.uuid4())

        # Save uploaded file
        filename = secure_filename(file.filename)
        input_path = app.config['UPLOAD_FOLDER'] / f"{job_id}_{filename}"
        file.save(str(input_path))

        # Create output filename
        output_filename = f"translated_{job_id}.mp4"
        output_path = app.config['OUTPUT_FOLDER'] / output_filename

        # Create config
        config = SimpleConfig(
            target_lang=target_lang,
            whisper_model=whisper_model,
            sync_audio=sync_audio and not subtitle_only,
            generate_subtitles=generate_subtitles,
            embed_subtitles=embed_subtitles,
            subtitle_only=subtitle_only
        )

        # Initialize job
        translation_jobs[job_id] = {
            'status': 'queued',
            'progress': 'Upload completed, queued for processing...',
            'input_file': filename,
            'output_file': output_filename,
            'config': {
                'target_lang': target_lang,
                'whisper_model': whisper_model,
                'sync_audio': sync_audio,
                'generate_subtitles': generate_subtitles,
                'embed_subtitles': embed_subtitles,
                'subtitle_only': subtitle_only
            }
        }

        # Start background translation
        thread = threading.Thread(
            target=translate_video_background,
            args=(job_id, input_path, output_path, config)
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            'job_id': job_id,
            'message': 'Translation started',
            'status': 'queued'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/status/<job_id>')
def get_status(job_id):
    """Get translation job status"""
    if job_id not in translation_jobs:
        return jsonify({'error': 'Job not found'}), 404

    job = translation_jobs[job_id]
    return jsonify({
        'status': job['status'],
        'progress': job['progress'],
        'result': job.get('result'),
        'error': job.get('error')
    })


@app.route('/download/<job_id>')
def download_file(job_id):
    """Download translated video"""
    if job_id not in translation_jobs:
        return jsonify({'error': 'Job not found'}), 404

    job = translation_jobs[job_id]
    if job['status'] != 'completed':
        return jsonify({'error': 'Translation not completed'}), 400

    output_path = app.config['OUTPUT_FOLDER'] / job['output_file']
    if not output_path.exists():
        return jsonify({'error': 'Output file not found'}), 404

    return send_file(
        str(output_path),
        as_attachment=True,
        download_name=job['output_file']
    )


@app.route('/jobs')
def list_jobs():
    """List all translation jobs"""
    jobs = []
    for job_id, job_data in translation_jobs.items():
        jobs.append({
            'job_id': job_id,
            'status': job_data['status'],
            'input_file': job_data['input_file'],
            'config': job_data['config']
        })
    return jsonify({'jobs': jobs})


if __name__ == '__main__':
    # Get DeepL API key from environment
    if not os.getenv('DEEPL_API_KEY'):
        print("Warning: DEEPL_API_KEY environment variable not set!")
        print("Please set it before using the translation feature.")

    print("\n" + "="*60)
    print("Video Translation Web Application")
    print("="*60)
    print(f"Upload folder: {app.config['UPLOAD_FOLDER']}")
    print(f"Output folder: {app.config['OUTPUT_FOLDER']}")
    print("\nAccess the application at: http://localhost:5000")
    print("="*60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=5000)
