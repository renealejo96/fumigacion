import io
import datetime
import pandas as pd
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from app.extensions import db
from app.shared.models import (
    Rotation, FumigationOrder, FumigationOrderDetail, FumigationOrderProductSummary,
    WarehouseDispatchLog, Product, Crop
)
from app.modules.fumigacion.services.order_service import OrderService
from app.shared.utils import (
    get_operator_for_zone, get_toxicological_color_info, 
    get_local_now, format_local_datetime, is_integer_unit, round_product_amount,
    is_liquid_unit, is_solid_unit
)
from app.shared.audit import record_audit
from app.modules.auth.routes import login_required, permission_required

bodega_bp = Blueprint('bodega', __name__)


@bodega_bp.route('/')
@bodega_bp.route('/salidas')
@login_required
@permission_required('bodega')
def salidas():
    """
    Centro de Salidas de Bodega:
    Muestra únicamente las salidas y requerimientos de insumos de las rotaciones
    y órdenes OFICIALES APROBADAS por los agrónomos / asistentes.
    """
    # Query only approved rotations
    approved_rotations = Rotation.query.filter(Rotation.status == 'APROBADA').order_by(Rotation.week.desc(), Rotation.version.desc()).all()
    
    if not approved_rotations:
        flash("Aún no hay planificaciones oficiales aprobadas en el sistema para despacho de bodega.", "info")
        return render_template(
            'bodega/salidas.html',
            rotation=None,
            orders=[],
            scheduled_days=[],
            data_by_area={},
            general_summary={},
            product_info={},
            all_rotations=[],
            prev_rotation=None,
            next_rotation=None,
            dispatch_logs=[],
            total_products_count=0,
            total_volume_liters=0.0,
            total_beds=0.0
        )

    # Determine which rotation to display
    target_id = request.args.get('rotation_id', type=int)
    target_week = request.args.get('week', '').strip()

    current_rot = None
    if target_id:
        current_rot = Rotation.query.filter_by(id=target_id, status='APROBADA').first()
    elif target_week:
        current_rot = Rotation.query.filter_by(week=target_week, status='APROBADA').order_by(Rotation.version.desc()).first()

    if not current_rot:
        # Pick first approved rotation that has official orders, or first approved
        for r in approved_rotations:
            official_orders_count = FumigationOrder.query.filter(
                FumigationOrder.rotation_id == r.id,
                FumigationOrder.status.in_(['APROBADA', 'EJECUTADA'])
            ).count()
            if official_orders_count > 0:
                current_rot = r
                break
        if not current_rot:
            current_rot = approved_rotations[0]

    # Calculate previous and next rotation in chronological sequence
    prev_rotation = None
    next_rotation = None
    for idx, r in enumerate(approved_rotations):
        if r.id == current_rot.id:
            if idx > 0:
                next_rotation = approved_rotations[idx - 1]
            if idx < len(approved_rotations) - 1:
                prev_rotation = approved_rotations[idx + 1]
            break

    # Get ONLY official approved orders for this rotation
    orders = FumigationOrder.query.filter(
        FumigationOrder.rotation_id == current_rot.id,
        FumigationOrder.status.in_(['APROBADA', 'EJECUTADA'])
    ).order_by(FumigationOrder.round_number.asc()).all()

    # Filter by specific program if requested
    target_order_id = request.args.get('order_id', type=int)
    selected_order = None
    if target_order_id:
        selected_order = next((o for o in orders if o.id == target_order_id), None)

    display_orders = [selected_order] if selected_order else orders

    # Get dispatch & print logs for this week
    dispatch_logs = WarehouseDispatchLog.query.filter_by(week=current_rot.week).order_by(WarehouseDispatchLog.created_at.desc()).limit(20).all()

    # Get unique scheduled days in execution order
    scheduled_days = []
    for ord in display_orders:
        if ord.scheduled_day and ord.scheduled_day not in scheduled_days:
            scheduled_days.append(ord.scheduled_day)

    # Build data structure: {area: {product_code: {day: quantity}}}
    data_by_area = {}
    product_info = {}

    for order in display_orders:
        for detail in order.details:
            area = (detail.crop_name or 'GENERAL').strip()
            product_code = (detail.product_code or '').strip()
            day = order.scheduled_day
            amount = float(detail.product_amount or 0.0)

            if not product_code or product_code == 'SIN PRODUCTO':
                continue

            if area not in data_by_area:
                data_by_area[area] = {}
            if product_code not in data_by_area[area]:
                data_by_area[area][product_code] = {d: 0.0 for d in scheduled_days}

            if product_code not in product_info:
                product_info[product_code] = {
                    'commercial_name': detail.commercial_name or product_code,
                    'unit': detail.unit or 'CC'
                }

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
        'bodega/salidas.html',
        rotation=current_rot,
        orders=orders,
        display_orders=display_orders,
        selected_order=selected_order,
        scheduled_days=scheduled_days,
        data_by_area=data_by_area,
        general_summary=general_summary,
        product_info=product_info,
        all_rotations=approved_rotations,
        prev_rotation=prev_rotation,
        next_rotation=next_rotation,
        dispatch_logs=dispatch_logs,
        total_products_count=total_products_count,
        total_volume_liters=total_volume_liters,
        total_beds=total_beds
    )


@bodega_bp.route('/ordenes')
@login_required
@permission_required('bodega')
def ordenes():
    """
    Listado oficial de órdenes de fumigación aprobadas listas para despacho en bodega.
    """
    week_filter = request.args.get('week', '').strip()
    
    query = FumigationOrder.query.join(Rotation).filter(
        Rotation.status == 'APROBADA',
        FumigationOrder.status.in_(['APROBADA', 'EJECUTADA'])
    )

    if week_filter:
        query = query.filter(FumigationOrder.week == week_filter)

    official_orders = query.order_by(FumigationOrder.week.desc(), FumigationOrder.round_number.asc()).all()

    # Get distinct weeks of approved orders for filter
    approved_weeks = [r.week for r in Rotation.query.filter(Rotation.status == 'APROBADA').order_by(Rotation.week.desc()).all()]
    approved_weeks = list(dict.fromkeys(approved_weeks))

    return render_template(
        'bodega/ordenes.html',
        orders=official_orders,
        approved_weeks=approved_weeks,
        selected_week=week_filter
    )


@bodega_bp.route('/ordenes/<int:order_id>')
@login_required
@permission_required('bodega')
def orden_detalle(order_id):
    """
    Vista detallada de la orden oficial en el sistema para el personal de bodega.
    """
    order = FumigationOrder.query.get_or_404(order_id)
    
    # Structure details grouped by Zone / Operator
    zones_map = {}
    distinct_products_map = {}

    for d in order.details:
        z_name = d.zone or 'ZONA GENERAL'
        if z_name not in zones_map:
            zones_map[z_name] = {
                'zone_name': z_name,
                'operator': d.operator,
                'details': [],
                'total_beds': 0.0,
                'total_liters': 0.0,
                'products_by_code': {}
            }
        zones_map[z_name]['details'].append(d)
        zones_map[z_name]['total_beds'] += (d.standard_beds or 0.0)
        zones_map[z_name]['total_liters'] += (d.total_liters or 0.0)

        if d.product_code and d.product_code != 'SIN PRODUCTO':
            u = d.unit or 'CC'
            is_liq = is_liquid_unit(u)
            is_sol = is_solid_unit(u)

            # Accumulate in zone
            if d.product_code not in zones_map[z_name]['products_by_code']:
                zones_map[z_name]['products_by_code'][d.product_code] = {
                    'product_code': d.product_code,
                    'commercial_name': d.commercial_name or d.product_code,
                    'unit': u,
                    'dose': d.dose,
                    'is_liquid': is_liq,
                    'is_solid': is_sol,
                    'total_amount': 0.0,
                    'pest': d.pest
                }
            zones_map[z_name]['products_by_code'][d.product_code]['total_amount'] += (d.product_amount or 0.0)

            # Accumulate in overall
            if d.product_code not in distinct_products_map:
                distinct_products_map[d.product_code] = {
                    'code': d.product_code,
                    'name': d.commercial_name or d.product_code,
                    'unit': u,
                    'dose': d.dose,
                    'is_liquid': is_liq,
                    'is_solid': is_sol,
                    'pest': d.pest,
                    'color': d.toxicological_color,
                    'category': d.toxicological_category,
                    'total_amount': 0.0
                }
            distinct_products_map[d.product_code]['total_amount'] += (d.product_amount or 0.0)

    # Process liquids and solids per zone
    zones_list = list(zones_map.values())
    zones_list.sort(key=lambda z: z['zone_name'])
    for z in zones_list:
        prods = list(z['products_by_code'].values())
        z['liquid_products'] = [p for p in prods if p['is_liquid']]
        z['solid_products'] = [p for p in prods if not p['is_liquid']]

    all_products = list(distinct_products_map.values())
    overall_liquids = [p for p in all_products if p['is_liquid']]
    overall_solids = [p for p in all_products if not p['is_liquid']]

    return render_template(
        'bodega/orden_detalle.html',
        order=order,
        zones_list=zones_list,
        products_summary=order.products_summary,
        distinct_products=all_products,
        overall_liquids=overall_liquids,
        overall_solids=overall_solids
    )


@bodega_bp.route('/ordenes/<int:order_id>/editar-titulo', methods=['POST'])
@login_required
@permission_required('bodega')
def orden_editar_titulo(order_id):
    """Actualiza el nombre / título del programa de fumigación"""
    order = FumigationOrder.query.get_or_404(order_id)
    if request.is_json:
        data = request.get_json() or {}
        new_title = data.get('title', '').strip()
    else:
        new_title = request.form.get('title', '').strip()
    
    if new_title:
        order.title = new_title
        db.session.commit()
        record_audit('BODEGA', 'UPDATE_PROGRAM_TITLE', 'FumigationOrder', order.id, details={'order_number': order.order_number, 'title': new_title})
    
    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'success': True, 'title': order.title or order.display_title})
    
    flash("Nombre del programa actualizado correctamente.", "success")
    return redirect(url_for('bodega.orden_detalle', order_id=order.id))



@bodega_bp.route('/rotacion/<int:rotation_id>/exportar-excel')
@login_required
@permission_required('bodega')
def exportar_salidas_excel(rotation_id):
    """Exporta las salidas oficiales de bodega a Excel"""
    rotation = Rotation.query.filter_by(id=rotation_id, status='APROBADA').first_or_404()
    target_order_id = request.args.get('order_id', type=int)

    orders_query = FumigationOrder.query.filter(
        FumigationOrder.rotation_id == rotation.id,
        FumigationOrder.status.in_(['APROBADA', 'EJECUTADA'])
    ).order_by(FumigationOrder.round_number.asc())

    if target_order_id:
        orders_query = orders_query.filter(FumigationOrder.id == target_order_id)

    orders = orders_query.all()

    if not orders:
        flash("No hay órdenes oficiales aprobadas para esta consulta.", "warning")
        return redirect(url_for('bodega.salidas', rotation_id=rotation_id))

    scheduled_days = []
    for ord in orders:
        if ord.scheduled_day and ord.scheduled_day not in scheduled_days:
            scheduled_days.append(ord.scheduled_day)

    data_by_area = {}
    product_info = {}

    for order in orders:
        for detail in order.details:
            area = (detail.crop_name or 'GENERAL').strip()
            product_code = (detail.product_code or '').strip()
            day = order.scheduled_day
            amount = float(detail.product_amount or 0.0)

            if not product_code or product_code == 'SIN PRODUCTO':
                continue

            if area not in data_by_area:
                data_by_area[area] = {}
            if product_code not in data_by_area[area]:
                data_by_area[area][product_code] = {d: 0.0 for d in scheduled_days}

            if product_code not in product_info:
                product_info[product_code] = {
                    'commercial_name': detail.commercial_name or product_code,
                    'unit': detail.unit or 'CC'
                }

            if day in data_by_area[area][product_code]:
                data_by_area[area][product_code][day] += amount

    rows = []
    for area in sorted(data_by_area.keys()):
        for product_code in sorted(data_by_area[area].keys()):
            u = product_info[product_code]['unit']
            is_int = is_integer_unit(u)

            row = {
                'ÁREA / VARIEDAD': area,
                'PRODUCTO AGROQUÍMICO': product_info[product_code]['commercial_name'],
                'U.M': u
            }
            total = 0.0
            for day in scheduled_days:
                qty = data_by_area[area][product_code][day]
                row[day] = int(round(qty)) if is_int else round(qty, 1)
                total += qty
            row['Total General Despacho'] = int(round(total)) if is_int else round(total, 1)
            rows.append(row)

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=f"Salidas_Bodega_{rotation.week}", index=False)

        ws = writer.sheets[f"Salidas_Bodega_{rotation.week}"]
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = col[0].column_letter
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    output.seek(0)
    filename = f"Salidas_Bodega_Semana_{rotation.week}.xlsx"

    # Log action
    user_name = session.get('full_name') or session.get('username') or 'Usuario Bodega'
    log_entry = WarehouseDispatchLog(
        week=rotation.week,
        rotation_id=rotation.id,
        action='EXPORTAR_EXCEL',
        performed_by=user_name,
        role=session.get('role', 'BODEGA'),
        notes=f"Exportación de planilla de salidas de bodega Semana {rotation.week} a Excel."
    )
    db.session.add(log_entry)
    db.session.commit()

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


@bodega_bp.route('/ordenes/<int:order_id>/exportar-excel')
@login_required
@permission_required('bodega')
def orden_exportar_excel(order_id):
    """Exporta la orden oficial a Excel para el personal de bodega"""
    order = FumigationOrder.query.get_or_404(order_id)
    excel_stream = OrderService.export_order_to_excel(order)
    filename = f"Orden_Oficial_{order.order_number}.xlsx"
    return send_file(
        excel_stream,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )


@bodega_bp.route('/rotaciones/<int:rotation_id>/marcar-impresa', methods=['POST'])
@login_required
@permission_required('bodega')
def marcar_impresa(rotation_id):
    """Marca la planilla de salidas como impresa y registra log"""
    rotation = Rotation.query.filter_by(id=rotation_id, status='APROBADA').first_or_404()
    user_name = session.get('full_name') or session.get('username') or 'Usuario Bodega'
    user_role = session.get('role') or 'BODEGA'

    rotation.is_salidas_printed = True
    rotation.salidas_printed_at = get_local_now()
    rotation.salidas_printed_by = user_name

    for ord in rotation.orders:
        if ord.status in ['APROBADA', 'EJECUTADA']:
            ord.is_printed = True
            ord.printed_at = get_local_now()
            ord.printed_by = user_name

    log_entry = WarehouseDispatchLog(
        week=rotation.week,
        rotation_id=rotation.id,
        action='IMPRESION_SALIDAS',
        performed_by=user_name,
        role=user_role,
        notes=f"Planilla de salidas de la Semana {rotation.week} impresa por Bodega."
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
    return redirect(url_for('bodega.salidas', rotation_id=rotation.id))


@bodega_bp.route('/rotaciones/<int:rotation_id>/marcar-despachada', methods=['POST'])
@login_required
@permission_required('bodega')
def marcar_despachada(rotation_id):
    """Alterna el estado de entrega física de insumos en bodega"""
    rotation = Rotation.query.filter_by(id=rotation_id, status='APROBADA').first_or_404()
    user_name = session.get('full_name') or session.get('username') or 'Usuario Bodega'
    user_role = session.get('role') or 'BODEGA'

    rotation.is_salidas_dispatched = not rotation.is_salidas_dispatched
    if rotation.is_salidas_dispatched:
        rotation.salidas_dispatched_at = get_local_now()
        rotation.salidas_dispatched_by = user_name
        status_action = "DESPACHO_BODEGA"
        msg_text = f"Insumos de la Semana {rotation.week} marcados como ENTREGADOS A OPERARIOS."
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
    return redirect(url_for('bodega.salidas', rotation_id=rotation.id))
