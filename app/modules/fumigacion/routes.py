import io
import datetime
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from app.extensions import db
from app.shared.models import (
    Rotation, RotationRound, RotationRoundItem, 
    FumigationOrder, FumigationOrderDetail, FumigationOrderProductSummary,
    AdditionalApplication, Requisition, RequisitionItem,
    Crop, Product, CropStateRecord
)
from app.modules.fumigacion.services.calculation_engine import CalculationEngine
from app.modules.fumigacion.services.order_service import OrderService
from app.modules.fumigacion.services.requisition_service import RequisitionService
from app.shared.utils import (
    get_operator_for_zone, get_toxicological_color_info, 
    get_local_now, format_local_datetime, 
    is_integer_unit, round_product_amount, is_liquid_unit, is_solid_unit
)
from app.shared.audit import record_audit
from app.modules.auth.routes import login_required, permission_required, admin_required

fumigacion_bp = Blueprint('fumigacion', __name__)

# ==================== ROTACIONES ====================

@fumigacion_bp.route('/')
@fumigacion_bp.route('/rotaciones')
@login_required
@permission_required('fumigacion')
def rotaciones_index():
    week_filter = request.args.get('week', '').strip()
    status_filter = request.args.get('status', 'all')

    query = Rotation.query
    if week_filter:
        query = query.filter(Rotation.week.ilike(f"%{week_filter}%"))
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    rotations = query.order_by(Rotation.week.desc(), Rotation.version.desc(), Rotation.created_at.desc()).all()
    unique_weeks = [r[0] for r in db.session.query(Rotation.week).distinct().order_by(Rotation.week.desc()).all()]

    return render_template(
        'fumigacion/rotaciones_index.html',
        rotations=rotations,
        selected_week=week_filter,
        selected_status=status_filter,
        unique_weeks=unique_weeks
    )


@fumigacion_bp.route('/rotaciones/crear', methods=['GET', 'POST'])
@fumigacion_bp.route('/rotaciones/nueva', methods=['GET', 'POST'])
@fumigacion_bp.route('/rotacion/crear', methods=['GET', 'POST'])
@login_required
@permission_required('fumigacion')
def rotacion_crear():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        week = str(data.get('week', '')).strip()
        title = data.get('title', '').strip() or f"Rotación Semana {week}"
        notes = data.get('notes', '').strip()
        agronomist = data.get('created_by', 'Agrónomo Responsable').strip()
        rotation_id = data.get('rotation_id')

        if not week:
            if request.is_json:
                return jsonify({'success': False, 'error': 'La semana de planificación es obligatoria.'}), 400
            flash('La semana de planificación es obligatoria.', 'danger')
            return redirect(url_for('fumigacion.rotacion_crear'))

        if rotation_id:
            # Update existing rotation
            rotation = Rotation.query.get_or_404(int(rotation_id))
            rotation.week = week
            rotation.title = title
            rotation.notes = notes
            rotation.created_by = agronomist
            rotation.updated_at = get_local_now()
            # Reset review caches if matrix changed
            rotation.review_data_json = None
            rotation.review_data_by_round_json = None
            
            # Cleanly delete old rounds and items via ORM & direct query
            for old_r in list(rotation.rounds):
                for old_it in list(old_r.items):
                    db.session.delete(old_it)
                db.session.delete(old_r)
            db.session.flush()
            db.session.expire(rotation, ['rounds'])
        else:
            # Create new rotation version
            existing_versions = Rotation.query.filter_by(week=week).count()
            new_version = existing_versions + 1

            rotation = Rotation(
                week=week,
                version=new_version,
                title=f"{title} (v{new_version})" if new_version > 1 else title,
                notes=notes,
                status='BORRADOR',
                created_by=agronomist
            )
            db.session.add(rotation)
            db.session.flush()

        # Parse rounds and product grid
        rounds_data = data.get('rounds', [])
        if isinstance(rounds_data, list) and rounds_data:
            for r_idx, r_info in enumerate(rounds_data, 1):
                r_name = r_info.get('name', f"Vuelta {r_idx}")
                r_day = r_info.get('scheduled_day', 'Lunes' if r_idx == 1 else 'Jueves')
                r_notes = r_info.get('notes', '')
                
                round_obj = RotationRound(
                    rotation_id=rotation.id,
                    round_number=r_idx,
                    name=r_name,
                    scheduled_day=r_day,
                    notes=r_notes
                )
                db.session.add(round_obj)
                db.session.flush()

                items_data = r_info.get('items', [])
                for order_idx, it_info in enumerate(items_data):
                    crop_name = it_info.get('crop_name')
                    stage = it_info.get('phenological_stage', 'VEGETATIVO').upper()
                    prod_id = it_info.get('product_id')
                    dose = it_info.get('dose_applied')
                    dose_unit = it_info.get('dose_unit', 'CC')

                    if crop_name and prod_id:
                        prod = Product.query.get(prod_id)
                        if prod:
                            item_obj = RotationRoundItem(
                                round_id=round_obj.id,
                                crop_name=crop_name,
                                phenological_stage=stage,
                                product_id=prod.id,
                                dose_applied=float(dose) if dose is not None else (prod.dose_fumigation or 0.0),
                                dose_unit=dose_unit or prod.unit or 'CC',
                                order_index=order_idx,
                                notes=it_info.get('notes', '')
                            )
                            db.session.add(item_obj)

        db.session.commit()

        # Auto-generate 15-day advance requisition forecast
        RequisitionService.generate_or_update_forecast(rotation.id)

        action_type = 'UPDATE' if rotation_id else 'CREATE'
        record_audit('FUMIGACION', action_type, 'Rotation', rotation.id, user=agronomist, details={'week': week, 'version': rotation.version})

        if request.is_json:
            return jsonify({'success': True, 'rotation_id': rotation.id, 'redirect_url': url_for('fumigacion.rotacion_detalle', rotation_id=rotation.id)})

        flash(f"Rotación para la semana {week} (v{rotation.version}) guardada exitosamente.", "success")
        return redirect(url_for('fumigacion.rotacion_detalle', rotation_id=rotation.id))

    # GET
    active_crops = Crop.query.filter_by(is_active=True).order_by(Crop.name.asc()).all()
    active_products = Product.query.filter_by(is_active=True).order_by(Product.code.asc()).all()
    
    now = datetime.datetime.now()
    cur_year = now.year
    cur_week = now.isocalendar()[1]
    adv_week = cur_week + 2
    default_week = f"{cur_year}-{adv_week:02d}"

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

    return render_template(
        'fumigacion/rotacion_form.html',
        rotation=None,
        active_crops=active_crops,
        active_products=active_products,
        default_week=default_week,
        week_options=week_options
    )


@fumigacion_bp.route('/api/calcular-preview', methods=['POST'])
@login_required
@permission_required('fumigacion')
def api_calcular_preview():
    data = request.get_json() or {}
    items_data = data.get('items', [])
    
    dummy_round = RotationRound(
        round_number=1,
        name="Simulación",
        scheduled_day="Lunes"
    )
    
    for it in items_data:
        crop_name = it.get('crop_name')
        stage = it.get('phenological_stage', 'VEGETATIVO').upper()
        prod_id = it.get('product_id')
        dose = it.get('dose_applied')
        
        if crop_name and prod_id:
            prod = Product.query.get(prod_id)
            if prod:
                item_obj = RotationRoundItem(
                    crop_name=crop_name,
                    phenological_stage=stage,
                    product_id=prod.id,
                    dose_applied=float(dose) if dose is not None else (prod.dose_fumigation or 0.0),
                    dose_unit=it.get('dose_unit') or prod.unit or 'CC'
                )
                item_obj.product = prod
                dummy_round.items.append(item_obj)

    result = CalculationEngine.calculate_round(dummy_round)
    return jsonify(result)


@fumigacion_bp.route('/rotaciones/<int:rotation_id>/editar')
@login_required
@permission_required('fumigacion')
def rotacion_editar(rotation_id):
    rotation = Rotation.query.get_or_404(rotation_id)
    active_crops = Crop.query.filter_by(is_active=True).order_by(Crop.name.asc()).all()
    active_products = Product.query.filter_by(is_active=True).order_by(Product.code.asc()).all()
    
    now = datetime.datetime.now()
    cur_year = now.year
    cur_week = now.isocalendar()[1]
    adv_week = cur_week + 2
    default_week = f"{cur_year}-{adv_week:02d}"

    week_options = []
    for i in range(-1, 9):
        w_num = cur_week + i
        y_num = cur_year
        if w_num > 52:
            w_num -= 52
            y_num += 1
        label = f"Semana {w_num:02d} ({y_num})"
        val = f"{y_num}-{w_num:02d}"
        is_target = (val == rotation.week)
        week_options.append({'value': val, 'label': label, 'is_target': is_target})

    return render_template(
        'fumigacion/rotacion_form.html',
        rotation=rotation,
        active_crops=active_crops,
        active_products=active_products,
        default_week=rotation.week,
        week_options=week_options
    )


@fumigacion_bp.route('/rotaciones/<int:rotation_id>/eliminar', methods=['POST'])
@login_required
@permission_required('fumigacion')
def rotacion_eliminar(rotation_id):
    rotation = Rotation.query.get_or_404(rotation_id)
    week = rotation.week
    version = rotation.version
    rotation.status = 'ELIMINADA'
    timestamp_str = format_local_datetime(get_local_now())
    rotation.notes = (rotation.notes + " | " if rotation.notes else "") + f"Rotación ELIMINADA por el usuario el {timestamp_str}"
    db.session.commit()
    record_audit('FUMIGACION', 'DELETE_ROTATION', 'Rotation', rotation_id, details={'week': week, 'version': version})
    flash(f"Rotación de la semana {week} (v{version}) marcada como ELIMINADA y registrada en el historial.", "warning")
    return redirect(url_for('fumigacion.rotaciones_index'))


@fumigacion_bp.route('/rotaciones/<int:rotation_id>')
@login_required
def rotacion_detalle(rotation_id):
    rotation = Rotation.query.get_or_404(rotation_id)
    
    # NEW: Load review data by round
    review_by_round = {}
    if rotation.review_data_by_round_json:
        try:
            review_by_round = json.loads(rotation.review_data_by_round_json)
        except Exception:
            review_by_round = {}
    
    # Get all rounds sorted
    all_rounds = RotationRound.query.filter_by(rotation_id=rotation.id).order_by(RotationRound.round_number.asc()).all()
    
    # For initial display, load first round's data (or base if no custom data)
    first_round_id = all_rounds[0].id if all_rounds else None
    review_segments = []
    if first_round_id and str(first_round_id) in review_by_round:
        review_segments = review_by_round[str(first_round_id)]
    
    # Calculate base rounds (pure theoretical estimate from map + crops) for Paso 1
    rounds_base_calculated = []
    for r in all_rounds:
        calc_base = CalculationEngine.calculate_round(r)
        rounds_base_calculated.append({
            'round': r,
            'calc': calc_base
        })

    # Calculate rounds with cumulative logic for Paso 2 review
    rounds_calculated = []
    for i, r in enumerate(all_rounds):
        # Apply cumulative: find the latest custom segments up to this round
        custom_segs = None
        for j in range(i + 1):
            rid = all_rounds[j].id
            if str(rid) in review_by_round:
                custom_segs = review_by_round[str(rid)]
        
        calc = CalculationEngine.calculate_round(r, custom_review_segments=custom_segs)
        rounds_calculated.append({
            'round': r,
            'calc': calc
        })

    # Get associated requisition (forecast based on baseline rounds)
    requisition = Requisition.query.filter_by(rotation_id=rotation.id).first()
    if not requisition:
        requisition = RequisitionService.generate_or_update_forecast(rotation.id)

    # Generated orders for this rotation
    orders = FumigationOrder.query.filter_by(rotation_id=rotation.id).order_by(FumigationOrder.round_number.asc()).all()

    # Additional applications for this week
    additional_apps = AdditionalApplication.query.filter_by(week=rotation.week).all()

    active_products = Product.query.filter_by(is_active=True).order_by(Product.code.asc()).all()
    active_crops = Crop.query.filter_by(is_active=True).order_by(Crop.name.asc()).all()

    # Unique crops present in this rotation for filtering
    rotation_crops = list(set([it.crop_name for r in rotation.rounds for it in r.items]))

    # Comparison data (Forecast vs Real Validated + Extras)
    comp_data = RequisitionService.get_comparison_data(rotation.id)

    # Distinct block to zone map from crop state records - FILTERED BY ROTATION WEEK
    block_records = db.session.query(
        CropStateRecord.block_full, 
        CropStateRecord.zone, 
        CropStateRecord.crop_master
    ).filter(
        CropStateRecord.week == rotation.week
    ).distinct().all()
    block_zone_map = {}
    for b_full, z, c_mast in block_records:
        if b_full:
            block_zone_map[b_full.strip()] = {
                'zone': (z or '').strip(),
                'crop': (c_mast or '').strip()
            }

    # Map standard rotation formulas by crop_name and phenological_stage for comparison and restoration
    rotation_formulas_map = {}
    for r in rotation.rounds:
        for it in sorted(r.items, key=lambda x: x.order_index):
            crop_k = CalculationEngine.normalize_crop_name(it.crop_name)
            stage_k = it.phenological_stage.strip().upper()
            formula_key = f"{crop_k}__{stage_k}"
            if formula_key not in rotation_formulas_map:
                rotation_formulas_map[formula_key] = []
            
            prod = it.product
            prod_entry = {
                'product_id': prod.id if prod else it.product_id,
                'product_code': prod.code if prod else '',
                'commercial_name': prod.commercial_name if (prod and prod.commercial_name) else (prod.code if prod else ''),
                'dose': float(it.dose_applied or (prod.dose_fumigation if prod else 0.0) or 0.0),
                'dose_unit': it.dose_unit or (prod.unit if prod else 'CC'),
                'pest': prod.pest if prod else '',
                'active_ingredient': prod.active_ingredient if prod else '',
                'toxicological_category': prod.toxicological_category if prod else ''
            }
            if not any(p['product_code'] == prod_entry['product_code'] for p in rotation_formulas_map[formula_key]):
                rotation_formulas_map[formula_key].append(prod_entry)

    return render_template(
        'fumigacion/rotacion_detalle.html',
        rotation=rotation,
        rounds_base_calculated=rounds_base_calculated,
        rounds_calculated=rounds_calculated,
        requisition=requisition,
        comp_data=comp_data,
        orders=orders,
        additional_apps=additional_apps,
        active_products=active_products,
        active_crops=active_crops,
        rotation_crops=rotation_crops,
        block_zone_map=block_zone_map,
        review_segments=review_segments,
        rotation_formulas_map=rotation_formulas_map,
        applied_rounds=[]
    )


@fumigacion_bp.route('/rotaciones/<int:rotation_id>/guardar-revision', methods=['POST'])
def rotacion_guardar_revision(rotation_id):
    """
    Saves calibration segments.
    - If target_round_id is provided, assigns segments to that specific round, automatically generates/updates the official FumigationOrder, and syncs Requisition.
    - If target_round_id is not provided, saves as active working draft in review_data_json.
    """
    rotation = Rotation.query.get_or_404(rotation_id)
    data = request.get_json() or {}
    segments = data.get('segments', [])
    target_round_id = data.get('target_round_id')

    if not segments:
        return jsonify({'success': False, 'error': 'No hay datos de segmentos para guardar.'}), 400

    # Always persist working draft
    rotation.review_data_json = json.dumps(segments, ensure_ascii=False)

    msg = "Ajustes de camas guardados como borrador de trabajo."

    if target_round_id:
        target_round = RotationRound.query.get(target_round_id)
        r_name = target_round.name if target_round else f"Vuelta #{target_round_id}"
        
        # Load review data by round
        review_by_round = {}
        if rotation.review_data_by_round_json:
            try:
                review_by_round = json.loads(rotation.review_data_by_round_json)
            except:
                review_by_round = {}

        review_by_round[str(target_round_id)] = segments
        rotation.review_data_by_round_json = json.dumps(review_by_round, ensure_ascii=False)
        db.session.commit()
        
        # Automatically generate/freeze official FumigationOrder for this assigned round
        OrderService.create_order_from_round(target_round_id, agronomist=rotation.created_by, custom_segments=segments)

        # Sync with requisition to update Paso 3 consumption
        RequisitionService.sync_with_final_orders(rotation.id)
        
        msg = f"Camas y mezcla asignadas exitosamente a {r_name}. Orden de Fumigación Oficial y Requisición actualizadas."
        record_audit('FUMIGACION', 'ASSIGN_REVIEW_TO_ROUND', 'Rotation', rotation.id, 
                     details={'target_round_id': target_round_id, 'round_name': r_name, 'segments_count': len(segments)})
    else:
        db.session.commit()
        record_audit('FUMIGACION', 'SAVE_REVIEW_DRAFT', 'Rotation', rotation.id, 
                     details={'segments_count': len(segments)})

    return jsonify({'success': True, 'message': msg})


@fumigacion_bp.route('/rotaciones/<int:rotation_id>/get-cumulative', methods=['GET'])
def rotacion_get_cumulative(rotation_id):
    """
    Returns cumulative segments for a given round_id.
    Cumulative logic: Load base calculation, then apply adjustments from all previous rounds up to target round.
    """
    rotation = Rotation.query.get_or_404(rotation_id)
    target_round_id = request.args.get('round_id', type=int)
    
    if not target_round_id:
        return jsonify({'success': False, 'error': 'round_id requerido'}), 400
    
    target_round = RotationRound.query.get_or_404(target_round_id)
    
    # Load review data by round
    review_by_round = {}
    if rotation.review_data_by_round_json:
        try:
            review_by_round = json.loads(rotation.review_data_by_round_json)
        except:
            review_by_round = {}
    
    # Get all rounds sorted by round_number
    all_rounds = RotationRound.query.filter_by(rotation_id=rotation.id).order_by(RotationRound.round_number.asc()).all()
    round_ids_ordered = [r.id for r in all_rounds]
    
    # Find position of target round
    try:
        target_position = round_ids_ordered.index(target_round_id)
    except ValueError:
        return jsonify({'success': False, 'error': 'Vuelta no encontrada en rotación'}), 404
    
    # Start with base calculation for this round
    calc = CalculationEngine.calculate_round(target_round)
    base_segments = calc.get('segments', [])
    
    # Apply cumulative adjustments from round 0 up to target_position
    cumulative_segments = base_segments
    for i in range(target_position + 1):
        rid = round_ids_ordered[i]
        if str(rid) in review_by_round:
            # This round has custom adjustments, use them
            cumulative_segments = review_by_round[str(rid)]
    
    # Convert segments to dict format for frontend
    segments_dict = []
    for seg in cumulative_segments:
        if isinstance(seg, dict):
            # Ensure products list is populated
            if 'products' not in seg or seg['products'] is None:
                crop_name = seg.get('crop_name', '')
                stage = seg.get('phenological_stage', 'VEGETATIVO')
                prods = []
                for it in sorted(target_round.items, key=lambda x: x.order_index):
                    if (CalculationEngine.normalize_crop_name(it.crop_name) == CalculationEngine.normalize_crop_name(crop_name) and 
                        it.phenological_stage.strip().upper() == stage.strip().upper()):
                        prod = it.product
                        prods.append({
                            'product_id': prod.id if prod else it.product_id,
                            'product_code': prod.code if prod else '',
                            'commercial_name': prod.commercial_name if (prod and prod.commercial_name) else (prod.code if prod else ''),
                            'dose': it.dose_applied or (prod.dose_fumigation if prod else 0.0),
                            'dose_unit': it.dose_unit or (prod.unit if prod else 'CC'),
                            'pest': prod.pest if prod else '',
                            'active_ingredient': prod.active_ingredient if prod else '',
                            'toxicological_category': prod.toxicological_category if prod else ''
                        })
                seg['products'] = prods
            segments_dict.append(seg)
        else:
            segments_dict.append({
                'zone': getattr(seg, 'zone', ''),
                'block_name': getattr(seg, 'block_name', ''),
                'suffix': getattr(seg, 'suffix', 'A'),
                'crop_name': getattr(seg, 'crop_name', ''),
                'variety': getattr(seg, 'variety', ''),
                'phenological_stage': getattr(seg, 'phenological_stage', 'VEGETATIVO'),
                'real_age': getattr(seg, 'real_age', 0),
                'bed_start': getattr(seg, 'bed_start', 1),
                'bed_end': getattr(seg, 'bed_end', 1),
                'standard_beds': getattr(seg, 'standard_beds', 1.0),
                'liters_per_bed': getattr(seg, 'liters_per_bed', 0.0),
                'products': getattr(seg, 'products', []),
                'is_additional': getattr(seg, 'is_additional', False)
            })
    
    return jsonify({
        'success': True,
        'round_name': target_round.name,
        'round_id': target_round.id,
        'segments': segments_dict
    })


@fumigacion_bp.route('/rotaciones/<int:rotation_id>/aprobar', methods=['POST'])
@login_required
@permission_required('fumigacion')
def rotacion_aprobar(rotation_id):
    rotation = Rotation.query.get_or_404(rotation_id)
    agronomist = request.form.get('agronomist', rotation.created_by)

    prev_rotations = Rotation.query.filter(Rotation.week == rotation.week, Rotation.id != rotation.id).all()
    for pr in prev_rotations:
        pr.status = 'NO_EJECUTADA'
        if not pr.notes or 'Reemplazada' not in pr.notes:
            pr.notes = (pr.notes + " | " if pr.notes else "") + f"Rotación NO EJECUTADA - Reemplazada por Versión {rotation.version}"

    rotation.status = 'APROBADA'
    rotation.approved_by = agronomist
    rotation.approved_at = get_local_now()
    db.session.commit()

    RequisitionService.sync_with_final_orders(rotation.id)

    record_audit('FUMIGACION', 'APPROVE_ROTATION', 'Rotation', rotation.id, user=agronomist, details={'week': rotation.week, 'version': rotation.version})
    flash(f"Rotación de la semana {rotation.week} (v{rotation.version}) APROBADA exitosamente.", "success")
    return redirect(url_for('fumigacion.rotacion_detalle', rotation_id=rotation.id))


@fumigacion_bp.route('/rotaciones/<int:rotation_id>/desaprobar', methods=['POST'])
@login_required
@permission_required('fumigacion')
def rotacion_desaprobar(rotation_id):
    rotation = Rotation.query.get_or_404(rotation_id)
    rotation.status = 'BORRADOR'
    rotation.approved_by = None
    rotation.approved_at = None
    db.session.commit()
    record_audit('FUMIGACION', 'UNAPPROVE_ROTATION', 'Rotation', rotation.id, details={'week': rotation.week})
    flash(f"Rotación de la semana {rotation.week} devuelta a estado BORRADOR. Ya puedes editar la matriz con Drag and Drop.", "info")
    return redirect(url_for('fumigacion.rotacion_editar', rotation_id=rotation.id))


@fumigacion_bp.route('/rotaciones/generar-orden/<int:round_id>', methods=['POST'])
@login_required
@permission_required('fumigacion')
def generar_orden(round_id):
    round_obj = RotationRound.query.get_or_404(round_id)
    rotation = round_obj.rotation
    agronomist = request.form.get('agronomist', rotation.created_by)
    notes = request.form.get('notes', '')

    custom_segs = None
    # NEW: Use cumulative logic from review_data_by_round_json
    if rotation.review_data_by_round_json:
        try:
            review_by_round = json.loads(rotation.review_data_by_round_json)
            
            # Get all rounds sorted by round_number to apply cumulative logic
            all_rounds = RotationRound.query.filter_by(rotation_id=rotation.id).order_by(RotationRound.round_number.asc()).all()
            round_ids_ordered = [r.id for r in all_rounds]
            
            # Find position of target round
            try:
                target_position = round_ids_ordered.index(round_obj.id)
                
                # Apply cumulative: use the latest available round data up to this round
                for i in range(target_position + 1):
                    rid = round_ids_ordered[i]
                    if str(rid) in review_by_round:
                        custom_segs = review_by_round[str(rid)]
                        
            except ValueError:
                pass  # Round not found, use base calculation
                
        except Exception:
            custom_segs = None

    try:
        order = OrderService.create_order_from_round(round_id, agronomist=agronomist, notes=notes, custom_segments=custom_segs)
        RequisitionService.sync_with_final_orders(rotation.id)

        flash(f"Orden de Fumigación {order.order_number} generada e inmutablemente congelada para la {order.round_name}.", "success")
        return redirect(url_for('fumigacion.orden_detalle', order_id=order.id))
    except Exception as e:
        flash(f"Error al generar orden de fumigación: {str(e)}", "danger")
        return redirect(url_for('fumigacion.rotacion_detalle', rotation_id=rotation.id))


# ==================== ORDENES DE FUMIGACION & EXPORTACIONES ====================

@fumigacion_bp.route('/ordenes')
@login_required
@permission_required('ordenes_ver')
def ordenes_index():
    week_filter = request.args.get('week', '').strip()
    status_filter = request.args.get('status', 'all')

    query = FumigationOrder.query
    if week_filter:
        query = query.filter(FumigationOrder.week.ilike(f"%{week_filter}%"))
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)

    orders = query.order_by(FumigationOrder.created_at.desc()).all()
    return render_template('fumigacion/ordenes_index.html', orders=orders, selected_week=week_filter, selected_status=status_filter)


@fumigacion_bp.route('/ordenes/<int:order_id>')
@login_required
@permission_required('ordenes_ver')
def orden_detalle(order_id):
    order = FumigationOrder.query.get_or_404(order_id)
    
    # Build structured hierarchy: Zone -> Blocks -> Rows + Zone Totals + Zone Product Totals (Liquids & Solids)
    zones_map = {}
    for d in order.details:
        z = (d.zone or 'GENERAL').strip()
        if z not in zones_map:
            zones_map[z] = {
                'zone_name': z,
                'blocks': {},
                'total_beds': 0.0,
                'total_liters': 0.0,
                'products_by_code': {}
            }
        b = d.block_name
        if b not in zones_map[z]['blocks']:
            zones_map[z]['blocks'][b] = {
                'block_name': b,
                'standard_beds': d.standard_beds,
                'total_liters': d.total_liters,
                'rows': []
            }
            zones_map[z]['total_beds'] += d.standard_beds
            zones_map[z]['total_liters'] += d.total_liters
            
        zones_map[z]['blocks'][b]['rows'].append(d)

        # Accumulate product amounts for zone subtotal
        if d.product_code and d.product_code != 'SIN PRODUCTO':
            u = d.unit or 'CC'
            is_liq = is_liquid_unit(u)
            if d.product_code not in zones_map[z]['products_by_code']:
                zones_map[z]['products_by_code'][d.product_code] = {
                    'product_code': d.product_code,
                    'commercial_name': d.commercial_name or d.product_code,
                    'unit': u,
                    'dose': d.dose,
                    'is_liquid': is_liq,
                    'total_amount': 0.0
                }
            zones_map[z]['products_by_code'][d.product_code]['total_amount'] += (d.product_amount or 0.0)

    for z_info in zones_map.values():
        prods = list(z_info['products_by_code'].values())
        z_info['liquid_products'] = [p for p in prods if p['is_liquid']]
        z_info['solid_products'] = [p for p in prods if not p['is_liquid']]

    return render_template('fumigacion/orden_detalle.html', order=order, zones_map=zones_map)



@fumigacion_bp.route('/ordenes/<int:order_id>/exportar-excel')
@login_required
@permission_required('ordenes_imprimir')
def orden_exportar_excel(order_id):
    order = FumigationOrder.query.get_or_404(order_id)
    excel_stream = OrderService.export_order_to_excel(order)
    filename = f"Orden_Fumigacion_{order.order_number}.xlsx"
    return send_file(
        excel_stream,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


@fumigacion_bp.route('/requisiciones/<int:requisition_id>/exportar-excel')
@login_required
@permission_required('salidas_imprimir')
def requisicion_exportar_excel(requisition_id):
    req = Requisition.query.get_or_404(requisition_id)
    excel_stream = RequisitionService.export_requisition_to_excel(req)
    filename = f"Requisicion_Agroquimicos_{req.week}.xlsx"
    return send_file(
        excel_stream,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


@fumigacion_bp.route('/salidas')
@login_required
@permission_required('salidas_ver')
def salidas_index():
    target_week = request.args.get('week', '').strip()
    if target_week:
        target_rot = Rotation.query.filter(Rotation.week == target_week, Rotation.status != 'ELIMINADA').order_by(Rotation.version.desc()).first()
        if target_rot:
            return redirect(url_for('fumigacion.ver_salidas', rotation_id=target_rot.id))

    # Priority 1: Approved rotations with orders
    approved_with_orders = Rotation.query.filter(Rotation.status == 'APROBADA').order_by(Rotation.week.desc(), Rotation.version.desc()).all()
    for r in approved_with_orders:
        if r.orders and len(r.orders) > 0:
            return redirect(url_for('fumigacion.ver_salidas', rotation_id=r.id))

    # Priority 2: Any active non-deleted rotation with orders
    active_with_orders = Rotation.query.filter(Rotation.status != 'ELIMINADA').order_by(Rotation.week.desc(), Rotation.version.desc()).all()
    for r in active_with_orders:
        if r.orders and len(r.orders) > 0:
            return redirect(url_for('fumigacion.ver_salidas', rotation_id=r.id))

    # Priority 3: Latest active rotation
    if active_with_orders:
        return redirect(url_for('fumigacion.ver_salidas', rotation_id=active_with_orders[0].id))

    flash("Aún no hay rotaciones registradas en el sistema para calcular salidas de bodega.", "info")
    return redirect(url_for('dashboard'))


@fumigacion_bp.route('/rotacion/<int:rotation_id>/salidas')
@fumigacion_bp.route('/rotaciones/<int:rotation_id>/salidas')
@login_required
@permission_required('salidas_ver')
def ver_salidas(rotation_id):
    """Vista de salidas agrupadas por área y día de aplicación con control de almacén y despacho"""
    rotation = Rotation.query.get_or_404(rotation_id)
    all_rotations = Rotation.query.filter(Rotation.status != 'ELIMINADA').order_by(Rotation.week.desc(), Rotation.version.desc()).all()
    
    # Calculate previous and next rotation in chronological sequence
    prev_rotation = None
    next_rotation = None
    for idx, r in enumerate(all_rotations):
        if r.id == rotation.id:
            # Since all_rotations is desc (newest first), the next chronological week is at idx-1 and previous is at idx+1
            if idx > 0:
                next_rotation = all_rotations[idx - 1]
            if idx < len(all_rotations) - 1:
                prev_rotation = all_rotations[idx + 1]
            break

    # Get all orders for this rotation
    orders = FumigationOrder.query.filter_by(rotation_id=rotation.id).order_by(FumigationOrder.round_number.asc()).all()

    # Filter by specific program if requested
    target_order_id = request.args.get('order_id', type=int)
    selected_order = None
    if target_order_id:
        selected_order = next((o for o in orders if o.id == target_order_id), None)

    display_orders = [selected_order] if selected_order else orders
    
    # Get dispatch & print logs for this week
    from app.shared.models import WarehouseDispatchLog
    dispatch_logs = WarehouseDispatchLog.query.filter_by(week=rotation.week).order_by(WarehouseDispatchLog.created_at.desc()).limit(20).all()

    if not orders:
        return render_template(
            'fumigacion/salidas.html',
            rotation=rotation,
            orders=[],
            display_orders=[],
            selected_order=None,
            scheduled_days=[],
            data_by_area={},
            general_summary={},
            product_info={},
            all_rotations=all_rotations,
            prev_rotation=prev_rotation,
            next_rotation=next_rotation,
            dispatch_logs=dispatch_logs,
            total_products_count=0,
            total_volume_liters=0.0,
            total_beds=0.0
        )
    
    # Get unique scheduled days in execution order
    scheduled_days = []
    for ord in display_orders:
        if ord.scheduled_day and ord.scheduled_day not in scheduled_days:
            scheduled_days.append(ord.scheduled_day)
    
    # Build data structure: {area: {product_code: {day: quantity}}}
    data_by_area = {}
    product_info = {}  # Store product details
    
    for order in display_orders:
        for detail in order.details:
            area = (detail.crop_name or 'GENERAL').strip()  # Area / Cultivo
            product_code = (detail.product_code or '').strip()
            day = order.scheduled_day
            amount = float(detail.product_amount or 0.0)

            if not product_code:
                continue
            
            # Initialize structures
            if area not in data_by_area:
                data_by_area[area] = {}
            if product_code not in data_by_area[area]:
                data_by_area[area][product_code] = {d: 0.0 for d in scheduled_days}
            
            # Store product info
            if product_code not in product_info:
                product_info[product_code] = {
                    'commercial_name': detail.commercial_name or product_code,
                    'unit': detail.unit or 'CC'
                }
            
            # Accumulate quantity
            if day in data_by_area[area][product_code]:
                data_by_area[area][product_code][day] += amount
    
    # Build general summary (without area grouping)
    general_summary = {}
    for area_products in data_by_area.values():
        for product_code, day_quantities in area_products.items():
            if product_code not in general_summary:
                general_summary[product_code] = {d: 0.0 for d in scheduled_days}
            for day, qty in day_quantities.items():
                if day in general_summary[product_code]:
                    general_summary[product_code][day] += qty

    total_products_count = len(product_info)
    total_volume_liters = sum(ord.total_liters for ord in display_orders)
    total_beds = sum(ord.total_standard_beds for ord in display_orders)

    return render_template(
        'fumigacion/salidas.html',
        rotation=rotation,
        orders=orders,
        display_orders=display_orders,
        selected_order=selected_order,
        scheduled_days=scheduled_days,
        data_by_area=data_by_area,
        general_summary=general_summary,
        product_info=product_info,
        all_rotations=all_rotations,
        prev_rotation=prev_rotation,
        next_rotation=next_rotation,
        dispatch_logs=dispatch_logs,
        total_products_count=total_products_count,
        total_volume_liters=total_volume_liters,
        total_beds=total_beds
    )


@fumigacion_bp.route('/rotaciones/<int:rotation_id>/marcar-salidas-impresa', methods=['POST'])
@login_required
@permission_required('salidas_imprimir')
def marcar_salidas_impresa(rotation_id):
    """Marca la planilla de salidas como impresa y registra log de almacén"""
    from app.shared.models import WarehouseDispatchLog
    rotation = Rotation.query.get_or_404(rotation_id)
    user_name = session.get('full_name') or session.get('username') or 'Usuario Bodega'
    user_role = session.get('role') or 'ASISTENTE'

    rotation.is_salidas_printed = True
    rotation.salidas_printed_at = get_local_now()
    rotation.salidas_printed_by = user_name

    for ord in rotation.orders:
        ord.is_printed = True
        ord.printed_at = get_local_now()
        ord.printed_by = user_name

    log_entry = WarehouseDispatchLog(
        week=rotation.week,
        rotation_id=rotation.id,
        action='IMPRESION_SALIDAS',
        performed_by=user_name,
        role=user_role,
        notes=f"Planilla de salidas de la Semana {rotation.week} impresa y lista para pesaje de bodega."
    )
    db.session.add(log_entry)
    db.session.commit()

    record_audit('BODEGA', 'PRINT_SALIDAS', 'Rotation', rotation.id, details={'week': rotation.week, 'user': user_name})

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'is_printed': True,
            'printed_at': format_local_datetime(rotation.salidas_printed_at),
            'printed_by': rotation.salidas_printed_by
        })

    flash(f"Planilla de salidas de la Semana {rotation.week} marcada como IMPRESA.", "success")
    return redirect(url_for('fumigacion.ver_salidas', rotation_id=rotation.id))


@fumigacion_bp.route('/rotaciones/<int:rotation_id>/marcar-salidas-despachada', methods=['POST'])
@login_required
@permission_required('salidas_imprimir')
def marcar_salidas_despachada(rotation_id):
    """Alterna el estado de despacho y entrega de insumos en bodega"""
    from app.shared.models import WarehouseDispatchLog
    rotation = Rotation.query.get_or_404(rotation_id)
    user_name = session.get('full_name') or session.get('username') or 'Usuario Bodega'
    user_role = session.get('role') or 'ASISTENTE'

    rotation.is_salidas_dispatched = not rotation.is_salidas_dispatched
    if rotation.is_salidas_dispatched:
        rotation.salidas_dispatched_at = get_local_now()
        rotation.salidas_dispatched_by = user_name
        status_action = "DESPACHO_BODEGA"
        msg_text = f"Insumos de la Semana {rotation.week} marcados como DESPACHADOS / ENTREGADOS A OPERARIOS."
    else:
        rotation.salidas_dispatched_at = None
        rotation.salidas_dispatched_by = None
        status_action = "REVERTIR_DESPACHO"
        msg_text = f"Despacho de la Semana {rotation.week} devuelto a estado PENDIENTE."

    log_entry = WarehouseDispatchLog(
        week=rotation.week,
        rotation_id=rotation.id,
        action=status_action,
        performed_by=user_name,
        role=user_role,
        notes=msg_text
    )
    db.session.add(log_entry)
    db.session.commit()

    record_audit('BODEGA', status_action, 'Rotation', rotation.id, details={'week': rotation.week, 'dispatched': rotation.is_salidas_dispatched})

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'is_dispatched': rotation.is_salidas_dispatched,
            'dispatched_at': format_local_datetime(rotation.salidas_dispatched_at) if rotation.salidas_dispatched_at else None,
            'dispatched_by': rotation.salidas_dispatched_by or ''
        })

    flash(msg_text, "success" if rotation.is_salidas_dispatched else "info")
    return redirect(url_for('fumigacion.ver_salidas', rotation_id=rotation.id))


@fumigacion_bp.route('/rotacion/<int:rotation_id>/salidas/exportar-excel')
@fumigacion_bp.route('/rotaciones/<int:rotation_id>/salidas/exportar-excel')
@login_required
@permission_required('salidas_imprimir')
def exportar_salidas_excel(rotation_id):
    """Exporta las salidas a Excel"""
    rotation = Rotation.query.get_or_404(rotation_id)
    orders = FumigationOrder.query.filter_by(rotation_id=rotation.id).order_by(FumigationOrder.round_number.asc()).all()
    
    if not orders:
        flash("No hay órdenes generadas para esta rotación.", "warning")
        return redirect(url_for('fumigacion.rotacion_detalle', rotation_id=rotation_id))
    
    # Same logic as ver_salidas to build data
    scheduled_days = sorted(set(ord.scheduled_day for ord in orders))
    data_by_area = {}
    product_info = {}
    
    for order in orders:
        for detail in order.details:
            area = detail.crop_name
            product_code = detail.product_code
            day = order.scheduled_day
            amount = detail.product_amount
            
            if area not in data_by_area:
                data_by_area[area] = {}
            if product_code not in data_by_area[area]:
                data_by_area[area][product_code] = {d: 0.0 for d in scheduled_days}
            
            if product_code not in product_info:
                product_info[product_code] = {
                    'commercial_name': detail.commercial_name or product_code,
                    'unit': detail.unit
                }
            
            data_by_area[area][product_code][day] += amount
    
    # Build DataFrame
    rows = []
    for area in sorted(data_by_area.keys()):
        for product_code in sorted(data_by_area[area].keys()):
            u = (product_info[product_code]['unit'] or '').strip().upper()
            is_int = u in ['CC', 'G', 'GR', 'ML', 'PST', 'PST.', 'GRAMOS', 'CENTIMETROS']

            row = {
                'ÁREA': area,
                'PRODUCTO': product_info[product_code]['commercial_name'],
                'U.M': product_info[product_code]['unit']
            }
            total = 0.0
            for day in scheduled_days:
                qty = data_by_area[area][product_code][day]
                row[day] = int(round(qty)) if is_int else round(qty, 1)
                total += qty
            row['Total general'] = int(round(total)) if is_int else round(total, 1)
            rows.append(row)
    
    import pandas as pd
    df = pd.DataFrame(rows)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=f"Salidas_{rotation.week}", index=False)
    
    output.seek(0)
    filename = f"Salidas_Productos_Semana_{rotation.week}.xlsx"
    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


@fumigacion_bp.route('/ordenes/<int:order_id>/cambiar-estado', methods=['POST'])
@login_required
@permission_required('ordenes_ver')
def orden_cambiar_estado(order_id):
    order = FumigationOrder.query.get_or_404(order_id)
    new_status = request.form.get('status')
    if new_status in ['GENERADA', 'APROBADA', 'EJECUTADA', 'CANCELADA']:
        order.status = new_status
        db.session.commit()
        record_audit('FUMIGACION', 'UPDATE_ORDER_STATUS', 'FumigationOrder', order.id, details={'order_number': order.order_number, 'status': new_status})
        flash(f"Estado de la orden {order.order_number} cambiado a {new_status}.", "success")
    return redirect(url_for('fumigacion.orden_detalle', order_id=order.id))


@fumigacion_bp.route('/ordenes/<int:order_id>/editar-titulo', methods=['POST'])
@login_required
@permission_required('ordenes_ver')
def orden_editar_titulo(order_id):
    order = FumigationOrder.query.get_or_404(order_id)
    if request.is_json:
        data = request.get_json() or {}
        new_title = data.get('title', '').strip()
    else:
        new_title = request.form.get('title', '').strip()
    
    if new_title:
        order.title = new_title
        db.session.commit()
        record_audit('FUMIGACION', 'UPDATE_ORDER_TITLE', 'FumigationOrder', order.id, details={'order_number': order.order_number, 'title': new_title})
    
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'title': order.title or order.display_title})
    
    flash("Nombre / Título del programa actualizado correctamente.", "success")
    return redirect(url_for('fumigacion.orden_detalle', order_id=order.id))



# ==================== APLICACIONES ADICIONALES ====================

@fumigacion_bp.route('/aplicaciones-adicionales', methods=['GET', 'POST'])
@login_required
@permission_required('aplicaciones_extras')
def aplicaciones_adicionales():
    if request.method == 'POST':
        week = request.form.get('week', '').strip()
        app_type = request.form.get('application_type', 'FUMIGACION')
        scheduled_day = request.form.get('scheduled_day', 'Lunes')
        zone = request.form.get('zone', '').strip()
        block_name = request.form.get('block_name', '').strip()
        suffix = request.form.get('suffix', 'A').strip().upper()
        crop_name = request.form.get('crop_name', '').strip()
        bed_start = int(request.form.get('bed_start', 1))
        bed_end = int(request.form.get('bed_end', 1))
        standard_beds = float(request.form.get('standard_beds', 1.0))
        liters_per_bed = float(request.form.get('liters_per_bed', 5.0))
        prod_id = int(request.form.get('product_id'))
        dose_applied = float(request.form.get('dose_applied', 1.0))
        reason = request.form.get('reason', '').strip()
        notes = request.form.get('notes', '').strip()

        prod = Product.query.get(prod_id)
        if not prod:
            flash("Producto no válido.", "danger")
            return redirect(url_for('fumigacion.aplicaciones_adicionales'))

        dose_unit = prod.unit or 'CC'
        total_liters = round(standard_beds * liters_per_bed, 1)
        total_product = round_product_amount(total_liters * dose_applied, dose_unit)
        operator = get_operator_for_zone(zone)

        add_app = AdditionalApplication(
            week=week,
            application_type=app_type,
            scheduled_day=scheduled_day,
            zone=zone,
            block_name=block_name,
            suffix=suffix,
            crop_name=crop_name,
            bed_start=bed_start,
            bed_end=bed_end,
            standard_beds=standard_beds,
            liters_per_bed=liters_per_bed,
            total_liters=total_liters,
            product_id=prod.id,
            product_code=prod.code,
            dose_applied=dose_applied,
            dose_unit=dose_unit,
            total_product=total_product,
            operator=operator,
            reason=reason,
            notes=notes
        )
        db.session.add(add_app)
        db.session.commit()

        # Update requisition difference if active rotation exists for this week
        rot = Rotation.query.filter_by(week=week, status='APROBADA').first() or Rotation.query.filter_by(week=week).first()
        if rot:
            RequisitionService.sync_with_final_orders(rot.id)

        record_audit('FUMIGACION', 'CREATE_ADDITIONAL_APP', 'AdditionalApplication', add_app.id, details={'block': block_name, 'product': prod.code, 'reason': reason})
        flash(f"Aplicación adicional registrada en {block_name} ({reason}).", "success")
        return redirect(url_for('fumigacion.aplicaciones_adicionales'))

    active_products = Product.query.filter_by(is_active=True).order_by(Product.code.asc()).all()
    active_crops = Crop.query.filter_by(is_active=True).order_by(Crop.name.asc()).all()
    recent_apps = AdditionalApplication.query.order_by(AdditionalApplication.created_at.desc()).limit(100).all()

    # Distinct block to zone map
    block_records = db.session.query(CropStateRecord.block_full, CropStateRecord.zone, CropStateRecord.crop_master).distinct().all()
    block_zone_map = {}
    for b_full, z, c_mast in block_records:
        if b_full:
            block_zone_map[b_full.strip()] = {
                'zone': (z or '').strip(),
                'crop': (c_mast or '').strip()
            }

    return render_template(
        'fumigacion/aplicaciones_adicionales.html',
        recent_apps=recent_apps,
        active_products=active_products,
        active_crops=active_crops,
        block_zone_map=block_zone_map
    )


@fumigacion_bp.route('/aplicaciones-adicionales/guardar-lote', methods=['POST'])
@login_required
@permission_required('aplicaciones_extras')
def aplicaciones_adicionales_guardar_lote():
    """
    Saves multiple boxes of additional applications (multi-product mixture & multi-block matrix).
    """
    data = request.get_json() or {}
    week = (data.get('week') or '').strip()
    boxes = data.get('boxes', [])

    if not week:
        return jsonify({'success': False, 'error': 'La semana es obligatoria (ej. 2026-36).'}), 400

    if not boxes or not isinstance(boxes, list):
        return jsonify({'success': False, 'error': 'No se enviaron boxes de aplicación.'}), 400

    created_records = []
    
    for b_idx, box in enumerate(boxes):
        app_type = box.get('application_type', 'FUMIGACION')
        sched_day = box.get('scheduled_day', 'Miércoles')
        box_reason = (box.get('reason') or f'Mancha / Foco Box {b_idx + 1}').strip()
        box_notes = (box.get('notes') or '').strip()
        products = box.get('products', [])
        blocks = box.get('blocks', [])

        if not products:
            continue
        if not blocks:
            continue

        for blk in blocks:
            zone = (blk.get('zone') or '').strip()
            block_name = (blk.get('block_name') or '').strip()
            suffix = (blk.get('suffix') or 'A').strip().upper()
            crop_name = (blk.get('crop_name') or '').strip()
            bed_start = int(blk.get('bed_start', 1))
            bed_end = int(blk.get('bed_end', 1))
            standard_beds = float(blk.get('standard_beds', 1.0))
            liters_per_bed = float(blk.get('liters_per_bed', 5.5))
            total_liters = round(standard_beds * liters_per_bed, 1)
            operator = get_operator_for_zone(zone)

            for prod_item in products:
                prod_id = prod_item.get('product_id')
                dose_applied = float(prod_item.get('dose', 1.0) or 1.0)
                prod = Product.query.get(prod_id) if prod_id else None
                prod_code = prod.code if prod else prod_item.get('product_code', 'N/A')
                dose_unit = prod.unit if (prod and prod.unit) else prod_item.get('unit', 'CC')
                total_product = round_product_amount(total_liters * dose_applied, dose_unit)

                add_app = AdditionalApplication(
                    week=week,
                    application_type=app_type,
                    scheduled_day=sched_day,
                    zone=zone,
                    block_name=block_name,
                    suffix=suffix,
                    crop_name=crop_name,
                    bed_start=bed_start,
                    bed_end=bed_end,
                    standard_beds=standard_beds,
                    liters_per_bed=liters_per_bed,
                    total_liters=total_liters,
                    product_id=prod.id if prod else None,
                    product_code=prod_code,
                    dose_applied=dose_applied,
                    dose_unit=dose_unit,
                    total_product=total_product,
                    operator=operator,
                    reason=box_reason,
                    notes=box_notes
                )
                db.session.add(add_app)
                created_records.append(add_app)

    db.session.commit()

    # Sync with rotation requisition if exists
    rot = Rotation.query.filter_by(week=week, status='APROBADA').first() or Rotation.query.filter_by(week=week).first()
    if rot:
        RequisitionService.sync_with_final_orders(rot.id)

    record_audit('FUMIGACION', 'CREATE_BATCH_ADDITIONAL_APPS', 'AdditionalApplication', len(created_records), details={'week': week, 'count': len(created_records)})

    return jsonify({
        'success': True,
        'count': len(created_records),
        'message': f'Se registraron exitosamente {len(created_records)} aplicaciones adicionales en la semana {week}.'
    })


@fumigacion_bp.route('/aplicaciones-adicionales/<int:app_id>/eliminar', methods=['POST'])
@login_required
@permission_required('aplicaciones_extras')
def aplicaciones_adicionales_eliminar(app_id):
    app_obj = AdditionalApplication.query.get_or_404(app_id)
    week = app_obj.week
    blk_name = app_obj.block_name
    prod_code = app_obj.product_code

    db.session.delete(app_obj)
    db.session.commit()

    rot = Rotation.query.filter_by(week=week, status='APROBADA').first() or Rotation.query.filter_by(week=week).first()
    if rot:
        RequisitionService.sync_with_final_orders(rot.id)

    record_audit('FUMIGACION', 'DELETE_ADDITIONAL_APP', 'AdditionalApplication', app_id, details={'week': week, 'block': blk_name, 'product': prod_code})
    flash(f"Aplicación adicional en {blk_name} ({prod_code}) eliminada.", "success")
    return redirect(url_for('fumigacion.aplicaciones_adicionales'))

