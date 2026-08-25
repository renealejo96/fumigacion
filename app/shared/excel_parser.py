import io
import pandas as pd
import numpy as np
from app.shared.normalizer import ColumnMapper, normalize_text

class ExcelParserService:

    @staticmethod
    def parse_products_excel(file_or_path):
        """
        Parses 'productos y dosis.xlsx'.
        Returns dict with:
        - success: bool
        - data: list of dicts with cleaned product fields
        - total_rows: int
        - errors: list of warnings/errors
        - preview: list of dicts (first 10 rows)
        """
        errors = []
        try:
            # Read sheet (Hoja1 or first sheet)
            xls = pd.ExcelFile(file_or_path)
            sheet_name = 'Hoja1' if 'Hoja1' in xls.sheet_names else xls.sheet_names[0]
            df = pd.read_excel(xls, sheet_name=sheet_name)
            
            # Map columns
            df, col_map = ColumnMapper.map_dataframe_columns(df, ColumnMapper.PRODUCT_ALIASES)
            
            if 'producto' not in df.columns:
                return {
                    'success': False,
                    'error': "No se encontró la columna requerida 'PRODUCTO' en el archivo.",
                    'columns_found': df.columns.tolist()
                }

            cleaned_products = []
            for idx, row in df.iterrows():
                code = str(row['producto']).strip() if pd.notna(row.get('producto')) else ''
                if not code or code.upper() == 'NAN':
                    continue

                comm_name = str(row.get('producto_comercial', '')).strip() if pd.notna(row.get('producto_comercial')) else code
                um = str(row.get('um', 'CC')).strip().upper() if pd.notna(row.get('um')) else 'CC'
                
                # Dosis fumi
                dose_fumi = None
                if 'dosis_fumi' in row and pd.notna(row['dosis_fumi']):
                    try:
                        dose_fumi = float(row['dosis_fumi'])
                    except (ValueError, TypeError):
                        dose_fumi = None
                
                # Dosis drench
                dose_drench = None
                if 'dosis_drench' in row and pd.notna(row['dosis_drench']):
                    try:
                        dose_drench = float(row['dosis_drench'])
                    except (ValueError, TypeError):
                        dose_drench = None

                pest = str(row.get('plaga', '')).strip() if pd.notna(row.get('plaga')) else ''
                ia = str(row.get('ingrediente_activo', '')).strip() if pd.notna(row.get('ingrediente_activo')) else ''
                cat_tox = str(row.get('categoria_toxicologica', '')).strip() if pd.notna(row.get('categoria_toxicologica')) else ''

                cleaned_products.append({
                    'code': code,
                    'commercial_name': comm_name,
                    'unit': um,
                    'dose_fumigation': dose_fumi,
                    'dose_drench': dose_drench,
                    'pest': pest,
                    'active_ingredient': ia,
                    'toxicological_category': cat_tox,
                    'is_active': True
                })

            return {
                'success': True,
                'total_rows': len(cleaned_products),
                'data': cleaned_products,
                'preview': cleaned_products[:15],
                'errors': errors,
                'sheet_name': sheet_name
            }
        except Exception as e:
            return {'success': False, 'error': f"Error al procesar archivo de productos: {str(e)}"}

    @staticmethod
    def parse_litrajes_excel(file_or_path):
        """
        Parses 'litrajes.xlsx'.
        Returns dict with:
        - success: bool
        - data: list of dicts with crop, age, liters_per_bed
        - total_rows: int
        - preview: list of dicts
        """
        errors = []
        try:
            xls = pd.ExcelFile(file_or_path)
            sheet_name = 'Hoja1' if 'Hoja1' in xls.sheet_names else xls.sheet_names[0]
            df = pd.read_excel(xls, sheet_name=sheet_name)
            
            df, col_map = ColumnMapper.map_dataframe_columns(df, ColumnMapper.LITRAJE_ALIASES)
            
            req_cols = ['cultivo', 'edades', 'litrajes']
            missing = [c for c in req_cols if c not in df.columns]
            if missing:
                return {
                    'success': False,
                    'error': f"Faltan columnas requeridas en el archivo de litrajes: {missing}",
                    'columns_found': df.columns.tolist()
                }

            cleaned_litrajes = []
            for idx, row in df.iterrows():
                crop = str(row['cultivo']).strip().upper() if pd.notna(row.get('cultivo')) else ''
                if not crop or crop == 'NAN':
                    continue

                try:
                    age = int(round(float(row['edades'])))
                except (ValueError, TypeError):
                    continue

                try:
                    liters = float(row['litrajes'])
                except (ValueError, TypeError):
                    liters = 0.0

                cleaned_litrajes.append({
                    'crop_name': crop,
                    'age': age,
                    'liters_per_bed': liters
                })

            return {
                'success': True,
                'total_rows': len(cleaned_litrajes),
                'data': cleaned_litrajes,
                'preview': cleaned_litrajes[:15],
                'errors': errors,
                'sheet_name': sheet_name
            }
        except Exception as e:
            return {'success': False, 'error': f"Error al procesar archivo de litrajes: {str(e)}"}

    @staticmethod
    def parse_crop_state_excel(file_or_path, header_row=4, sheet_name='DATOS'):
        """
        Parses 'Estado Cultivo PYGAN 2026-33.xlsx'.
        Header begins at row index 4 (5th line in Excel).
        Returns dict with:
        - success: bool
        - data: list of cleaned bed records
        - summary: counts by crop, zone, total standard beds
        - preview: sample rows
        """
        errors = []
        try:
            xls = pd.ExcelFile(file_or_path)
            
            target_sheet = sheet_name if sheet_name in xls.sheet_names else ('DATOS' if 'DATOS' in xls.sheet_names else xls.sheet_names[0])
            
            # Read from specified header row
            df = pd.read_excel(xls, sheet_name=target_sheet, header=header_row)
            
            df, col_map = ColumnMapper.map_dataframe_columns(df, ColumnMapper.CROP_STATE_ALIASES)
            
            # Ensure essential columns exist
            if 'bloques2' not in df.columns:
                # Try finding any column with 'bloq'
                bloq_cols = [c for c in df.columns if 'bloq' in str(c).lower()]
                if bloq_cols:
                    df['bloques2'] = df[bloq_cols[0]]
                else:
                    return {'success': False, 'error': "No se encontró columna para Bloques (BLOQUES2)."}

            cleaned_records = []
            crops_counter = {}
            zones_counter = {}
            total_std_beds = 0.0

            for idx, row in df.iterrows():
                block_full = str(row.get('bloques2', '')).strip() if pd.notna(row.get('bloques2')) else ''
                if not block_full or block_full.upper() in ('NAN', 'TOTAL', 'BLOQUES2'):
                    continue

                # Block num
                block_num = str(row.get('blq', '')).strip() if pd.notna(row.get('blq')) else ''
                if not block_num or block_num == 'nan':
                    block_num = block_full.replace('BL', '').replace('BLQ', '').strip()

                # Bed number
                bed_val = row.get('cama')
                try:
                    bed_num = int(float(bed_val))
                except (ValueError, TypeError):
                    bed_num = 1

                # Suffix
                suffix = str(row.get('sufijo', 'A')).strip().upper() if pd.notna(row.get('sufijo')) else 'A'
                if not suffix or suffix == 'NAN':
                    suffix = 'A'

                # Crop master & Product
                crop_master = str(row.get('producto_maestro', '')).strip().upper() if pd.notna(row.get('producto_maestro')) else ''
                product_name = str(row.get('producto', '')).strip().upper() if pd.notna(row.get('producto')) else crop_master
                variety = str(row.get('variedades_elite', '')).strip().upper() if pd.notna(row.get('variedades_elite')) else ''
                zone = str(row.get('zona', '')).strip().upper() if pd.notna(row.get('zona')) else ''
                status_raw = str(row.get('estado', '')).strip().upper() if pd.notna(row.get('estado')) else ''

                # Standard bed
                std_bed = 1.0
                if 'cama_estandar' in row and pd.notna(row['cama_estandar']):
                    try:
                        std_bed = float(row['cama_estandar'])
                    except (ValueError, TypeError):
                        std_bed = 1.0

                # Real age
                real_age = None
                if 'edad_real' in row and pd.notna(row['edad_real']):
                    try:
                        real_age = float(row['edad_real'])
                    except (ValueError, TypeError):
                        real_age = None

                cleaned_records.append({
                    'block_full': block_full,
                    'block_num': block_num,
                    'bed_num': bed_num,
                    'suffix': suffix,
                    'crop_master': crop_master,
                    'product_name': product_name,
                    'variety': variety,
                    'standard_bed': std_bed,
                    'zone': zone,
                    'real_age': real_age,
                    'status_raw': status_raw
                })

                if crop_master:
                    crops_counter[crop_master] = crops_counter.get(crop_master, 0) + 1
                if zone:
                    zones_counter[zone] = zones_counter.get(zone, 0) + 1
                total_std_beds += std_bed

            return {
                'success': True,
                'total_rows': len(cleaned_records),
                'data': cleaned_records,
                'preview': cleaned_records[:20],
                'summary': {
                    'total_records': len(cleaned_records),
                    'total_standard_beds': round(total_std_beds, 2),
                    'crops_count': crops_counter,
                    'zones_count': zones_counter
                },
                'sheet_name': target_sheet,
                'errors': errors
            }
        except Exception as e:
            return {'success': False, 'error': f"Error al procesar Estado de Cultivo: {str(e)}"}
