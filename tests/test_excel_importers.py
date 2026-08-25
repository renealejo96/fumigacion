import unittest
from pathlib import Path
from app.shared.excel_parser import ExcelParserService

BASE_DIR = Path(__file__).resolve().parent.parent

class TestExcelImporters(unittest.TestCase):

    def test_parse_products_excel(self):
        prod_path = BASE_DIR / 'productos y dosis.xlsx'
        if prod_path.exists():
            res = ExcelParserService.parse_products_excel(str(prod_path))
            self.assertTrue(res['success'])
            self.assertGreater(res['total_rows'], 0)
            self.assertTrue(any(p['code'] == 'ACARAMIK' for p in res['data']))

    def test_parse_litrajes_excel(self):
        lit_path = BASE_DIR / 'litrajes.xlsx'
        if lit_path.exists():
            res = ExcelParserService.parse_litrajes_excel(str(lit_path))
            self.assertTrue(res['success'])
            self.assertGreater(res['total_rows'], 0)
            self.assertTrue(any(l['crop_name'] == 'HYPERICUM' for l in res['data']))

    def test_parse_crop_state_excel(self):
        ec_path = BASE_DIR / 'Estado Cultivo PYGAN 2026-33.xlsx'
        if ec_path.exists():
            res = ExcelParserService.parse_crop_state_excel(str(ec_path), header_row=4, sheet_name='DATOS')
            self.assertTrue(res['success'])
            self.assertGreater(res['total_rows'], 0)
            self.assertGreater(res['summary']['total_standard_beds'], 0)

if __name__ == '__main__':
    unittest.main()
