import unittest
from app.shared.models import Crop

class TestAgeRanges(unittest.TestCase):

    def setUp(self):
        self.hypericum = Crop(
            name='Hypericum',
            veg_min_age=0,
            veg_max_age=12,
            prod_min_age=13,
            prod_max_age=25
        )
        self.veronica = Crop(
            name='Veronica',
            veg_min_age=0,
            veg_max_age=9,
            prod_min_age=10,
            prod_max_age=15
        )

    def test_hypericum_classification(self):
        self.assertEqual(self.hypericum.classify_age(0), 'VEGETATIVO')
        self.assertEqual(self.hypericum.classify_age(5), 'VEGETATIVO')
        self.assertEqual(self.hypericum.classify_age(12), 'VEGETATIVO')
        self.assertEqual(self.hypericum.classify_age(13), 'PRODUCTIVO')
        self.assertEqual(self.hypericum.classify_age(20), 'PRODUCTIVO')
        self.assertEqual(self.hypericum.classify_age(25), 'PRODUCTIVO')
        self.assertEqual(self.hypericum.classify_age(26), 'FUERA_DE_RANGO')
        self.assertEqual(self.hypericum.classify_age(None), 'SIN_EDAD')

    def test_veronica_classification(self):
        self.assertEqual(self.veronica.classify_age(0), 'VEGETATIVO')
        self.assertEqual(self.veronica.classify_age(9), 'VEGETATIVO')
        self.assertEqual(self.veronica.classify_age(10), 'PRODUCTIVO')
        self.assertEqual(self.veronica.classify_age(15), 'PRODUCTIVO')
        self.assertEqual(self.veronica.classify_age(16), 'FUERA_DE_RANGO')

if __name__ == '__main__':
    unittest.main()
