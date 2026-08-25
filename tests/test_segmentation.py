import unittest
from app.modules.fumigacion.services.calculation_engine import CalculationEngine

class TestSegmentation(unittest.TestCase):

    def test_format_bed_range(self):
        self.assertEqual(CalculationEngine.format_bed_range([1, 2, 3, 4, 5]), "Camas 1-5")
        self.assertEqual(CalculationEngine.format_bed_range([1, 2, 3, 7, 8, 9]), "Camas 1-3, 7-9")
        self.assertEqual(CalculationEngine.format_bed_range([5]), "Cama 5")
        self.assertEqual(CalculationEngine.format_bed_range([1, 3, 5, 7]), "Camas 1, 3, 5, 7")
        self.assertEqual(CalculationEngine.format_bed_range([10, 11, 12, 15]), "Camas 10-12, 15")
        self.assertEqual(CalculationEngine.format_bed_range([]), "")

if __name__ == '__main__':
    unittest.main()
