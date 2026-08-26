import math
import json
from app.extensions import db
from app.shared.models import Crop, Product, Litraje, CropStateRecord, AdditionalApplication
from app.shared.utils import get_operator_for_zone, get_toxicological_color_info, is_integer_unit, round_product_amount

class CalculationEngine:

    @staticmethod
    def normalize_crop_name(crop_name: str) -> str:
        if not crop_name:
            return ""
        import unicodedata, re
        n = str(crop_name).strip()
        n = unicodedata.normalize('NFKD', n).encode('ASCII', 'ignore').decode('utf-8')
        n = re.sub(r'[^a-zA-Z0-9]+', '_', n).strip('_').upper()
        return n

    _crops_cache = None
    _crops_cache_time = 0
    _litraje_cache = None
    _litraje_cache_time = 0

    @classmethod
    def get_all_crops(cls):
        import time
        now = time.time()
        if cls._crops_cache is None or (now - cls._crops_cache_time > 60):
            cls._crops_cache = Crop.query.all()
            cls._crops_cache_time = now
        return cls._crops_cache

    @classmethod
    def get_litraje_map(cls):
        import time
        now = time.time()
        if cls._litraje_cache is None or (now - cls._litraje_cache_time > 60):
            all_lits = Litraje.query.all()
            l_map = {}
            for l in all_lits:
                c_clean = cls.normalize_crop_name(l.crop_name)
                l_map[(c_clean, int(round(l.age)))] = l.liters_per_bed
            cls._litraje_cache = l_map
            cls._litraje_cache_time = now
        return cls._litraje_cache

    @classmethod
    def get_crop_config(cls, crop_identifier: str):
        """
        Finds the Crop configuration model by name or alias with tolerant matching using cached crop models.
        """
        if not crop_identifier:
            return None
        crop_id_clean = cls.normalize_crop_name(crop_identifier)
        crops = cls.get_all_crops()
        for c in crops:
            if cls.normalize_crop_name(c.name) == crop_id_clean:
                return c
            for alias in c.aliases:
                alias_clean = cls.normalize_crop_name(alias)
                if alias_clean == crop_id_clean or crop_id_clean in alias_clean or alias_clean in crop_id_clean:
                    return c
        return None

    @classmethod
    def match_records_for_crop(cls, crop_obj, records_query):
        """
        Filters CropStateRecords that belong to the specified crop_obj.
        Excludes VACIO, unclassified or discarded beds.
        """
        if not crop_obj:
            return []

        search_terms = [cls.normalize_crop_name(crop_obj.name)]
        for alias in crop_obj.aliases:
            search_terms.append(cls.normalize_crop_name(alias))

        c_name_u = (crop_obj.name or '').upper()
        if 'HYPERICUM' in c_name_u or 'HYPERYCUM' in c_name_u:
            search_terms.extend(['HYPERICUM', 'HYPERYCUM', 'MAGICAL'])
        elif 'VERONICA' in c_name_u:
            search_terms.extend(['VERONICA', 'VERONICA_SPRAY', 'VERONICA_SPLASH', 'SKYLER'])
        elif 'GYPSOPHILA' in c_name_u or 'GYPSO' in c_name_u:
            search_terms.extend(['GYPSOPHILA', 'XLENCE', 'BILLION_LIGHTS', 'GYPSO'])
        elif 'SOLIDAGO' in c_name_u:
            search_terms.extend(['SOLIDAGO', 'GOLDEN_GLORY_YELLOW'])
        elif 'RUSCUS' in c_name_u:
            search_terms.extend(['RUSCUS'])
        elif 'SUNFLOWER' in c_name_u or 'GIRASOL' in c_name_u:
            search_terms.extend(['SUNFLOWER', 'GIRASOL'])
        elif 'RUMEX' in c_name_u:
            search_terms.extend(['RUMEX'])
        elif 'LYSIMACHIA' in c_name_u:
            search_terms.extend(['LYSIMACHIA'])
        elif 'ASTER' in c_name_u:
            search_terms.extend(['ASTER'])

        search_terms = list(set([cls.normalize_crop_name(s) for s in search_terms if s]))

        matched = []
        for r in records_query:
            if not r.crop_master or r.crop_master.upper() in ('VACIO', 'DESCARTE', 'TUMBAR', 'NAN', 'TOTAL', 'TOTAL_GENERAL'):
                continue

            r_crop_master = cls.normalize_crop_name(r.crop_master)
            r_product = cls.normalize_crop_name(r.product_name or '')
            r_variety = cls.normalize_crop_name(r.variety or '')

            is_match = False
            for term in search_terms:
                if not term:
                    continue
                if (term == r_crop_master or 
                    term == r_product or 
                    term in r_product or 
                    term in r_variety or 
                    term in r_crop_master or
                    r_crop_master in term):
                    is_match = True
                    break
                if r_crop_master in ('PROD_NUEVOS', 'PROD_NUEVO', 'NUEVOS_PROD'):
                    if term in r_product or term in r_variety or r_product in term:
                        is_match = True
                        break

            if is_match:
                matched.append(r)

        return matched

    @classmethod
    def get_liters_per_bed(cls, crop_name: str, age: float) -> tuple[float, bool]:
        """
        Looks up liters per bed from in-memory Litraje table cache for given crop and age.
        """
        if age is None:
            return 0.0, False

        int_age = int(round(age))
        crop_clean = cls.normalize_crop_name(crop_name)
        l_map = cls.get_litraje_map()

        # 1. Direct match
        if (crop_clean, int_age) in l_map:
            return l_map[(crop_clean, int_age)], True

        # 2. Check aliases
        crop_obj = cls.get_crop_config(crop_name)
        if crop_obj:
            candidate_names = [crop_obj.name.upper()] + [a.upper() for a in crop_obj.aliases]
            if 'GYPSOPHILA' in crop_obj.name.upper():
                candidate_names.extend(['XLENCE', 'BILLION LIGHTS', 'GYPSO'])
            elif 'VERONICA' in crop_obj.name.upper():
                candidate_names.extend(['VERONICA', 'VERONICA SPLASH'])

            for c_name in set(candidate_names):
                cn_clean = cls.normalize_crop_name(c_name)
                if (cn_clean, int_age) in l_map:
                    return l_map[(cn_clean, int_age)], True

        # 3. Fallback to closest configured age from cache
        matching_ages = [(k_age, ltr) for (k_crop, k_age), ltr in l_map.items() if k_crop == crop_clean]
        if matching_ages:
            closest = min(matching_ages, key=lambda x: abs(x[0] - int_age))
            return closest[1], True

        return 0.0, False

    @staticmethod
    def format_bed_range(bed_nums: list[int]) -> str:
        """
        Formats bed numbers into clean range, e.g. "Camas 1-11" or "Camas 4-54"
        """
        if not bed_nums:
            return ""
        unique_beds = sorted(list(set(bed_nums)))
        if len(unique_beds) == 1:
            return f"Cama {unique_beds[0]}"

        ranges = []
        start = unique_beds[0]
        prev = unique_beds[0]

        for b in unique_beds[1:]:
            if b == prev + 1:
                prev = b
            else:
                if start == prev:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}-{prev}")
                start = b
                prev = b
        
        if start == prev:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}-{prev}")

        return f"Camas {', '.join(ranges)}"

    @classmethod
    def calculate_round(cls, round_obj, custom_review_segments=None, cached_crop_records=None):
        """
        Calculates application segments, product quantities, assigned operators and toxicological info for a round.
        If custom_review_segments is provided, it uses the agronomist's approved/adjusted segments!
        """
        warnings = []
        segments = []
        product_summary_map = {}

        if not round_obj or not round_obj.items:
            return {
                'segments': [],
                'product_summaries': [],
                'totals': {'total_liters': 0.0, 'total_standard_beds': 0.0, 'total_segments': 0, 'total_beds': 0},
                'warnings': ["La vuelta no tiene productos ni cultivos asignados."]
            }

        # If custom reviewed segments are provided (from agronomist review tab)
        if custom_review_segments is not None and len(custom_review_segments) > 0:
            # Calculate from custom reviewed segments
            total_liters_all = 0.0
            total_std_beds_all = 0.0
            total_beds_count = 0

            for seg in custom_review_segments:
                block_full = seg.get('block_name', '')
                suffix = seg.get('suffix', 'A')
                crop_name = seg.get('crop_name', '')
                variety = seg.get('variety', '')
                stage = seg.get('phenological_stage', 'VEGETATIVO')
                raw_age = seg.get('real_age', '')
                if raw_age is None:
                    real_age = ''
                elif isinstance(raw_age, (int, float)):
                    real_age = int(round(raw_age)) if raw_age == int(round(raw_age)) else raw_age
                else:
                    real_age = str(raw_age).strip()
                    if real_age.endswith('.0'):
                        real_age = real_age[:-2]
                bed_start = int(seg.get('bed_start', 1))
                bed_end = int(seg.get('bed_end', 1))
                bed_count = max(1, bed_end - bed_start + 1)
                standard_beds = round(float(seg.get('standard_beds', 1.0)), 2)
                liters_per_bed = round(float(seg.get('liters_per_bed', 0.0)), 1)
                segment_liters = round(standard_beds * liters_per_bed, 1)
                zone = seg.get('zone', '')
                operator = seg.get('operator') or get_operator_for_zone(zone)
                bed_range_str = seg.get('bed_range', f"Camas {bed_start}-{bed_end}")

                # Retrieve products assigned to this segment
                products_list = seg.get('products', [])
                products_detail = []
                products_summary_text_parts = []

                for it_idx, it in enumerate(products_list):
                    prod_id = it.get('product_id')
                    prod_code = it.get('product_code', 'N/A')
                    comm_name = it.get('commercial_name', prod_code)
                    dose = float(it.get('dose', 0.0) or 0.0)
                    dose_unit = it.get('dose_unit', 'CC')
                    pest = it.get('pest', '')
                    ia = it.get('active_ingredient', '')
                    ct = it.get('toxicological_category', '')
                    color_info = get_toxicological_color_info(ct)

                    product_amount = round_product_amount(segment_liters * dose, dose_unit)

                    products_detail.append({
                        'product_id': prod_id,
                        'product_code': prod_code,
                        'commercial_name': comm_name,
                        'dose': dose,
                        'dose_unit': dose_unit,
                        'product_amount': product_amount,
                        'pest': pest,
                        'active_ingredient': ia,
                        'toxicological_category': ct,
                        'toxicological_color': color_info['name'],
                        'color_info': color_info,
                        'order_in_mix': it_idx
                    })

                    products_summary_text_parts.append(f"{prod_code} ({dose} {dose_unit}/L)")

                    summary_key = (prod_code, dose, dose_unit)
                    if summary_key not in product_summary_map:
                        product_summary_map[summary_key] = {
                            'product_id': prod_id,
                            'product_code': prod_code,
                            'commercial_name': comm_name,
                            'dose': dose,
                            'dose_unit': dose_unit,
                            'pest': pest,
                            'total_required_quantity': 0.0
                        }
                    product_summary_map[summary_key]['total_required_quantity'] += product_amount

                segment_data = {
                    'round_number': round_obj.round_number,
                    'round_name': round_obj.name,
                    'scheduled_day': round_obj.scheduled_day,
                    'scheduled_date': round_obj.scheduled_date,
                    'operator': operator,
                    'zone': zone,
                    'block_name': block_full,
                    'suffix': suffix,
                    'crop_name': crop_name,
                    'variety': variety,
                    'phenological_stage': stage,
                    'real_age': real_age,
                    'bed_start': bed_start,
                    'bed_end': bed_end,
                    'bed_range': bed_range_str,
                    'bed_count': bed_count,
                    'standard_beds': standard_beds,
                    'liters_per_bed': liters_per_bed,
                    'total_liters': segment_liters,
                    'products': products_list,
                    'products_detail': products_detail,
                    'products_summary_text': ", ".join(products_summary_text_parts),
                    'is_additional': seg.get('is_additional', False)
                }

                segments.append(segment_data)
                total_liters_all += segment_liters
                total_std_beds_all += standard_beds
                total_beds_count += bed_count

            # Sort segments sequentially: ZONA -> BLOQUE (natural) -> SUFIJO -> CAMA INICIO -> CAMA FIN
            import re
            def get_seg_sort_key(s):
                b_name = s.get('block_name') or ''
                digits = re.findall(r'\d+', b_name)
                b_num = int(digits[0]) if digits else 99999
                return (
                    s.get('zone') or '',
                    b_num,
                    b_name,
                    s.get('suffix') or 'A',
                    int(s.get('bed_start') or 0),
                    int(s.get('bed_end') or 0)
                )

            segments.sort(key=get_seg_sort_key)

            product_summaries = list(product_summary_map.values())
            for ps in product_summaries:
                ps['total_required_quantity'] = round_product_amount(ps['total_required_quantity'], ps.get('dose_unit', 'CC'))
            product_summaries.sort(key=lambda p: p['product_code'])

            return {
                'segments': segments,
                'product_summaries': product_summaries,
                'totals': {
                    'total_liters': round(total_liters_all, 1),
                    'total_standard_beds': round(total_std_beds_all, 2),
                    'total_segments': len(segments),
                    'total_beds': total_beds_count
                },
                'warnings': warnings
            }

        # Otherwise calculate from database crop state (filtered by rotation week to prevent multi-week duplication)
        if cached_crop_records is not None:
            all_active_records = cached_crop_records
        else:
            rot_week = round_obj.rotation.week.strip() if (round_obj and round_obj.rotation and round_obj.rotation.week) else None
            available_weeks = [w[0] for w in db.session.query(CropStateRecord.week).distinct().order_by(CropStateRecord.week.desc()).all() if w[0]]

            filter_week = None
            if rot_week:
                for aw in available_weeks:
                    if aw.strip() == rot_week or rot_week in aw or aw in rot_week:
                        filter_week = aw
                        break

            if not filter_week and available_weeks:
                filter_week = available_weeks[0]

            rec_query = CropStateRecord.query.filter(
                CropStateRecord.crop_master.isnot(None),
                ~CropStateRecord.crop_master.in_(['VACIO', 'DESCARTE', 'TUMBAR', 'NAN', 'TOTAL', 'TOTAL_GENERAL'])
            )
            if filter_week:
                rec_query = rec_query.filter(CropStateRecord.week == filter_week)

            all_active_records = rec_query.all()
            for r in all_active_records:
                if r.real_age is None or r.real_age < 0:
                    r.real_age = 10.0

        mixes_by_crop_stage = {}
        for it_idx, item in enumerate(sorted(round_obj.items, key=lambda x: x.order_index)):
            key = (item.crop_name.strip(), item.phenological_stage.strip().upper())
            if key not in mixes_by_crop_stage:
                mixes_by_crop_stage[key] = []
            mixes_by_crop_stage[key].append((it_idx, item))

        total_liters_all = 0.0
        total_std_beds_all = 0.0
        total_beds_count = 0

        for (crop_name, stage), items_with_idx in mixes_by_crop_stage.items():
            crop_obj = cls.get_crop_config(crop_name)
            if not crop_obj:
                # Dynamic fallback object
                crop_obj = Crop(
                    name=crop_name.strip(),
                    veg_min_age=0,
                    veg_max_age=9,
                    prod_min_age=10,
                    prod_max_age=999
                )
                crop_obj.aliases = [crop_name.strip()]

            crop_records = cls.match_records_for_crop(crop_obj, all_active_records)
            if not crop_records:
                continue

            stage_records = []
            for r in crop_records:
                classified_stage = crop_obj.classify_age(r.real_age)
                if classified_stage == stage:
                    stage_records.append(r)

            if not stage_records:
                continue

            segment_groups = {}
            for r in stage_records:
                seg_key = (r.block_full.strip(), r.suffix.strip(), r.real_age, (r.zone or '').strip())
                if seg_key not in segment_groups:
                    segment_groups[seg_key] = []
                segment_groups[seg_key].append(r)

            for (block_full, suffix, real_age, zone), recs in segment_groups.items():
                bed_nums = [r.bed_num for r in recs]
                bed_min = min(bed_nums)
                bed_max = max(bed_nums)
                bed_range_str = cls.format_bed_range(bed_nums)
                bed_count = len(recs)
                total_std_beds = sum(r.standard_bed for r in recs)

                liters_per_bed, lit_found = cls.get_liters_per_bed(crop_name, real_age)
                segment_liters = round(total_std_beds * liters_per_bed, 1)

                operator = get_operator_for_zone(zone)
                products_detail = []
                products_summary_text_parts = []

                for it_idx, it in items_with_idx:
                    prod = it.product
                    dose = it.dose_applied or 0.0
                    dose_unit = it.dose_unit or (prod.unit if prod else 'CC')
                    product_amount = round_product_amount(segment_liters * dose, dose_unit)
                    
                    prod_code = prod.code if prod else 'N/A'
                    comm_name = prod.commercial_name if (prod and prod.commercial_name) else prod_code
                    pest = prod.pest if prod else ''
                    ia = prod.active_ingredient if prod else ''
                    ct = prod.toxicological_category if prod else ''
                    color_info = get_toxicological_color_info(ct)

                    products_detail.append({
                        'product_id': prod.id if prod else None,
                        'product_code': prod_code,
                        'commercial_name': comm_name,
                        'dose': dose,
                        'dose_unit': dose_unit,
                        'product_amount': product_amount,
                        'pest': pest,
                        'active_ingredient': ia,
                        'toxicological_category': ct,
                        'toxicological_color': color_info['name'],
                        'color_info': color_info,
                        'order_in_mix': it_idx
                    })

                    products_summary_text_parts.append(f"{prod_code} ({dose} {dose_unit}/L)")

                    summary_key = (prod_code, dose, dose_unit)
                    if summary_key not in product_summary_map:
                        product_summary_map[summary_key] = {
                            'product_id': prod.id if prod else None,
                            'product_code': prod_code,
                            'commercial_name': comm_name,
                            'dose': dose,
                            'dose_unit': dose_unit,
                            'pest': pest,
                            'total_required_quantity': 0.0
                        }
                    product_summary_map[summary_key]['total_required_quantity'] += product_amount

                varieties = list(set([r.variety for r in recs if r.variety]))
                variety_str = ", ".join(varieties) if varieties else crop_name

                segment_data = {
                    'round_number': round_obj.round_number,
                    'round_name': round_obj.name,
                    'scheduled_day': round_obj.scheduled_day,
                    'scheduled_date': round_obj.scheduled_date,
                    'operator': operator,
                    'zone': zone,
                    'block_name': block_full,
                    'suffix': suffix,
                    'crop_name': crop_name,
                    'variety': variety_str,
                    'phenological_stage': stage,
                    'real_age': real_age,
                    'bed_start': bed_min,
                    'bed_end': bed_max,
                    'bed_range': bed_range_str,
                    'bed_count': bed_count,
                    'standard_beds': round(total_std_beds, 2),
                    'liters_per_bed': round(liters_per_bed, 1),
                    'total_liters': segment_liters,
                    'products': [
                        {
                            'product_id': p['product_id'],
                            'product_code': p['product_code'],
                            'commercial_name': p['commercial_name'],
                            'dose': p['dose'],
                            'dose_unit': p['dose_unit'],
                            'pest': p['pest'],
                            'active_ingredient': p['active_ingredient'],
                            'toxicological_category': p['toxicological_category']
                        } for p in products_detail
                    ],
                    'products_detail': products_detail,
                    'products_summary_text': ", ".join(products_summary_text_parts),
                    'is_additional': False
                }

                segments.append(segment_data)
                total_liters_all += segment_liters
                total_std_beds_all += total_std_beds
                total_beds_count += bed_count

        # Sort segments sequentially: ZONA -> BLOQUE (natural) -> SUFIJO -> CAMA INICIO -> CAMA FIN
        import re
        def get_seg_sort_key_db(s):
            b_name = s.get('block_name') or ''
            digits = re.findall(r'\d+', b_name)
            b_num = int(digits[0]) if digits else 99999
            return (
                s.get('zone') or '',
                b_num,
                b_name,
                s.get('suffix') or 'A',
                int(s.get('bed_start') or 0),
                int(s.get('bed_end') or 0)
            )

        segments.sort(key=get_seg_sort_key_db)

        product_summaries = list(product_summary_map.values())
        for ps in product_summaries:
            ps['total_required_quantity'] = round_product_amount(ps['total_required_quantity'], ps.get('dose_unit', 'CC'))
        product_summaries.sort(key=lambda p: p['product_code'])

        return {
            'segments': segments,
            'product_summaries': product_summaries,
            'totals': {
                'total_liters': round(total_liters_all, 1),
                'total_standard_beds': round(total_std_beds_all, 2),
                'total_segments': len(segments),
                'total_beds': total_beds_count
            },
            'warnings': list(set(warnings))
        }
