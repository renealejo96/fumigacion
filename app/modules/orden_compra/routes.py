import datetime
import io
import json
import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from app.extensions import db
from app.shared.models import Crop, Product, Litraje, CropStateRecord, Rotation, Requisition, RequisitionItem
from app.modules.fumigacion.services.calculation_engine import CalculationEngine
from app.modules.fumigacion.services.requisition_service import RequisitionService
from app.shared.utils import get_local_now, format_product_amount, format_age
from app.shared.audit import record_audit
from app.modules.auth.routes import login_required, permission_required

orden_compra_bp = Blueprint('orden_compra', __name__)

@orden_compra_bp.route('/', methods=['GET', 'POST'])
@login_required
@permission_required('orden_compra')
def index():
    now = datetime.datetime.now()
    cur_year = now.year
    cur_week = now.isocalendar()[1]
    adv_week = cur_week + 2
    default_week = f"{cur_year}-{adv_week:02d}"

    # Get selected week from form POST or query string
    if request.method == 'POST':
        selected_week = request.form.get('week', default_week).strip()
    else:
        selected_week = request.args.get('week', default_week).strip()

    # Find active rotation for this week or latest rotation
    rotation = Rotation.query.filter_by(week=selected_week).order_by(Rotation.version.desc()).first()

    # Get bed configuration from rotation review data or calculate
    bed_configuration = []
    if rotation and rotation.review_data_by_round_json:
        try:
            r_data = json.loads(rotation.review_data_by_round_json)
            if r_data:
                # Use the first round's reviewed data or latest
                first_key = list(r_data.keys())[0]
                bed_configuration = r_data[first_key]
        except Exception:
            bed_configuration = []
    elif rotation and rotation.review_data_json:
        try:
            bed_configuration = json.loads(rotation.review_data_json)
        except Exception:
            bed_configuration = []

    if not bed_configuration and rotation and rotation.rounds:
        try:
            first_round = rotation.rounds[0]
            calc = CalculationEngine.calculate_round(first_round)
            bed_configuration = calc.get('segments', [])
        except Exception:
            bed_configuration = []

    # Calculate summary per variety / crop
    variety_summary = {}
    total_standard_beds_sum = 0.0
    if bed_configuration:
        for seg in bed_configuration:
            if isinstance(seg, dict):
                crop = (seg.get('crop_name') or 'SIN CULTIVO').strip()
                std_beds = float(seg.get('standard_beds', 0) or 0)
                liters_bed = float(seg.get('liters_per_bed', 0) or 0)
                stage = (seg.get('phenological_stage') or 'VEGETATIVO').strip().upper()
                total_standard_beds_sum += std_beds

                if crop not in variety_summary:
                    variety_summary[crop] = {
                        'crop_name': crop,
                        'total_std_beds': 0.0,
                        'veg_std_beds': 0.0,
                        'prod_std_beds': 0.0,
                        'total_liters': 0.0,
                        'segments_count': 0
                    }
                variety_summary[crop]['total_std_beds'] += std_beds
                if stage == 'VEGETATIVO':
                    variety_summary[crop]['veg_std_beds'] += std_beds
                else:
                    variety_summary[crop]['prod_std_beds'] += std_beds
                variety_summary[crop]['total_liters'] += (std_beds * liters_bed)
                variety_summary[crop]['segments_count'] += 1

    variety_summary_list = sorted(variety_summary.values(), key=lambda x: x['crop_name'])

    # If no rotation exists for this week yet, find latest or create draft
    requisition = None
    if rotation:
        requisition = Requisition.query.filter_by(rotation_id=rotation.id).first()
        if not requisition:
            requisition = RequisitionService.generate_or_update_forecast(rotation.id)

    # Convert to dicts for JSON serialization
    active_crops = [{'id': c.id, 'name': c.name} for c in Crop.query.filter_by(is_active=True).order_by(Crop.name.asc()).all()]
    active_products = [{'id': p.id, 'code': p.code, 'name': p.commercial_name} for p in Product.query.filter_by(is_active=True).order_by(Product.code.asc()).all()]

    # Block map - FILTERED BY SELECTED WEEK
    block_records = db.session.query(
        CropStateRecord.block_full, 
        CropStateRecord.zone, 
        CropStateRecord.crop_master
    ).filter(
        CropStateRecord.week == selected_week
    ).distinct().all()
    block_zone_map = {b[0].strip(): {'zone': (b[1] or '').strip(), 'crop': (b[2] or '').strip()} for b in block_records if b[0]}

    # Count beds configured
    total_beds_count = len(bed_configuration) if bed_configuration else 0

    # Available weeks list for dropdown
    week_options = []
    for i in range(-1, 9):
        w_num = cur_week + i
        y_num = cur_year
        if w_num > 52:
            w_num -= 52
            y_num += 1
        label = f"Semana {w_num:02d} ({y_num})"
        val = f"{y_num}-{w_num:02d}"
        is_target = (i == 2)
        week_options.append({'value': val, 'label': label, 'is_target': is_target})

    # Consolidated Dynamic Pivot Data (15-Day Purchase vs Foliar + Drench + Trichos)
    pivot_data = RequisitionService.get_consolidated_pivot_data(selected_week)

    return render_template(
        'orden_compra/index_new.html',
        selected_week=selected_week,
        rotation=rotation,
        requisition=requisition,
        pivot_data=pivot_data,
        active_crops=active_crops,
        active_products=active_products,
        block_zone_map=block_zone_map,
        week_options=week_options,
        total_beds_count=total_beds_count,
        total_standard_beds_sum=total_standard_beds_sum,
        variety_summary_list=variety_summary_list,
        bed_configuration=bed_configuration
    )


@orden_compra_bp.route('/exportar-excel')
@login_required
@permission_required('orden_compra')
def exportar_excel():
    week = request.args.get('week')
    if not week:
        flash("Debe especificar una semana.", "danger")
        return redirect(url_for('orden_compra.index'))

    rot = Rotation.query.filter_by(week=week).order_by(Rotation.version.desc()).first()
    if not rot:
        flash(f"No se encontró rotación para la semana {week}.", "warning")
        return redirect(url_for('orden_compra.index'))

    req = Requisition.query.filter_by(rotation_id=rot.id).first()
    if not req:
        req = RequisitionService.generate_or_update_forecast(rot.id)

    excel_stream = RequisitionService.export_requisition_to_excel(req)
    filename = f"Orden_Compra_Agroquimicos_15Dias_{req.week}.xlsx"
    return send_file(
        excel_stream,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


@orden_compra_bp.route('/recalculate-with-budget', methods=['POST'])
@login_required
@permission_required('orden_compra')
def recalculate_with_budget():
    """Recalcula la requisición sumando camas de presupuesto"""
    try:
        data = request.get_json()
        week = data.get('week')
        rotation_id = data.get('rotation_id')
        adjustments = data.get('adjustments', [])
        
        if not rotation_id:
            return jsonify({'success': False, 'error': 'No se especificó la rotación'}), 400
        
        rotation = Rotation.query.get(rotation_id)
        if not rotation:
            return jsonify({'success': False, 'error': 'Rotación no encontrada'}), 404
        
        # Get or create requisition
        requisition = Requisition.query.filter_by(rotation_id=rotation.id).first()
        if not requisition:
            requisition = RequisitionService.generate_or_update_forecast(rotation.id)
        
        # Save budget adjustments
        requisition.budget_adjustments_json = json.dumps(adjustments)
        db.session.commit()
        
        # Regenerate requisition with budget adjustments
        RequisitionService.recalculate_with_budget(requisition.id, adjustments)
        
        return jsonify({'success': True, 'message': 'Requisición recalculada con presupuesto'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@orden_compra_bp.route('/approve-order', methods=['POST'])
@login_required
@permission_required('orden_compra')
def approve_order():
    """Aprueba y congela la orden de compra"""
    try:
        data = request.get_json() if request.is_json else request.form
        week = data.get('week')
        rotation_id = data.get('rotation_id')
        
        if not rotation_id:
            return jsonify({'success': False, 'error': 'No se especificó la rotación'}), 400
        
        rotation = Rotation.query.get(rotation_id)
        if not rotation:
            return jsonify({'success': False, 'error': 'Rotación no encontrada'}), 404
        
        requisition = Requisition.query.filter_by(rotation_id=rotation.id).first()
        if not requisition:
            return jsonify({'success': False, 'error': 'No existe requisición para aprobar'}), 404
        
        # Approve requisition (frozen state)
        user_name = session.get('username') or session.get('name') or 'Ing. Agrónomo'
        requisition.status = 'APROBADO'
        requisition.approved_by = user_name
        requisition.approved_at = get_local_now()
        
        db.session.commit()
        record_audit('ORDEN_COMPRA', 'APPROVE', 'Requisition', requisition.id, details={'week': rotation.week, 'user': user_name, 'total_liters': requisition.total_liters})
        
        return jsonify({'success': True, 'message': f'Orden de compra aprobada exitosamente para la Semana {rotation.week}.'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@orden_compra_bp.route('/eliminar-orden', methods=['POST'])
@login_required
@permission_required('orden_compra')
def eliminar_orden():
    """Solo el Administrador puede eliminar/reiniciar una Orden de Compra aprobada"""
    try:
        if session.get('role') != 'ADMIN':
            return jsonify({
                'success': False, 
                'error': 'Permiso denegado: Solo los usuarios con rol Administrador pueden eliminar o reiniciar una Orden de Compra.'
            }), 403

        data = request.get_json() if request.is_json else request.form
        rotation_id = data.get('rotation_id')
        week = data.get('week')

        if not rotation_id:
            return jsonify({'success': False, 'error': 'No se especificó la rotación'}), 400

        rotation = Rotation.query.get(rotation_id)
        if not rotation:
            return jsonify({'success': False, 'error': 'Rotación no encontrada'}), 404

        requisition = Requisition.query.filter_by(rotation_id=rotation.id).first()
        if not requisition:
            return jsonify({'success': False, 'error': 'No existe orden de compra para eliminar'}), 404

        req_id = requisition.id
        req_week = requisition.week
        RequisitionItem.query.filter_by(requisition_id=req_id).delete()
        db.session.delete(requisition)
        db.session.commit()

        record_audit('ORDEN_COMPRA', 'DELETE_REQUISITION', 'Requisition', req_id, details={'week': req_week, 'admin': session.get('username')})

        return jsonify({'success': True, 'message': f'Orden de compra de la Semana {req_week} eliminada correctamente. Ya puedes recalcular nuevamente.'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
