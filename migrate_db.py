"""
Script de migración para agregar nuevos campos a las tablas
Ejecutar este script para actualizar la base de datos con los nuevos campos:

TABLA rotations:
- applied_rounds_json: JSON con los IDs de las vueltas donde se aplica la configuración
- confirmed_rounds_json: JSON con el estado de confirmación de vueltas

TABLA crop_state_records:
- week: Identificación de semana del plano de estado de cultivo

TABLA rotations (si no existe):
- week: Semana de la rotación

TABLA requisitions (si no existe):
- week: Semana de la requisición

TABLA drench_applications (si no existe):
- week: Semana de la aplicación drench

TABLA tricho_applications (si no existe):
- week: Semana de la aplicación tricho

TABLA disinfection_applications (si no existe):
- week: Semana de la aplicación desinfección
"""

from app import create_app
from app.extensions import db

def migrate_database():
    app = create_app()
    with app.app_context():
        # Agregar columnas si no existen
        with db.engine.connect() as conn:
            try:
                print("Iniciando migración de base de datos...\n")
                
                # Función auxiliar para verificar si tabla existe
                def table_exists(table_name):
                    result = conn.execute(db.text(
                        f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
                    ))
                    return result.fetchone() is not None
                
                # TABLA rotations
                if table_exists('rotations'):
                    print("Verificando tabla 'rotations'...")
                    result = conn.execute(db.text("PRAGMA table_info(rotations)"))
                    columns = [row[1] for row in result.fetchall()]
                    
                    if 'applied_rounds_json' not in columns:
                        conn.execute(db.text("ALTER TABLE rotations ADD COLUMN applied_rounds_json TEXT"))
                        print("  ✓ Columna 'applied_rounds_json' agregada")
                    else:
                        print("  - Columna 'applied_rounds_json' ya existe")
                    
                    if 'confirmed_rounds_json' not in columns:
                        conn.execute(db.text("ALTER TABLE rotations ADD COLUMN confirmed_rounds_json TEXT"))
                        print("  ✓ Columna 'confirmed_rounds_json' agregada")
                    else:
                        print("  - Columna 'confirmed_rounds_json' ya existe")
                else:
                    print("⚠ Tabla 'rotations' no existe aún")
                
                # TABLA crop_state_records
                if table_exists('crop_state_records'):
                    print("\nVerificando tabla 'crop_state_records'...")
                    result = conn.execute(db.text("PRAGMA table_info(crop_state_records)"))
                    columns = [row[1] for row in result.fetchall()]
                    
                    if 'week' not in columns:
                        conn.execute(db.text("ALTER TABLE crop_state_records ADD COLUMN week VARCHAR(20) DEFAULT '2026-33'"))
                        conn.execute(db.text("CREATE INDEX IF NOT EXISTS ix_crop_state_records_week ON crop_state_records (week)"))
                        print("  ✓ Columna 'week' agregada con índice")
                    else:
                        print("  - Columna 'week' ya existe")
                else:
                    print("\n⚠ Tabla 'crop_state_records' no existe aún")
                
                # TABLA requisitions
                if table_exists('requisitions'):
                    print("\nVerificando tabla 'requisitions'...")
                    result = conn.execute(db.text("PRAGMA table_info(requisitions)"))
                    columns = [row[1] for row in result.fetchall()]
                    
                    if 'week' not in columns:
                        conn.execute(db.text("ALTER TABLE requisitions ADD COLUMN week VARCHAR(20)"))
                        conn.execute(db.text("CREATE INDEX IF NOT EXISTS ix_requisitions_week ON requisitions (week)"))
                        print("  ✓ Columna 'week' agregada con índice")
                    else:
                        print("  - Columna 'week' ya existe")
                else:
                    print("\n⚠ Tabla 'requisitions' no existe aún")
                
                # TABLA drench_applications
                if table_exists('drench_applications'):
                    print("\nVerificando tabla 'drench_applications'...")
                    result = conn.execute(db.text("PRAGMA table_info(drench_applications)"))
                    columns = [row[1] for row in result.fetchall()]
                    
                    if 'week' not in columns:
                        conn.execute(db.text("ALTER TABLE drench_applications ADD COLUMN week VARCHAR(20)"))
                        conn.execute(db.text("CREATE INDEX IF NOT EXISTS ix_drench_applications_week ON drench_applications (week)"))
                        print("  ✓ Columna 'week' agregada con índice")
                    else:
                        print("  - Columna 'week' ya existe")
                else:
                    print("\n⚠ Tabla 'drench_applications' no existe aún")
                
                # TABLA tricho_applications
                if table_exists('tricho_applications'):
                    print("\nVerificando tabla 'tricho_applications'...")
                    result = conn.execute(db.text("PRAGMA table_info(tricho_applications)"))
                    columns = [row[1] for row in result.fetchall()]
                    
                    if 'week' not in columns:
                        conn.execute(db.text("ALTER TABLE tricho_applications ADD COLUMN week VARCHAR(20)"))
                        conn.execute(db.text("CREATE INDEX IF NOT EXISTS ix_tricho_applications_week ON tricho_applications (week)"))
                        print("  ✓ Columna 'week' agregada con índice")
                    else:
                        print("  - Columna 'week' ya existe")
                else:
                    print("\n⚠ Tabla 'tricho_applications' no existe aún")
                
                # TABLA disinfection_applications
                if table_exists('disinfection_applications'):
                    print("\nVerificando tabla 'disinfection_applications'...")
                    result = conn.execute(db.text("PRAGMA table_info(disinfection_applications)"))
                    columns = [row[1] for row in result.fetchall()]
                    
                    if 'week' not in columns:
                        conn.execute(db.text("ALTER TABLE disinfection_applications ADD COLUMN week VARCHAR(20)"))
                        conn.execute(db.text("CREATE INDEX IF NOT EXISTS ix_disinfection_applications_week ON disinfection_applications (week)"))
                        print("  ✓ Columna 'week' agregada con índice")
                    else:
                        print("  - Columna 'week' ya existe")
                else:
                    print("\n⚠ Tabla 'disinfection_applications' no existe aún")
                
                # TABLA import_batches
                if table_exists('import_batches'):
                    print("\nVerificando tabla 'import_batches'...")
                    result = conn.execute(db.text("PRAGMA table_info(import_batches)"))
                    columns = [row[1] for row in result.fetchall()]
                    
                    if 'week' not in columns:
                        conn.execute(db.text("ALTER TABLE import_batches ADD COLUMN week VARCHAR(20) DEFAULT '2026-33'"))
                        print("  ✓ Columna 'week' agregada")
                    else:
                        print("  - Columna 'week' ya existe")
                else:
                    print("\n⚠ Tabla 'import_batches' no existe aún")
                
                # TABLA requisitions - Campos de presupuesto y aprobación
                if table_exists('requisitions'):
                    print("\nVerificando tabla 'requisitions' (campos de presupuesto y aprobación)...")
                    result = conn.execute(db.text("PRAGMA table_info(requisitions)"))
                    columns = [row[1] for row in result.fetchall()]
                    
                    if 'budget_adjustments_json' not in columns:
                        conn.execute(db.text("ALTER TABLE requisitions ADD COLUMN budget_adjustments_json TEXT"))
                        print("  ✓ Columna 'budget_adjustments_json' agregada")
                    else:
                        print("  - Columna 'budget_adjustments_json' ya existe")
                    
                    if 'approved_by' not in columns:
                        conn.execute(db.text("ALTER TABLE requisitions ADD COLUMN approved_by VARCHAR(100)"))
                        print("  ✓ Columna 'approved_by' agregada")
                    else:
                        print("  - Columna 'approved_by' ya existe")
                    
                    if 'approved_at' not in columns:
                        conn.execute(db.text("ALTER TABLE requisitions ADD COLUMN approved_at DATETIME"))
                        print("  ✓ Columna 'approved_at' agregada")
                    else:
                        print("  - Columna 'approved_at' ya existe")
                    
                    # Actualizar valores de status antiguos a nuevos
                    conn.execute(db.text("UPDATE requisitions SET status = 'PENDIENTE' WHERE status = 'PEDIDO_INICIAL'"))
                    print("  ✓ Status actualizados de PEDIDO_INICIAL a PENDIENTE")
                
                # TABLA rotations - Campo para revisión por vuelta
                if table_exists('rotations'):
                    print("\nVerificando tabla 'rotations' (revisión acumulativa por vuelta)...")
                    result = conn.execute(db.text("PRAGMA table_info(rotations)"))
                    columns = [row[1] for row in result.fetchall()]
                    
                    if 'review_data_by_round_json' not in columns:
                        conn.execute(db.text("ALTER TABLE rotations ADD COLUMN review_data_by_round_json TEXT"))
                        print("  ✓ Columna 'review_data_by_round_json' agregada")
                    else:
                        print("  - Columna 'review_data_by_round_json' ya existe")
                
                conn.commit()
                print("\n✅ Migración completada exitosamente")
                
            except Exception as e:
                print(f"\n✗ Error en migración: {str(e)}")
                conn.rollback()

if __name__ == '__main__':
    migrate_database()
