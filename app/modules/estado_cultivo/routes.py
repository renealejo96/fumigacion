from flask import Blueprint, render_template, request, jsonify
from app.extensions import db
from app.shared.models import CropStateRecord, Crop
from app.modules.fumigacion.services.calculation_engine import CalculationEngine
from app.modules.auth.routes import login_required, permission_required

estado_cultivo_bp = Blueprint('estado_cultivo', __name__)

@estado_cultivo_bp.route('/')
@login_required
@permission_required('catalogos')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    crop_filter = request.args.get('crop', '').strip()
    zone_filter = request.args.get('zone', '').strip()
    block_filter = request.args.get('block', '').strip()
    week_filter = request.args.get('week', '').strip()
    view_mode = request.args.get('view', 'segments')  # 'segments' or 'beds'

    query = CropStateRecord.query.filter(
        CropStateRecord.crop_master.isnot(None),
        CropStateRecord.crop_master != 'VACIO'
    )

    if crop_filter:
        query = query.filter(
            db.or_(
                CropStateRecord.crop_master.ilike(f"%{crop_filter}%"),
                CropStateRecord.product_name.ilike(f"%{crop_filter}%")
            )
        )
    if zone_filter:
        query = query.filter(CropStateRecord.zone.ilike(f"%{zone_filter}%"))
    if block_filter:
        query = query.filter(CropStateRecord.block_full.ilike(f"%{block_filter}%"))
    if week_filter:
        query = query.filter(CropStateRecord.week.ilike(f"%{week_filter}%"))

    # Summary stats
    total_records = CropStateRecord.query.count()
    active_records = CropStateRecord.query.filter(CropStateRecord.crop_master != 'VACIO').count()
    empty_records = total_records - active_records
    total_std_beds = db.session.query(db.func.sum(CropStateRecord.standard_bed)).filter(CropStateRecord.crop_master != 'VACIO').scalar() or 0.0

    unique_crops = [r[0] for r in db.session.query(CropStateRecord.crop_master).filter(CropStateRecord.crop_master != 'VACIO').distinct().order_by(CropStateRecord.crop_master).all() if r[0]]
    unique_zones = [r[0] for r in db.session.query(CropStateRecord.zone).distinct().order_by(CropStateRecord.zone).all() if r[0]]
    unique_weeks = [r[0] for r in db.session.query(CropStateRecord.week).distinct().order_by(CropStateRecord.week.desc()).all() if r[0]]

    if view_mode == 'segments':
        # Aggregate beds into segments
        all_filtered = query.order_by(CropStateRecord.crop_master, CropStateRecord.block_full, CropStateRecord.suffix, CropStateRecord.real_age).all()
        segment_groups = {}
        for r in all_filtered:
            key = (r.crop_master, r.product_name, r.block_full, r.suffix, r.real_age, r.zone)
            if key not in segment_groups:
                segment_groups[key] = []
            segment_groups[key].append(r)

        segments = []
        for (crop_m, prod_n, block, suffix, age, zone), recs in segment_groups.items():
            bed_nums = [r.bed_num for r in recs]
            bed_range = CalculationEngine.format_bed_range(bed_nums)
            std_sum = sum(r.standard_bed for r in recs)
            variety = list(set([r.variety for r in recs if r.variety]))
            
            # Classification
            crop_obj = CalculationEngine.get_crop_config(crop_m or prod_n)
            stage = crop_obj.classify_age(age) if crop_obj else 'DESCONOCIDO'

            segments.append({
                'crop': crop_m,
                'product': prod_n,
                'variety': ", ".join(variety),
                'block': block,
                'suffix': suffix,
                'real_age': age,
                'stage': stage,
                'zone': zone,
                'bed_range': bed_range,
                'bed_count': len(recs),
                'standard_beds': round(std_sum, 2)
            })

        # Simple pagination for segments
        total_items = len(segments)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_segments = segments[start:end]
        total_pages = (total_items + per_page - 1) // per_page

        return render_template(
            'estado_cultivo/index.html',
            segments=paginated_segments,
            view_mode='segments',
            page=page,
            total_pages=total_pages,
            total_items=total_items,
            total_records=total_records,
            active_records=active_records,
            empty_records=empty_records,
            total_std_beds=round(total_std_beds, 2),
            unique_crops=unique_crops,
            unique_zones=unique_zones,
            unique_weeks=unique_weeks,
            selected_crop=crop_filter,
            selected_zone=zone_filter,
            selected_block=block_filter,
            selected_week=week_filter
        )
    else:
        pagination = query.order_by(CropStateRecord.block_full.asc(), CropStateRecord.bed_num.asc()).paginate(page=page, per_page=per_page, error_out=False)
        return render_template(
            'estado_cultivo/index.html',
            pagination=pagination,
            view_mode='beds',
            total_records=total_records,
            active_records=active_records,
            empty_records=empty_records,
            total_std_beds=round(total_std_beds, 2),
            unique_crops=unique_crops,
            unique_zones=unique_zones,
            unique_weeks=unique_weeks,
            selected_crop=crop_filter,
            selected_zone=zone_filter,
            selected_block=block_filter,
            selected_week=week_filter
        )
