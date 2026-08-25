import io
import datetime
import pandas as pd
from app.extensions import db
from app.shared.models import (
    Rotation, Requisition, RequisitionItem, 
    FumigationOrder, FumigationOrderProductSummary, 
    AdditionalApplication, Product
)
from app.modules.fumigacion.services.calculation_engine import CalculationEngine
from app.shared.utils import is_integer_unit, round_product_amount

class RequisitionService:

    @classmethod
    def generate_or_update_forecast(cls, rotation_id: int, title: str = None) -> Requisition:
        """
        Generates or updates the 15-day advance purchase requisition from the rotation plan.
        """
        rotation = Rotation.query.get_or_404(rotation_id)
        
        product_totals = {}
        total_liters_all = 0.0

        for r in rotation.rounds:
            calc = CalculationEngine.calculate_round(r)
            total_liters_all += calc['totals']['total_liters']

            for ps in calc['product_summaries']:
                key = ps['product_code']
                if key not in product_totals:
                    product_totals[key] = {
                        'product_id': ps['product_id'],
                        'product_code': ps['product_code'],
                        'commercial_name': ps['commercial_name'],
                        'dose': ps['dose'],
                        'dose_unit': ps['dose_unit'],
                        'quantity_forecast': 0.0,
                        'pest': ps['pest']
                    }
                product_totals[key]['quantity_forecast'] += ps['total_required_quantity']

        # Find or create requisition
        req = Requisition.query.filter_by(rotation_id=rotation.id).first()
        if not req:
            req = Requisition(
                rotation_id=rotation.id,
                week=rotation.week,
                title=title or f"Requisición de Agroquímicos Semana {rotation.week}",
                status="PEDIDO_INICIAL",
                total_liters=round(total_liters_all, 1)
            )
            db.session.add(req)
            db.session.flush()
        else:
            req.total_liters = round(total_liters_all, 1)
            RequisitionItem.query.filter_by(requisition_id=req.id).delete()
            db.session.flush()

        for p_info in product_totals.values():
            qty_f = round_product_amount(p_info['quantity_forecast'], p_info['dose_unit'])
            item = RequisitionItem(
                requisition_id=req.id,
                product_id=p_info['product_id'],
                product_code=p_info['product_code'],
                commercial_name=p_info['commercial_name'],
                average_dose=p_info['dose'],
                unit=p_info['dose_unit'],
                quantity_forecast=qty_f,
                quantity_final=qty_f,
                difference=0.0,
                pest=p_info['pest']
            )
            db.session.add(item)

        db.session.commit()
        return req

    @classmethod
    def get_comparison_data(cls, rotation_id: int):
        """
        Builds the unified comparative data between:
        1. Cantidad Comprada (Requisición 15 días)
        2. Cantidad Ejecutada Real (Órdenes de Rotación generadas con el nuevo plano)
        3. Aplicaciones Adicionales / Extras de la semana
        4. Total Requerido Real = Ejecutado + Extras
        5. Diferencia = Total Requerido Real - Comprado
        """
        rotation = Rotation.query.get_or_404(rotation_id)
        req = Requisition.query.filter_by(rotation_id=rotation.id).first()
        if not req:
            req = cls.generate_or_update_forecast(rotation_id)

        # Forecast items from purchase order
        forecast_by_code = {it.product_code: it for it in req.items}

        # Real quantities from generated orders
        orders = FumigationOrder.query.filter_by(rotation_id=rotation.id).all()
        orders_by_code = {}
        for ord in orders:
            for ps in ord.products_summary:
                c = ps.product_code
                if c not in orders_by_code:
                    orders_by_code[c] = {
                        'product_code': c,
                        'commercial_name': ps.commercial_name,
                        'unit': ps.dose_unit,
                        'quantity_orders': 0.0,
                        'dose': ps.dose,
                        'pest': ps.pest
                    }
                orders_by_code[c]['quantity_orders'] += ps.total_required_quantity

        # Additional / Spot applications for this week
        add_apps = AdditionalApplication.query.filter_by(week=rotation.week).all()
        extras_by_code = {}
        for a in add_apps:
            c = a.product_code
            if c not in extras_by_code:
                extras_by_code[c] = {
                    'product_code': c,
                    'unit': a.dose_unit,
                    'quantity_extras': 0.0,
                    'reasons': []
                }
            extras_by_code[c]['quantity_extras'] += a.total_product
            if a.reason and a.reason not in extras_by_code[c]['reasons']:
                extras_by_code[c]['reasons'].append(a.reason)

        # Combine all product codes
        all_codes = list(set(list(forecast_by_code.keys()) + list(orders_by_code.keys()) + list(extras_by_code.keys())))
        all_codes.sort()

        comparison_rows = []
        for code in all_codes:
            f_item = forecast_by_code.get(code)
            o_item = orders_by_code.get(code)
            e_item = extras_by_code.get(code)

            # Determine product info
            prod = Product.query.filter_by(code=code).first()
            comm_name = prod.commercial_name if prod else (f_item.commercial_name if f_item else (o_item['commercial_name'] if o_item else code))
            unit = prod.unit if prod else (f_item.unit if f_item else (o_item['unit'] if o_item else (e_item['unit'] if e_item else 'CC')))
            pest = prod.pest if prod else (f_item.pest if f_item else (o_item['pest'] if o_item else 'Adicional'))

            qty_forecast = f_item.quantity_forecast if f_item else 0.0
            qty_orders = o_item['quantity_orders'] if o_item else 0.0
            qty_extras = e_item['quantity_extras'] if e_item else 0.0

            total_real = qty_orders + qty_extras
            diff = total_real - qty_forecast

            # Determine product origin
            extra_reasons_list = e_item['reasons'] if e_item else []
            extra_reasons_str = ", ".join(extra_reasons_list) if extra_reasons_list else ""

            if qty_forecast > 0 and qty_extras > 0:
                origin = 'AMBOS'
                origin_label = 'Rotación + Extra'
                origin_badge = 'bg-dark text-white'
            elif qty_forecast > 0:
                origin = 'ROTACION'
                origin_label = 'Rotación (15 Días)'
                origin_badge = 'bg-primary'
            elif qty_extras > 0:
                origin = 'EXTRA'
                origin_label = 'Aplicación Extra / Manchas'
                origin_badge = 'bg-danger'
            else:
                origin = 'OTRO'
                origin_label = 'Orden Directa'
                origin_badge = 'bg-secondary'

            # Status
            if qty_forecast > 0 and diff > 0:
                status = 'DEFICIT'
                status_label = f'DÉFICIT (Comprar +{round(diff, 1)} {unit})'
                badge_class = 'bg-danger text-white'
            elif qty_forecast > 0 and diff < 0:
                status = 'SUPERAVIT'
                status_label = f'SUPERÁVIT (Sobra {round(abs(diff), 1)} {unit})'
                badge_class = 'bg-info text-white'
            elif qty_forecast == 0 and total_real > 0:
                status = 'ADICIONAL_PURO'
                status_label = f'NO PEDIDO (Adicional +{round(total_real, 1)} {unit})'
                badge_class = 'bg-warning text-dark'
            else:
                status = 'OK'
                status_label = 'OK (Abastecido)'
                badge_class = 'bg-success text-white'

            comparison_rows.append({
                'product_code': code,
                'commercial_name': comm_name,
                'unit': unit,
                'origin': origin,
                'origin_label': origin_label,
                'origin_badge': origin_badge,
                'extra_reasons_str': extra_reasons_str,
                'quantity_forecast': round_product_amount(qty_forecast, unit),
                'quantity_orders': round_product_amount(qty_orders, unit),
                'quantity_extras': round_product_amount(qty_extras, unit),
                'total_real': round_product_amount(total_real, unit),
                'difference': round_product_amount(diff, unit),
                'status': status,
                'status_label': status_label,
                'badge_class': badge_class,
                'pest': pest
            })

        # Calculate totals
        total_forecast = sum(r['quantity_forecast'] for r in comparison_rows)
        total_orders = sum(r['quantity_orders'] for r in comparison_rows)
        total_extras = sum(r['quantity_extras'] for r in comparison_rows)
        total_real_all = sum(r['total_real'] for r in comparison_rows)
        total_diff = sum(r['difference'] for r in comparison_rows)

        return {
            'requisition': req,
            'rotation': rotation,
            'rows': comparison_rows,
            'totals': {
                'total_forecast': round(total_forecast, 2),
                'total_orders': round(total_orders, 2),
                'total_extras': round(total_extras, 2),
                'total_real': round(total_real_all, 2),
                'total_difference': round(total_diff, 2)
            }
        }

    @classmethod
    def sync_with_final_orders(cls, rotation_id: int):
        """
        Synchronizes the Requisition model with the latest state of orders and extras.
        """
        data = cls.get_comparison_data(rotation_id)
        req = data['requisition']

        for row in data['rows']:
            it = RequisitionItem.query.filter_by(requisition_id=req.id, product_code=row['product_code']).first()
            if it:
                it.quantity_final = row['total_real']
                it.difference = row['difference']
            else:
                prod = Product.query.filter_by(code=row['product_code']).first()
                new_it = RequisitionItem(
                    requisition_id=req.id,
                    product_id=prod.id if prod else None,
                    product_code=row['product_code'],
                    commercial_name=row['commercial_name'],
                    average_dose=prod.dose_fumigation if prod else 0.0,
                    unit=row['unit'],
                    quantity_forecast=row['quantity_forecast'],
                    quantity_final=row['total_real'],
                    difference=row['difference'],
                    pest=row['pest']
                )
                db.session.add(new_it)

        req.status = "VALIDADO"
        db.session.commit()
        return req

    @staticmethod
    def export_requisition_to_excel(req_obj) -> io.BytesIO:
        """
        Exports the purchase comparison to an Excel workbook (.xlsx) with separate columns for
        Origen, Comprado 15 días, Ejecutado Real, Aplicaciones Extras, Total Requerido y Diferencia.
        """
        comp_data = RequisitionService.get_comparison_data(req_obj.rotation_id)
        rows = []
        for r in comp_data['rows']:
            u = r['unit']
            is_int = is_integer_unit(u)
            rows.append({
                'CÓDIGO PRODUCTO': r['product_code'],
                'PRODUCTO COMERCIAL': r['commercial_name'],
                'ORIGEN DEL PRODUCTO': r['origin_label'],
                'MOTIVO / DETALLE EXTRAS': r.get('extra_reasons_str', ''),
                'CANTIDAD COMPRADA (15 DÍAS)': int(round(r['quantity_forecast'])) if is_int else round(r['quantity_forecast'], 2),
                'CANTIDAD EJECUTADA REAL': int(round(r['quantity_orders'])) if is_int else round(r['quantity_orders'], 2),
                'APLICACIONES EXTRAS / MANCHAS': int(round(r['quantity_extras'])) if is_int else round(r['quantity_extras'], 2),
                'TOTAL REQUERIDO REAL': int(round(r['total_real'])) if is_int else round(r['total_real'], 2),
                'DIFERENCIA (+/-)': int(round(r['difference'])) if is_int else round(r['difference'], 2),
                'UNIDAD': r['unit'],
                'ESTADO COMPRA': r['status_label'],
                'BLANCO / PLAGA': r['pest']
            })

        df = pd.DataFrame(rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            sheet_title = f"Comparativa_{req_obj.week}"
            df.to_excel(writer, sheet_name=sheet_title, index=False)
            ws = writer.sheets[sheet_title]
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                col_letter = col[0].column_letter
                ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        output.seek(0)
        return output

    @classmethod
    def recalculate_with_budget(cls, requisition_id: int, budget_adjustments: list):
        """
        Recalcula la requisición sumando las camas de presupuesto.
        
        Args:
            requisition_id: ID de la requisición
            budget_adjustments: Lista de ajustes [{crop_name, age, stage, beds, reason}, ...]
        """
        requisition = Requisition.query.get_or_404(requisition_id)
        rotation = Rotation.query.get_or_404(requisition.rotation_id)
        
        # First, regenerate base requisition from rotation (without budget)
        product_totals = {}
        total_liters_all = 0.0
        
        # Calculate from rotation rounds
        for r in rotation.rounds:
            calc = CalculationEngine.calculate_round(r)
            total_liters_all += calc['totals']['total_liters']
            
            for ps in calc['product_summaries']:
                key = ps['product_code']
                if key not in product_totals:
                    product_totals[key] = {
                        'product_id': ps['product_id'],
                        'product_code': ps['product_code'],
                        'commercial_name': ps['commercial_name'],
                        'dose': ps['dose'],
                        'dose_unit': ps['dose_unit'],
                        'quantity_forecast': 0.0,
                        'pest': ps['pest']
                    }
                product_totals[key]['quantity_forecast'] += ps['total_required_quantity']
        
        # Now add budget adjustments
        # For each adjustment, calculate additional product needs
        for adj in budget_adjustments:
            crop_name = adj.get('crop_name')
            age = adj.get('age')
            stage = adj.get('stage')
            beds = adj.get('beds', 0)
            
            if not all([crop_name, age, stage, beds]):
                continue
            
            # Get liters per bed for this crop/age
            from app.shared.models import Litraje
            lit_rule = Litraje.query.filter_by(crop_name=crop_name, age=int(age)).first()
            liters_per_bed = lit_rule.liters_per_bed if lit_rule else 80.0  # Default 80L
            
            total_liters_budget = beds * liters_per_bed
            total_liters_all += total_liters_budget
            
            # Get products for this crop/stage from rotation rounds
            # We'll use the products from the first round that has this crop/stage
            products_to_apply = []
            for r in rotation.rounds:
                for item in r.items:
                    if item.crop_name == crop_name and item.phenological_stage == stage:
                        products_to_apply.append({
                            'product_id': item.product_id,
                            'product_code': item.product.code,
                            'commercial_name': item.product.commercial_name,
                            'dose': item.dose_applied,
                            'dose_unit': item.dose_unit,
                            'pest': item.product.pest
                        })
                if products_to_apply:
                    break  # Use products from first matching round
            
            # Calculate additional quantities for these products
            for prod_info in products_to_apply:
                key = prod_info['product_code']
                dose = prod_info['dose']
                
                # Calculate additional quantity needed
                additional_qty = (dose * total_liters_budget) / 100.0
                
                if key not in product_totals:
                    product_totals[key] = {
                        'product_id': prod_info['product_id'],
                        'product_code': prod_info['product_code'],
                        'commercial_name': prod_info['commercial_name'],
                        'dose': dose,
                        'dose_unit': prod_info['dose_unit'],
                        'quantity_forecast': 0.0,
                        'pest': prod_info['pest']
                    }
                
                product_totals[key]['quantity_forecast'] += additional_qty
        
        # Update requisition
        requisition.total_liters = round(total_liters_all, 1)
        
        # Delete old items and create new ones with updated quantities
        RequisitionItem.query.filter_by(requisition_id=requisition.id).delete()
        db.session.flush()
        
        for p_info in product_totals.values():
            item = RequisitionItem(
                requisition_id=requisition.id,
                product_id=p_info['product_id'],
                product_code=p_info['product_code'],
                commercial_name=p_info['commercial_name'],
                average_dose=p_info['dose'],
                unit=p_info['dose_unit'],
                quantity_forecast=round(p_info['quantity_forecast'], 2),
                quantity_final=round(p_info['quantity_forecast'], 2),
                difference=0.0,
                pest=p_info['pest']
            )
            db.session.add(item)
        
        db.session.commit()
        return requisition
