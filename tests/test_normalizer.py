import unittest
from app.shared.normalizer import normalize_text, ColumnMapper

class TestNormalizer(unittest.TestCase):

    def test_normalize_text_accents_and_case(self):
        self.assertEqual(normalize_text("EDAD REAL"), "edad_real")
        self.assertEqual(normalize_text("Edad Real"), "edad_real")
        self.assertEqual(normalize_text("edad_real"), "edad_real")
        self.assertEqual(normalize_text("  EDAD_REAL  "), "edad_real")
        self.assertEqual(normalize_text("CAMA ESTÁNDAR"), "cama_estandar")
        self.assertEqual(normalize_text("CATEGORÍA TOXICOLÓGICA"), "categoria_toxicologica")
        self.assertEqual(normalize_text("# Cama"), "cama")

    def test_column_alias_matching(self):
        # Product aliases
        self.assertEqual(ColumnMapper.match_column("PRODUCTO", ColumnMapper.PRODUCT_ALIASES), "producto")
        self.assertEqual(ColumnMapper.match_column("PRODUCTO COMERCIAL", ColumnMapper.PRODUCT_ALIASES), "producto_comercial")
        self.assertEqual(ColumnMapper.match_column("DOSIS FUMI", ColumnMapper.PRODUCT_ALIASES), "dosis_fumi")
        self.assertEqual(ColumnMapper.match_column("DOSIS DRENCH", ColumnMapper.PRODUCT_ALIASES), "dosis_drench")
        self.assertEqual(ColumnMapper.match_column("UM", ColumnMapper.PRODUCT_ALIASES), "um")

        # Crop state aliases
        self.assertEqual(ColumnMapper.match_column("BLOQUES2", ColumnMapper.CROP_STATE_ALIASES), "bloques2")
        self.assertEqual(ColumnMapper.match_column("BLQ", ColumnMapper.CROP_STATE_ALIASES), "blq")
        self.assertEqual(ColumnMapper.match_column("# Cama", ColumnMapper.CROP_STATE_ALIASES), "cama")
        self.assertEqual(ColumnMapper.match_column("SUFIJO", ColumnMapper.CROP_STATE_ALIASES), "sufijo")
        self.assertEqual(ColumnMapper.match_column("CAMA ESTÁNDAR", ColumnMapper.CROP_STATE_ALIASES), "cama_estandar")
        self.assertEqual(ColumnMapper.match_column("EDAD REAL", ColumnMapper.CROP_STATE_ALIASES), "edad_real")
        self.assertEqual(ColumnMapper.match_column("ZONA", ColumnMapper.CROP_STATE_ALIASES), "zona")

if __name__ == '__main__':
    unittest.main()
