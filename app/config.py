import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'agri-fumigacion-secure-key-2026')
    DB_PATH = BASE_DIR / 'fumigacion_agricola.db'
    
    # Priority: 1) DATABASE_URL environment variable, 2) Fallback to SQLite
    pg_url = os.environ.get('DATABASE_URL', '').strip()
    if pg_url.startswith('postgres://'):
        pg_url = pg_url.replace('postgres://', 'postgresql://', 1)
        
    sqlite_url = f'sqlite:///{DB_PATH}'
    
    use_pg = False
    if pg_url and 'sqlite' not in pg_url:
        try:
            from sqlalchemy import create_engine
            test_engine = create_engine(pg_url, connect_args={'connect_timeout': 3})
            with test_engine.connect() as conn:
                use_pg = True
        except Exception:
            use_pg = False

    if use_pg:
        SQLALCHEMY_DATABASE_URI = pg_url
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': int(os.environ.get('DB_POOL_SIZE', 10)),
            'max_overflow': int(os.environ.get('DB_MAX_OVERFLOW', 20)),
            'pool_timeout': 30,
            'pool_recycle': 1800,
            'pool_pre_ping': True,
        }
    else:
        SQLALCHEMY_DATABASE_URI = sqlite_url
        SQLALCHEMY_ENGINE_OPTIONS = {
            'connect_args': {'timeout': 30}
        }

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = str(BASE_DIR / 'uploads')
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # 64 MB
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() in ('true', '1', 't')
