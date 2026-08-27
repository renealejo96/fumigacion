import os
from flask import Flask, render_template, session, g
from app.config import Config
from app.extensions import db
from app.shared.utils import (
    format_product_amount, format_age, format_local_datetime, 
    is_liquid_unit, is_solid_unit, safe_float, safe_int
)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)

    # Concurrency optimization: Enable WAL mode & busy timeout if SQLite is used
    if 'sqlite' in str(app.config.get('SQLALCHEMY_DATABASE_URI', '')):
        from sqlalchemy import event
        from sqlalchemy.engine import Engine

        @event.listens_for(Engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()
            except Exception:
                pass

    # Register Jinja2 filters
    @app.template_filter('format_number')
    def filter_format_number(val, decimals=2):
        if val is None:
            return "0"
        try:
            f = safe_float(val, default=0.0)
            if decimals == 0:
                return f"{int(round(f)):,}"
            return f"{f:,.{decimals}f}"
        except (ValueError, TypeError):
            return str(val)

    @app.template_filter('format_product')
    def filter_format_product(amount, unit):
        return format_product_amount(amount, unit)

    @app.template_filter('format_age')
    def filter_format_age(age):
        return format_age(age)

    @app.template_filter('format_local_datetime')
    def filter_format_local_datetime(dt, fmt="%Y-%m-%d %H:%M"):
        return format_local_datetime(dt, fmt)

    @app.template_filter('is_liquid')
    def filter_is_liquid(unit):
        return is_liquid_unit(unit)

    @app.template_filter('is_solid')
    def filter_is_solid(unit):
        return is_solid_unit(unit)

    @app.template_filter('crop_category')
    def filter_crop_category(crop_name):
        from app.shared.utils import get_crop_category
        return get_crop_category(crop_name)

    # Safe dynamic column migrations
    with app.app_context():
        try:
            from sqlalchemy import text
            db.session.execute(text("ALTER TABLE crops ADD COLUMN IF NOT EXISTS category VARCHAR(50) DEFAULT 'PRODUCTOS_NUEVOS'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
            try:
                db.session.execute(text("ALTER TABLE crops ADD COLUMN category VARCHAR(50) DEFAULT 'PRODUCTOS_NUEVOS'"))
                db.session.commit()
            except Exception:
                db.session.rollback()

    # Register blueprints
    from app.modules.auth.routes import auth_bp
    from app.modules.orden_compra.routes import orden_compra_bp
    from app.modules.fumigacion.routes import fumigacion_bp
    from app.modules.drench.routes import drench_bp
    from app.modules.trichos.routes import trichos_bp
    from app.modules.desinfecciones.routes import desinfecciones_bp
    from app.modules.productos.routes import productos_bp
    from app.modules.cultivos.routes import cultivos_bp
    from app.modules.litrajes.routes import litrajes_bp
    from app.modules.estado_cultivo.routes import estado_cultivo_bp
    from app.modules.importador.routes import importador_bp
    from app.modules.bodega.routes import bodega_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(orden_compra_bp, url_prefix='/orden-compra')
    app.register_blueprint(fumigacion_bp, url_prefix='/fumigacion')
    app.register_blueprint(bodega_bp, url_prefix='/bodega')
    app.register_blueprint(drench_bp, url_prefix='/drench')
    app.register_blueprint(trichos_bp, url_prefix='/trichos')
    app.register_blueprint(desinfecciones_bp, url_prefix='/desinfecciones')
    app.register_blueprint(productos_bp, url_prefix='/productos')
    app.register_blueprint(cultivos_bp, url_prefix='/cultivos')
    app.register_blueprint(litrajes_bp, url_prefix='/litrajes')
    app.register_blueprint(estado_cultivo_bp, url_prefix='/estado-cultivo')
    app.register_blueprint(importador_bp, url_prefix='/importador')

    # Global user context processor
    @app.context_processor
    def inject_user():
        from app.shared.models import User
        user_id = session.get('user_id')
        current_user = User.query.get(user_id) if user_id else None
        return {'current_user': current_user}

    # Force login by default for all application routes
    @app.before_request
    def check_authenticated_user():
        from flask import request, redirect, url_for
        if request.endpoint:
            if request.endpoint.startswith('static') or request.endpoint in ['auth.login', 'auth.logout']:
                return None
        
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))

    # Main dashboard route
    @app.route('/')
    def dashboard():
        from flask import request, redirect, url_for
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))

        from app.shared.models import (
            Crop, Product, CropStateRecord, 
            Rotation, RotationRound, RotationRoundItem, 
            FumigationOrder
        )
        crops_count = Crop.query.filter_by(is_active=True).count()
        products_count = Product.query.filter_by(is_active=True).count()
        beds_count = CropStateRecord.query.count()
        rotations_count = Rotation.query.count()
        orders_count = FumigationOrder.query.count()

        all_rotations = Rotation.query.options(
            db.joinedload(Rotation.rounds).joinedload(RotationRound.items).joinedload(RotationRoundItem.product)
        ).order_by(Rotation.week.desc(), Rotation.version.desc()).all()
        
        # Group rotations by week with full details of rounds and chemicals
        weekly_rotations_data = {}
        for rot in all_rotations:
            w = rot.week
            if w not in weekly_rotations_data:
                weekly_rotations_data[w] = []
            
            rounds_info = []
            for rd in sorted(rot.rounds, key=lambda x: x.round_number):
                formula_groups = {}
                for it in sorted(rd.items, key=lambda x: x.order_index):
                    crop_k = it.crop_name or 'Cultivo'
                    stage_k = it.phenological_stage or 'GENERAL'
                    grp_k = f"{crop_k} ({stage_k})"
                    if grp_k not in formula_groups:
                        formula_groups[grp_k] = []
                    
                    p_code = it.product.code if it.product else f"Prod #{it.product_id}"
                    p_name = it.product.commercial_name if (it.product and it.product.commercial_name) else p_code
                    formula_groups[grp_k].append({
                        'code': p_code,
                        'name': p_name,
                        'dose': it.dose_applied,
                        'unit': it.dose_unit or (it.product.unit if it.product else 'CC')
                    })
                
                distinct_formulas = []
                for grp_k, p_list in formula_groups.items():
                    distinct_formulas.append({
                        'label': grp_k,
                        'products': p_list
                    })

                rounds_info.append({
                    'round_number': rd.round_number,
                    'name': rd.name,
                    'day': rd.scheduled_day,
                    'formulas': distinct_formulas,
                    'total_items': len(rd.items)
                })

            weekly_rotations_data[w].append({
                'id': rot.id,
                'week': rot.week,
                'version': rot.version,
                'title': rot.title or f"Rotación Semana {rot.week}",
                'status': rot.status,
                'created_by': rot.created_by,
                'approved_by': rot.approved_by,
                'created_at': rot.created_at,
                'approved_at': rot.approved_at,
                'notes': rot.notes,
                'rounds': rounds_info
            })

        weeks_list = list(weekly_rotations_data.keys())
        selected_week = request.args.get('week')
        if not selected_week and weeks_list:
            selected_week = weeks_list[0]

        recent_orders = FumigationOrder.query.order_by(FumigationOrder.created_at.desc()).limit(8).all()

        return render_template(
            'dashboard.html',
            crops_count=crops_count,
            products_count=products_count,
            beds_count=beds_count,
            rotations_count=rotations_count,
            orders_count=orders_count,
            weekly_rotations_data=weekly_rotations_data,
            weeks_list=weeks_list,
            selected_week=selected_week,
            recent_orders=recent_orders
        )

    return app
