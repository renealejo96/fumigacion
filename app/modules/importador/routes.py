import os
from pathlib import Path
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
from app.extensions import db
from app.shared.models import ImportBatch, Product, Litraje, CropStateRecord, AuditLog
from app.shared.excel_parser import ExcelParserService
from app.shared.audit import record_audit
from app.modules.auth.routes import login_required, permission_required

importador_bp = Blueprint('importador', __name__)

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'xlsm'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@importador_bp.route('/')
@login_required
@permission_required('importador')
def index():
    batches = ImportBatch.query.order_by(ImportBatch.created_at.desc()).all()
    audit_logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(20).all()
    return render_template('importador/index.html', batches=batches, audit_logs=audit_logs)


@importador_bp.route('/upload', methods=['POST'])
@login_required
@permission_required('importador')
def upload():
    file_type = request.form.get('file_type')
    action_type = request.form.get('action_type', 'commit')  # 'preview' or 'commit'
    mode = request.form.get('mode', 'replace')  # 'replace' or 'append'

    if 'file' not in request.files:
        flash("No se seleccionó ningún archivo.", "danger")
        return redirect(url_for('importador.index'))

    file = request.files['file']
    if file.filename == '':
        flash("Nombre de archivo vacío.", "danger")
        return redirect(url_for('importador.index'))

    if not allowed_file(file.filename):
        flash("Formato no soportado. Por favor sube un archivo Excel (.xlsx, .xls, .xlsm).", "danger")
        return redirect(url_for('importador.index'))

    filename = secure_filename(file.filename)
    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
    file.save(upload_path)

    # Process according to file type
    if file_type == 'PRODUCTOS_DOSIS':
        res = ExcelParserService.parse_products_excel(upload_path)
        if not res['success']:
            flash(f"Error al analizar archivo de productos: {res.get('error')}", "danger")
            return redirect(url_for('importador.index'))

        if action_type == 'commit':
            if mode == 'replace':
                # Deactivate or clear existing
                Product.query.update({'is_active': False})
            
            imported_count = 0
            for item in res['data']:
                p = Product.query.filter_by(code=item['code']).first()
                if p:
                    p.commercial_name = item['commercial_name']
                    p.unit = item['unit']
                    p.dose_fumigation = item['dose_fumigation']
                    p.dose_drench = item['dose_drench']
                    p.pest = item['pest']
                    p.active_ingredient = item['active_ingredient']
                    p.toxicological_category = item['toxicological_category']
                    p.is_active = True
                else:
                    p = Product(
                        code=item['code'],
                        commercial_name=item['commercial_name'],
                        unit=item['unit'],
                        dose_fumigation=item['dose_fumigation'],
                        dose_drench=item['dose_drench'],
                        pest=item['pest'],
                        active_ingredient=item['active_ingredient'],
                        toxicological_category=item['toxicological_category'],
                        is_active=True
                    )
                    db.session.add(p)
                imported_count += 1

            batch = ImportBatch(
                file_type=file_type,
                filename=filename,
                imported_rows=imported_count,
                status='SUCCESS',
                notes=f"Modo: {mode}. Total filas procesadas: {imported_count}"
            )
            db.session.add(batch)
            db.session.commit()
            record_audit('IMPORTADOR', 'IMPORT_EXCEL', 'Product', batch.id, details={'file': filename, 'rows': imported_count})
            flash(f"Se importaron exitosamente {imported_count} productos.", "success")
            return redirect(url_for('importador.index'))

        # Preview mode
        return render_template('importador/preview.html', file_type=file_type, filename=filename, res=res, mode=mode)

    elif file_type == 'LITRAJES':
        res = ExcelParserService.parse_litrajes_excel(upload_path)
        if not res['success']:
            flash(f"Error al analizar archivo de litrajes: {res.get('error')}", "danger")
            return redirect(url_for('importador.index'))

        if action_type == 'commit':
            if mode == 'replace':
                Litraje.query.delete()

            imported_count = 0
            for item in res['data']:
                lit = Litraje.query.filter_by(crop_name=item['crop_name'], age=item['age']).first()
                if lit:
                    lit.liters_per_bed = item['liters_per_bed']
                else:
                    lit = Litraje(
                        crop_name=item['crop_name'],
                        age=item['age'],
                        liters_per_bed=item['liters_per_bed']
                    )
                    db.session.add(lit)
                imported_count += 1

            batch = ImportBatch(
                file_type=file_type,
                filename=filename,
                imported_rows=imported_count,
                status='SUCCESS',
                notes=f"Modo: {mode}. Total reglas de litraje: {imported_count}"
            )
            db.session.add(batch)
            db.session.commit()
            record_audit('IMPORTADOR', 'IMPORT_EXCEL', 'Litraje', batch.id, details={'file': filename, 'rows': imported_count})
            flash(f"Se importaron exitosamente {imported_count} reglas de litrajes.", "success")
            return redirect(url_for('importador.index'))

        return render_template('importador/preview.html', file_type=file_type, filename=filename, res=res, mode=mode)

    elif file_type == 'ESTADO_CULTIVO':
        header_row = int(request.form.get('header_row', 4))
        sheet_name = request.form.get('sheet_name', 'DATOS')
        target_week = request.form.get('target_week', '').strip()
        
        if not target_week:
            flash("Debes especificar la semana para este plano de estado de cultivo.", "danger")
            return redirect(url_for('importador.index'))

        res = ExcelParserService.parse_crop_state_excel(upload_path, header_row=header_row, sheet_name=sheet_name)
        if not res['success']:
            flash(f"Error al analizar Estado de Cultivo: {res.get('error')}", "danger")
            return redirect(url_for('importador.index'))

        if action_type == 'commit':
            # Delete existing records for this specific week to prevent duplicates
            if request.form.get('mode', 'replace') == 'replace':
                CropStateRecord.query.filter_by(week=target_week).delete()
            # In append mode, duplicates are prevented by the fact that we're adding to a different week

            batch = ImportBatch(
                file_type=file_type,
                filename=filename,
                week=target_week,
                imported_rows=len(res['data']),
                status='SUCCESS',
                notes=f"Semana: {target_week}. Hoja: {sheet_name}. Fila encabezado: {header_row+1}. Camas estándar: {res['summary']['total_standard_beds']}"
            )
            db.session.add(batch)
            db.session.flush()

            records = []
            for r in res['data']:
                rec = CropStateRecord(
                    batch_id=batch.id,
                    week=target_week,
                    block_full=r['block_full'],
                    block_num=r['block_num'],
                    bed_num=r['bed_num'],
                    suffix=r['suffix'],
                    crop_master=r['crop_master'],
                    product_name=r['product_name'],
                    variety=r['variety'],
                    standard_bed=r['standard_bed'],
                    zone=r['zone'],
                    real_age=r['real_age'],
                    status_raw=r['status_raw']
                )
                records.append(rec)

            db.session.bulk_save_objects(records)
            db.session.commit()
            record_audit('IMPORTADOR', 'IMPORT_EXCEL', 'CropStateRecord', batch.id, details={'file': filename, 'week': target_week, 'rows': len(records)})
            flash(f"Se importaron exitosamente {len(records)} registros de Estado de Cultivo para la Semana {target_week} (sin duplicados).", "success")
            return redirect(url_for('importador.index'))

        return render_template('importador/preview.html', file_type=file_type, filename=filename, res=res, mode=mode, target_week=target_week)

    flash("Tipo de archivo no reconocido.", "warning")
    return redirect(url_for('importador.index'))
