import io
import datetime
import pandas as pd
from app.extensions import db
from app.shared.models import FumigationOrder, FumigationOrderDetail, FumigationOrderProductSummary, RotationRound, Rotation
from app.modules.fumigacion.services.calculation_engine import CalculationEngine
from app.shared.audit import record_audit
from app.shared.utils import is_integer_unit, round_product_amount

class OrderService:

    @staticmethod
    def generate_order_number(week: str, round_number: int) -> str:
        clean_week = str(week).replace(' ', '').replace('/', '-')
        prefix = f"ORD-FUM-{clean_week}-V{round_number}"
        existing_count = FumigationOrder.query.filter(FumigationOrder.order_number.like(f"{prefix}%")).count()
        seq = existing_count + 1
        return f"{prefix}-{seq:03d}"

    @classmethod
    def create_order_from_round(cls, round_id: int, agronomist: str = "Agrónomo Responsable", notes: str = None, custom_segments: list = None) -> FumigationOrder:
        """
        Generates and freezes an immutable order snapshot with all specific columns and operator assignments.
        """
        round_obj = RotationRound.query.get_or_404(round_id)
        rotation = round_obj.rotation

        # Delete existing orders for this specific round in this rotation to prevent duplication
        existing_orders = FumigationOrder.query.filter_by(rotation_id=rotation.id, round_id=round_obj.id).all()
        for eo in existing_orders:
            FumigationOrderDetail.query.filter_by(order_id=eo.id).delete()
            FumigationOrderProductSummary.query.filter_by(order_id=eo.id).delete()
            db.session.delete(eo)
        db.session.flush()

        calc_result = CalculationEngine.calculate_round(round_obj, custom_review_segments=custom_segments)
        segments = calc_result['segments']
        product_summaries = calc_result['product_summaries']
        totals = calc_result['totals']

        order_num = cls.generate_order_number(rotation.week, round_obj.round_number)

        order = FumigationOrder(
            order_number=order_num,
            title=f"Programa de Fumigación {round_obj.name or f'Vuelta {round_obj.round_number}'} • Sem {rotation.week}",
            rotation_id=rotation.id,
            round_id=round_obj.id,
            week=rotation.week,
            round_number=round_obj.round_number,
            round_name=round_obj.name or f"Vuelta {round_obj.round_number}",
            scheduled_day=round_obj.scheduled_day,
            scheduled_date=round_obj.scheduled_date or datetime.date.today(),
            agronomist=agronomist or rotation.created_by or "Agrónomo Responsable",
            notes=notes or round_obj.notes or "",
            status="APROBADA",
            total_liters=totals['total_liters'],
            total_standard_beds=totals['total_standard_beds'],
            total_segments=totals['total_segments']
        )

        db.session.add(order)
        db.session.flush()

        # Create detailed item rows (one row per product in each segment mix)
        for seg in segments:
            products_detail = seg.get('products_detail', [])
            if not products_detail:
                # Segment without product
                detail = FumigationOrderDetail(
                    order_id=order.id,
                    round_number=order.round_number,
                    round_name=order.round_name,
                    scheduled_day=order.scheduled_day,
                    scheduled_date=order.scheduled_date,
                    operator=seg['operator'],
                    zone=seg['zone'],
                    block_name=seg['block_name'],
                    suffix=seg['suffix'],
                    crop_name=seg['crop_name'],
                    variety_specific=seg['variety'],
                    phenological_stage=seg['phenological_stage'],
                    real_age=seg['real_age'],
                    standard_beds=seg['standard_beds'],
                    bed_range=seg['bed_range'],
                    bed_count=seg['bed_count'],
                    product_code='SIN PRODUCTO',
                    commercial_name='-',
                    unit='-',
                    dose=0.0,
                    product_amount=0.0,
                    total_liters=seg['total_liters'],
                    liters_per_bed=seg['liters_per_bed'],
                    pest='',
                    active_ingredient='',
                    toxicological_category='',
                    toxicological_color='',
                    order_in_mix=0,
                    is_additional=seg.get('is_additional', False)
                )
                db.session.add(detail)
            else:
                for p_it in products_detail:
                    detail = FumigationOrderDetail(
                        order_id=order.id,
                        round_number=order.round_number,
                        round_name=order.round_name,
                        scheduled_day=order.scheduled_day,
                        scheduled_date=order.scheduled_date,
                        operator=seg['operator'],
                        zone=seg['zone'],
                        block_name=seg['block_name'],
                        suffix=seg['suffix'],
                        crop_name=seg['crop_name'],
                        variety_specific=seg['variety'],
                        phenological_stage=seg['phenological_stage'],
                        real_age=seg['real_age'],
                        standard_beds=seg['standard_beds'],
                        bed_range=seg['bed_range'],
                        bed_count=seg['bed_count'],
                        product_code=p_it['product_code'],
                        commercial_name=p_it['commercial_name'],
                        unit=p_it['dose_unit'],
                        dose=p_it['dose'],
                        product_amount=round_product_amount(p_it['product_amount'], p_it['dose_unit']),
                        total_liters=seg['total_liters'],
                        liters_per_bed=seg['liters_per_bed'],
                        pest=p_it['pest'],
                        active_ingredient=p_it['active_ingredient'],
                        toxicological_category=p_it['toxicological_category'],
                        toxicological_color=p_it['toxicological_color'],
                        order_in_mix=p_it['order_in_mix'],
                        is_additional=seg.get('is_additional', False)
                    )
                    db.session.add(detail)

        # Freeze product summaries
        for ps in product_summaries:
            summary = FumigationOrderProductSummary(
                order_id=order.id,
                product_id=ps['product_id'],
                product_code=ps['product_code'],
                commercial_name=ps['commercial_name'],
                dose=ps['dose'],
                dose_unit=ps['dose_unit'],
                total_required_quantity=round_product_amount(ps['total_required_quantity'], ps['dose_unit']),
                pest=ps['pest']
            )
            db.session.add(summary)

        # Update rotation status to APROBADA
        rotation.status = "APROBADA"
        rotation.approved_by = agronomist
        rotation.approved_at = datetime.datetime.utcnow()

        db.session.commit()

        record_audit(
            module="FUMIGACION",
            action="GENERATE_ORDER",
            entity_type="FumigationOrder",
            entity_id=order.id,
            user=agronomist,
            details={
                'order_number': order.order_number,
                'week': order.week,
                'round': order.round_name,
                'total_liters': order.total_liters
            }
        )

        return order

    @staticmethod
    def export_order_to_excel(order_obj) -> io.BytesIO:
        """
        Exports the fumigation order to a clean, well-formatted Excel workbook (.xlsx)
        repeating values row by row without gaps so the warehouse (almacén) can filter and weigh directly.
        """
        rows = []
        for d in order_obj.details:
            is_int = is_integer_unit(d.unit)
            amt = int(round(d.product_amount)) if is_int else round(d.product_amount, 2)
            
            rows.append({
                'VTA': d.round_name,
                'DÍA': d.scheduled_day,
                'FECHA': d.scheduled_date.strftime('%Y-%m-%d') if d.scheduled_date else '',
                'ZONA': d.zone or '',
                'BLOQUE': d.block_name,
                'SUFIJO': d.suffix,
                'VARIEDAD': d.crop_name,
                'EDAD': d.real_age,
                'CAMAS': round(d.standard_beds, 2),
                'UBICACION': d.bed_range,
                'PRODUCTO': d.product_code,
                'NOMBRE COMERCIAL': d.commercial_name,
                'UM': d.unit,
                'DOSIS': d.dose,
                'TOTAL PRODUCTO': amt,
                'TOTAL LITROS': round(d.total_liters, 1),
                'LT/CAMA': round(d.liters_per_bed, 1),
                'PLAGA': d.pest or '',
                'INGREDIENTE ACTIVO': d.active_ingredient or '',
                'CT': d.toxicological_category or '',
                'COLOR': d.toxicological_color or '',
                'OPERARIO': d.operator
            })

        df = pd.DataFrame(rows)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=f"Orden_{order_obj.round_name}", index=False)
            
            # Auto-adjust column widths in openpyxl
            ws = writer.sheets[f"Orden_{order_obj.round_name}"]
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = col[0].column_letter
                ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

        output.seek(0)
        return output
