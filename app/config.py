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
    
    # Check if PostgreSQL connection can be established, otherwise use SQLite
    if not pg_url or 'sqlite' in pg_url:
        SQLALCHEMY_DATABASE_URI = sqlite_url
    else:
        try:
            from sqlalchemy import create_engine
            engine = create_engine(pg_url, connect_args={'connect_timeout': 3})
            with engine.connect() as conn:
                pass
            SQLALCHEMY_DATABASE_URI = pg_url
            print(f"[Database] Connected to PostgreSQL: {pg_url.split('@')[-1] if '@' in pg_url else 'configured DB'}")
        except Exception as e:
            print(f"[Database] PostgreSQL connection failed ({e}). Falling back to SQLite database at {DB_PATH}")
            SQLALCHEMY_DATABASE_URI = sqlite_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = str(BASE_DIR / 'uploads')
    MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # 64 MB
    DEBUG = True
