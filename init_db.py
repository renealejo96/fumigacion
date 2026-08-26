import os
import sys
import time
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app import create_app
from app.extensions import db
from app.shared.models import User, Crop
from seed_data import seed_database

def wait_for_db(max_retries=30, delay=2):
    """Wait for database to become available before proceeding."""
    pg_url = os.environ.get('DATABASE_URL', '').strip()
    if pg_url.startswith('postgres://'):
        pg_url = pg_url.replace('postgres://', 'postgresql://', 1)
        
    if not pg_url or 'sqlite' in pg_url:
        print("[Init DB] Using SQLite database. No wait required.")
        return True

    print(f"[Init DB] Waiting for PostgreSQL at {pg_url.split('@')[-1] if '@' in pg_url else 'configured host'}...")
    from sqlalchemy import create_engine
    
    for attempt in range(1, max_retries + 1):
        try:
            engine = create_engine(pg_url, connect_args={'connect_timeout': 3})
            with engine.connect() as conn:
                print(f"[Init DB] Database is ready! (Connected on attempt {attempt})")
                return True
        except Exception as e:
            print(f"[Init DB] DB not ready yet (attempt {attempt}/{max_retries}): {e}")
            time.sleep(delay)
    
    print("[Init DB] Error: Could not connect to PostgreSQL after multiple attempts.")
    return False

def init_application():
    """Create tables, seed initial data, and guarantee admin user."""
    print("==========================================")
    print("  AgroFumigación - Database Initialization")
    print("==========================================")
    
    wait_for_db()
    
    app = create_app()
    with app.app_context():
        print("[Init DB] Creating tables...")
        db.create_all()
        
        # 1. Guarantee default admin user
        admin_user = User.query.filter_by(role='ADMIN').first()
        admin_pass = os.environ.get('ADMIN_PASSWORD', 'admin123')
        if not admin_user:
            print("[Init DB] Creating default admin user...")
            new_admin = User(
                username='admin',
                full_name='Administrador Principal',
                role='ADMIN',
                permissions=[
                    'fumigacion', 'ordenes_ver', 'ordenes_imprimir', 'salidas_ver', 'salidas_imprimir',
                    'aplicaciones_extras', 'orden_compra', 'drench', 'trichos', 'desinfecciones',
                    'catalogos', 'importador', 'bodega'
                ]
            )
            new_admin.set_password(admin_pass)
            db.session.add(new_admin)
            db.session.commit()
            print(f"[Init DB] Default admin user created (username: admin, default password configured).")
        else:
            print(f"[Init DB] Admin user already exists (username: {admin_user.username}).")

        # 2. Seed initial data if crops table is empty
        crop_count = Crop.query.count()
        if crop_count == 0:
            print("[Init DB] Master catalogs are empty. Running initial seed...")
            try:
                seed_database(reset=False)
                print("[Init DB] Seed data initialized successfully.")
            except Exception as e:
                print(f"[Init DB] Warning during seed data initialization: {e}")
        else:
            print(f"[Init DB] Database already contains {crop_count} crops. Skipping seed.")

    print("==========================================")
    print("  Initialization finished successfully!")
    print("==========================================")

if __name__ == '__main__':
    init_application()
