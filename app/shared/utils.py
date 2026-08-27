"""
Shared utility functions, local timezone helpers, number formatters,
operator zone assignment, and toxicological categorization.
"""

import datetime
from zoneinfo import ZoneInfo

# Local Timezone for Ecuador / Colombia (UTC-5)
LOCAL_TZ = ZoneInfo("America/Guayaquil")

def get_local_now() -> datetime.datetime:
    """
    Returns the current local datetime as a naive datetime in UTC-5 (e.g. 15:12:00).
    Ensures databases like SQLite and PostgreSQL store the exact local farm time.
    """
    return datetime.datetime.now(LOCAL_TZ).replace(tzinfo=None)

def format_local_datetime(dt, fmt="%Y-%m-%d %H:%M") -> str:
    """Safely formats a datetime object in local time."""
    if not dt:
        return ""
    return dt.strftime(fmt)

def is_integer_unit(unit: str) -> bool:
    """
    Returns True if the unit of measurement is counted/weighed in whole units
    without decimals (CC, G, GR, ML, PST, GRAMOS, etc.) because field scales
    cannot measure sub-decimal fractions of CC/GR.
    """
    if not unit:
        return True
    u = str(unit).strip().upper()
    return u in ['CC', 'G', 'GR', 'ML', 'PST', 'PST.', 'GRAMOS', 'CENTIMETROS', 'CM3', 'UNIDAD', 'UNIDADES', 'TAB', 'TABLETA', 'UND', 'UN']

def safe_float(val, default=0.0) -> float:
    """
    Safely converts a value (string, None, int, float, localized number with comma) to a float.
    Never raises an exception; returns `default` on error or empty string.
    """
    if val is None:
        return float(default)
    if isinstance(val, (int, float)):
        import math
        if math.isnan(val) or math.isinf(val):
            return float(default)
        return float(val)
    try:
        s = str(val).strip().replace(',', '.')
        if not s or s.lower() in ('none', 'nan', 'null', 'undefined'):
            return float(default)
        return float(s)
    except (ValueError, TypeError):
        return float(default)

def safe_int(val, default=0) -> int:
    """
    Safely converts a value to an integer (handling strings like '1.0', '1,0', None, NaN).
    Never raises an exception; returns `default` on error or empty string.
    """
    if val is None:
        return int(default)
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        import math
        if math.isnan(val) or math.isinf(val):
            return int(default)
        return int(round(val))
    try:
        s = str(val).strip().replace(',', '.')
        if not s or s.lower() in ('none', 'nan', 'null', 'undefined'):
            return int(default)
        return int(round(float(s)))
    except (ValueError, TypeError):
        return int(default)

def format_product_amount(amount: float, unit: str) -> str:
    """
    Business Rule for Product Quantities:
    - CC, G, GR, ML, PST: 0 decimals (integers, e.g. 150 CC, 25 GR)
    - LT, KG, L, K: 1 decimal (e.g. 2.5 LT, 1.2 KG)
    """
    if amount is None:
        return "0"
    val = safe_float(amount, default=0.0)

    if is_integer_unit(unit):
        return f"{int(round(val)):,}"
    else:
        u = str(unit or '').strip().upper()
        if u in ['LT', 'KG', 'L', 'K', 'LITROS', 'KILOS']:
            return f"{val:.1f}"
        else:
            return f"{int(round(val)) if val == int(round(val)) else round(val, 1):,}"

def round_product_amount(amount: float, unit: str) -> float:
    """
    Rounds product amount according to farm measurement capabilities:
    - CC, G, GR, ML, PST: exact integer (0 decimals)
    - LT, KG, L, K: 1 decimal (or 2 if smaller)
    """
    if amount is None:
        return 0.0
    val = safe_float(amount, default=0.0)

    if is_integer_unit(unit):
        return float(int(round(val)))
    else:
        return round(val, 2)

def is_liquid_unit(unit: str) -> bool:
    """
    Returns True if the unit represents liquid volumes (CC, ML, LT, L, LITROS, CENTIMETROS, CM3).
    """
    if not unit:
        return True
    u = str(unit).strip().upper()
    return u in ['CC', 'ML', 'LT', 'L', 'LITROS', 'CENTIMETROS', 'CM3', 'C.C.', 'CC.']

def is_solid_unit(unit: str) -> bool:
    """
    Returns True if the unit represents solid weights or item units (G, GR, GRAMOS, KG, K, KILOS, PST, PST., TAB, TABLETA, UNIDAD, UND).
    """
    if not unit:
        return False
    u = str(unit).strip().upper()
    return u in ['G', 'GR', 'GRAMOS', 'KG', 'K', 'KILOS', 'PST', 'PST.', 'TAB', 'TABLETA', 'UNIDAD', 'UNIDADES', 'UND', 'UN']

def format_age(age) -> str:
    """Formats crop real age with 0 decimals (integer weeks)."""
    if age is None or age == '':
        return "-"
    try:
        return str(int(round(float(age))))
    except (ValueError, TypeError):
        return str(age)

# Exact Zone -> Operator Mapping:
# ZONA 1, 2 Y 5: RICHARD CAÑAR
# ZONA 4, STA TERESA 1, 2, 3, 4: NELSON PIEDRA
# PALMERAS 1, 2, 3: LUIS BAUTISTA
# ZONA 3: JORGE MEDINA
# VIRGINIA: CRISTOBAL GOMEZ
def get_operator_for_zone(zone_name: str) -> str:
    if not zone_name:
        return "RICHARD CAÑAR"
    z = zone_name.strip().upper().replace(" ", "")
    
    if any(k in z for k in ["ZONA1", "ZONA2", "ZONA5", "Z1", "Z2", "Z5"]):
        return "RICHARD CAÑAR"
    elif any(k in z for k in ["ZONA4", "Z4", "STATERESA", "SANTA TERESA", "TERESA"]):
        return "NELSON PIEDRA"
    elif any(k in z for k in ["PALMERA", "PALMERAS"]):
        return "LUIS BAUTISTA"
    elif any(k in z for k in ["ZONA3", "Z3"]):
        return "JORGE MEDINA"
    elif any(k in z for k in ["VIRGINIA"]):
        return "CRISTOBAL GOMEZ"
    else:
        return "RICHARD CAÑAR"

def get_toxicological_color_info(cat: str) -> dict:
    """
    Returns toxicological color info:
    I -> ROJO
    II -> AMARILLO
    III -> AZUL
    IV -> VERDE
    N/A or empty -> VACÍO
    """
    if not cat:
        return {'name': '', 'bg': 'transparent', 'text': '#000000', 'border': '#cccccc', 'label': ''}
    c = str(cat).strip().upper()
    if c in ['I', '1', 'IA', 'IB']:
        return {'name': 'ROJO', 'bg': '#ef4444', 'text': '#ffffff', 'border': '#b91c1c', 'label': 'I - Rojo'}
    elif c in ['II', '2']:
        return {'name': 'AMARILLO', 'bg': '#eab308', 'text': '#000000', 'border': '#ca8a04', 'label': 'II - Amarillo'}
    elif c in ['III', '3']:
        return {'name': 'AZUL', 'bg': '#3b82f6', 'text': '#ffffff', 'border': '#1d4ed8', 'label': 'III - Azul'}
    elif c in ['IV', '4']:
        return {'name': 'VERDE', 'bg': '#22c55e', 'text': '#ffffff', 'border': '#15803d', 'label': 'IV - Verde'}
    else:
        return {'name': '', 'bg': 'transparent', 'text': '#000000', 'border': '#cccccc', 'label': c}

def get_crop_category(crop_name: str, crop_obj=None) -> str:
    """
    Returns the farm operational printing and warehouse weighing group:
    - 'GYPSOPHILA': Gypsophila, Xlence, Billion Lights, etc.
    - 'PRODUCTOS_NUEVOS': Variedades / Productos Nuevos (Solidago, Verónica, Hypericum, Sunflower, Ruscus, Rumex, etc.)
    - 'PIV': Propagación / Invernadero Vegetativo / PIV
    """
    if crop_obj and getattr(crop_obj, 'category', None):
        return crop_obj.category

    if not crop_name:
        return 'PRODUCTOS_NUEVOS'

    cn = str(crop_name).strip().upper()

    if any(k in cn for k in ['GYPSO', 'GYPSOPHILA', 'XLENCE', 'BILLION']):
        return 'GYPSOPHILA'
    elif any(k in cn for k in ['PIV', 'PROPAGACION', 'PROPAGACIÓN', 'ENRAIZ', 'INVERNADERO']):
        return 'PIV'
    else:
        return 'PRODUCTOS_NUEVOS'

