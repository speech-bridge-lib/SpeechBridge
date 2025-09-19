#!/usr/bin/env python3
"""
Конфигурация проекта Video-Translator
Все настройки, пути и параметры в одном  месте
"""


import os
import yaml
from pathlib import Path
from typing import Dict, Any, Set
from dotenv import load_dotenv

# Загружаем переменные окружения из корня проекта
project_root = Path(__file__).parent.parent
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path)


class Config:
    """Основная конфигурация приложения"""
    
    # === БАЗОВЫЕ ПУТИ ===
    PROJECT_ROOT = Path(__file__).parent.parent.resolve()
    SRC_DIR = PROJECT_ROOT / "src"
    CONFIG_FILE = PROJECT_ROOT / "config.yaml"
    
    # === РАБОЧИЕ ДИРЕКТОРИИ ===
    UPLOAD_FOLDER = PROJECT_ROOT / "uploads"
    OUTPUT_FOLDER = PROJECT_ROOT / "outputs"
    TEMP_FOLDER = SRC_DIR / "temp"
    LOGS_FOLDER = PROJECT_ROOT / "logs"
    TEMPLATES_FOLDER = PROJECT_ROOT / "templates"
    STATIC_FOLDER = PROJECT_ROOT / "static"
    
    # === FLASK НАСТРОЙКИ ===
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024  # 500MB по умолчанию
    
    # === НАСТРОЙКИ ОБРАБОТКИ ФАЙЛОВ ===
    ALLOWED_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
    MAX_FILE_SIZE_MB = int(os.getenv('MAX_FILE_SIZE_MB', '500'))
    MAX_DURATION_MINUTES = int(os.getenv('MAX_DURATION_MINUTES', '60'))
    
    # === АУДИО ПАРАМЕТРЫ ===
    AUDIO_SAMPLE_RATE = 16000
    AUDIO_CHANNELS = 1
    AUDIO_FORMAT = 'wav'
    
    # === ПАРАМЕТРЫ СЕГМЕНТАЦИИ ===
    MIN_SILENCE_LEN = 1000  # миллисекунды
    SILENCE_THRESH = -40    # дБ
    KEEP_SILENCE = 500      # миллисекунды
    
    # === НАСТРОЙКИ КАЧЕСТВА ===
    VIDEO_CODEC = 'libx264'
    AUDIO_CODEC = 'aac'
    
    # === ЛОГИРОВАНИЕ ===
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE = LOGS_FOLDER / "video_translator.log"
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # === API НАСТРОЙКИ ===
    # Speech Recognition
    SPEECH_API_KEY = os.getenv('GOOGLE_SPEECH_API_KEY')
    SPEECH_LANGUAGE = 'en-US'
    
    # Translation  
    TRANSLATE_API_KEY = os.getenv('GOOGLE_TRANSLATE_API_KEY')
    SOURCE_LANGUAGE = 'en'
    TARGET_LANGUAGE = 'ru'
    
    # Text-to-Speech
    TTS_API_KEY = os.getenv('GOOGLE_TTS_API_KEY')
    TTS_LANGUAGE = 'ru'
    TTS_VOICE = 'ru-RU-Standard-A'
    # Принудительное использование только pyttsx3
    FORCE_PYTTSX3_ONLY = True
    TTS_ENGINE_PRIORITY = ['pyttsx3']  # только pyttsx3

    # === ЭКСПЕРИМЕНТАЛЬНЫЕ ФУНКЦИИ ===
    USE_SPEAKER_DIARIZATION = True   # Сегментация по спикерам
    USE_ADAPTIVE_VIDEO_TIMING = False  # Адаптивная синхронизация видео - ОТКЛЮЧЕНО ДЛЯ ТЕСТА
    ADJUST_VIDEO_SPEED = True  # Замедление видео по сегментам для синхронизации
    
    # === ДОПОЛНИТЕЛЬНЫЕ API ===
    DEEPL_API_KEY = os.getenv('DEEPL_API_KEY')
    ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY')
    
    def __init__(self):
        """Инициализация конфигурации"""
        self._load_yaml_config()
        self.create_directories()
    
    def _load_yaml_config(self):
        """Загрузка настроек из YAML файла"""
        if self.CONFIG_FILE.exists():
            try:
                with open(self.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    yaml_config = yaml.safe_load(f)
                    self._apply_yaml_config(yaml_config)
            except Exception as e:
                print(f"Предупреждение: Не удалось загрузить config.yaml: {e}")
    
    def _apply_yaml_config(self, yaml_config: Dict[str, Any]):
        """Применение настроек из YAML"""
        # API настройки
        if 'api' in yaml_config:
            api_config = yaml_config['api']
            
            # Speech Recognition
            if 'speech_recognition' in api_config:
                sr_config = api_config['speech_recognition']
                if 'google' in sr_config:
                    self.SPEECH_LANGUAGE = sr_config['google'].get('language', self.SPEECH_LANGUAGE)
            
            # Text-to-Speech
            if 'text_to_speech' in api_config:
                tts_config = api_config['text_to_speech']
                if 'google' in tts_config:
                    google_tts = tts_config['google']
                    self.TTS_VOICE = google_tts.get('voice_name', self.TTS_VOICE)
        
        # Настройки обработки
        if 'processing' in yaml_config:
            proc_config = yaml_config['processing']
            
            # Сегментация аудио
            if 'audio_segmentation' in proc_config:
                seg_config = proc_config['audio_segmentation']
                self.MIN_SILENCE_LEN = int(seg_config.get('min_silence_duration', 1.0) * 1000)
                self.SILENCE_THRESH = seg_config.get('silence_threshold', self.SILENCE_THRESH)
            
            # Качество
            if 'quality' in proc_config:
                quality_config = proc_config['quality']
                self.AUDIO_SAMPLE_RATE = quality_config.get('audio_sample_rate', self.AUDIO_SAMPLE_RATE)
                self.AUDIO_CHANNELS = quality_config.get('audio_channels', self.AUDIO_CHANNELS)
                self.VIDEO_CODEC = quality_config.get('video_codec', self.VIDEO_CODEC)
                self.AUDIO_CODEC = quality_config.get('audio_codec', self.AUDIO_CODEC)
        
        # Логирование
        if 'logging' in yaml_config:
            log_config = yaml_config['logging']
            self.LOG_LEVEL = log_config.get('level', self.LOG_LEVEL)
            if 'file_path' in log_config:
                self.LOG_FILE = self.PROJECT_ROOT / log_config['file_path']
    
    def create_directories(self):
        """Создание необходимых директорий"""
        directories = [
            self.UPLOAD_FOLDER,
            self.OUTPUT_FOLDER,
            self.TEMP_FOLDER,
            self.LOGS_FOLDER,
            self.TEMPLATES_FOLDER,
            self.STATIC_FOLDER,
        ]
        
        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                print(f"Предупреждение: Не удалось создать директорию {directory}: {e}")
    
    def get_file_path(self, folder_type: str, filename: str) -> Path:
        """Получение полного пути к файлу"""
        folder_map = {
            'upload': self.UPLOAD_FOLDER,
            'output': self.OUTPUT_FOLDER,
            'temp': self.TEMP_FOLDER,
            'logs': self.LOGS_FOLDER,
            'templates': self.TEMPLATES_FOLDER,
            'static': self.STATIC_FOLDER,
        }
        
        folder = folder_map.get(folder_type)
        if not folder:
            raise ValueError(f"Неизвестный тип папки: {folder_type}")
        
        return folder / filename
    
    def is_allowed_file(self, filename: str) -> bool:
        """Проверка расширения файла"""
        if not filename:
            return False
        
        file_ext = Path(filename).suffix.lower()
        return file_ext in self.ALLOWED_EXTENSIONS
    
    def validate_file_size(self, file_size: int) -> bool:
        """Валидация размера файла"""
        max_size = self.MAX_FILE_SIZE_MB * 1024 * 1024
        return file_size <= max_size
    
    def get_temp_filename(self, prefix: str = "", extension: str = ".tmp") -> Path:
        """Генерация имени временного файла"""
        import uuid
        filename = f"{prefix}_{uuid.uuid4().hex}{extension}"
        return self.TEMP_FOLDER / filename
    
    def get_api_config(self) -> Dict[str, Any]:
        """Получение конфигурации API"""
        return {
            'speech_recognition': {
                'api_key': self.SPEECH_API_KEY,
                'language': self.SPEECH_LANGUAGE,
            },
            'translation': {
                'api_key': self.TRANSLATE_API_KEY,
                'source_lang': self.SOURCE_LANGUAGE,
                'target_lang': self.TARGET_LANGUAGE,
                'deepl_api_key': self.DEEPL_API_KEY,
            },
            'text_to_speech': {
                'api_key': self.TTS_API_KEY,
                'language': self.TTS_LANGUAGE,
                'voice': self.TTS_VOICE,
                'elevenlabs_api_key': self.ELEVENLABS_API_KEY,
            }
        }
    
    def get_processing_config(self) -> Dict[str, Any]:
        """Получение конфигурации обработки"""
        return {
            'audio': {
                'sample_rate': self.AUDIO_SAMPLE_RATE,
                'channels': self.AUDIO_CHANNELS,
                'format': self.AUDIO_FORMAT,
            },
            'segmentation': {
                'min_silence_len': self.MIN_SILENCE_LEN,
                'silence_thresh': self.SILENCE_THRESH,
                'keep_silence': self.KEEP_SILENCE,
            },
            'codecs': {
                'video': self.VIDEO_CODEC,
                'audio': self.AUDIO_CODEC,
            }
        }
    
    def __str__(self) -> str:
        """Строковое представление конфигурации"""
        return f"""
Video-Translator Configuration:
├── Project Root: {self.PROJECT_ROOT}
├── Upload Folder: {self.UPLOAD_FOLDER}
├── Output Folder: {self.OUTPUT_FOLDER}
├── Temp Folder: {self.TEMP_FOLDER}
├── Logs Folder: {self.LOGS_FOLDER}
├── Max File Size: {self.MAX_FILE_SIZE_MB}MB
├── Allowed Extensions: {', '.join(self.ALLOWED_EXTENSIONS)}
├── Audio Sample Rate: {self.AUDIO_SAMPLE_RATE}Hz
├── Video Codec: {self.VIDEO_CODEC}
└── Audio Codec: {self.AUDIO_CODEC}
        """.strip()


class DevelopmentConfig(Config):
    """Конфигурация для разработки"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Конфигурация для продакшена"""
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.getenv('FLASK_SECRET_KEY', os.urandom(32))


class TestingConfig(Config):
    """Конфигурация для тестирования"""
    DEBUG = True
    TESTING = True
    
    # Переопределяем пути для тестов
    def __init__(self):
        super().__init__()
        # Создаем временные директории для тестов
        import tempfile
        self.temp_dir = Path(tempfile.mkdtemp())
        self.UPLOAD_FOLDER = self.temp_dir / "uploads"
        self.OUTPUT_FOLDER = self.temp_dir / "outputs"
        self.TEMP_FOLDER = self.temp_dir / "temp"
        self.LOGS_FOLDER = self.temp_dir / "logs"
        self.create_directories()


def get_config(env: str = None) -> Config:
    """Фабрика конфигураций"""
    env = env or os.getenv('FLASK_ENV', 'development')
    
    config_map = {
        'development': DevelopmentConfig,
        'production': ProductionConfig,
        'testing': TestingConfig,
    }
    
    config_class = config_map.get(env, DevelopmentConfig)
    return config_class()


# Создание глобального экземпляра конфигурации
config = get_config()


if __name__ == "__main__":
    # Тестирование конфигурации
    print("=== Тестирование конфигурации ===")
    print(config)
    
    print("\n=== API Config ===")
    api_config = config.get_api_config()
    for service, settings in api_config.items():
        print(f"{service}: {settings}")
    
    print("\n=== Processing Config ===") 
    proc_config = config.get_processing_config()
    for category, settings in proc_config.items():
        print(f"{category}: {settings}")
    
    print("\n=== Validation Tests ===")
    print(f"test.mp4 allowed: {config.is_allowed_file('test.mp4')}")
    print(f"test.txt allowed: {config.is_allowed_file('test.txt')}")
    print(f"100MB file valid: {config.validate_file_size(100 * 1024 * 1024)}")
    print(f"600MB file valid: {config.validate_file_size(600 * 1024 * 1024)}")
