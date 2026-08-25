import unittest
from app import create_app
from app.extensions import db
from app.shared.models import Crop, Product, Litraje, CropStateRecord, Rotation, RotationRound, RotationRoundItem, FumigationOrder
from app.modules.fumigacion.services.calculation_engine import CalculationEngine
from app.modules.fumigacion.services.order_service import OrderService

class TestCalculations(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.app_context.pop()

    def test_calculation_formula(self):
        # Liters total = Liters per bed * Standard beds
        liters_per_bed = 5.0
        standard_beds = 10.0
        total_liters = liters_per_bed * standard_beds
        self.assertEqual(total_liters, 50.0)

        # Product quantity = Total liters * Dose
        dose = 2.0  # 2 ml/L
        product_amount = total_liters * dose
        self.assertEqual(product_amount, 100.0)

    def test_end_to_end_calculation(self):
        # Find active crop & product in db
        crop = Crop.query.filter_by(name='Hypericum').first()
        self.assertIsNotNone(crop)
        product = Product.query.filter_by(code='ACARAMIK').first()
        self.assertIsNotNone(product)

        # Create test round
        dummy_round = RotationRound(
            round_number=1,
            name="Test Round",
            scheduled_day="Lunes"
        )
        item = RotationRoundItem(
            crop_name='Hypericum',
            phenological_stage='VEGETATIVO',
            product_id=product.id,
            dose_applied=0.5,
            dose_unit='CC'
        )
        item.product = product
        dummy_round.items.append(item)

        result = CalculationEngine.calculate_round(dummy_round)
        self.assertGreater(result['totals']['total_liters'], 0)
        self.assertGreater(result['totals']['total_standard_beds'], 0)
        self.assertGreater(len(result['segments']), 0)
        self.assertEqual(len(result['product_summaries']), 1)
        self.assertEqual(result['product_summaries'][0]['product_code'], 'ACARAMIK')

    def test_order_snapshot_immutability(self):
        # Create rotation and round
        rot = Rotation(week='2026-99', title='Rotación Test Inmutabilidad')
        db.session.add(rot)
        db.session.flush()

        v = RotationRound(rotation_id=rot.id, round_number=1, name='Vuelta 1', scheduled_day='Lunes')
        db.session.add(v)
        db.session.flush()

        prod = Product.query.filter_by(code='ACARAMIK').first()
        item = RotationRoundItem(
            round_id=v.id,
            crop_name='Hypericum',
            phenological_stage='VEGETATIVO',
            product_id=prod.id,
            dose_applied=0.5,
            dose_unit='CC'
        )
        db.session.add(item)
        db.session.commit()

        # Generate order snapshot
        order = OrderService.create_order_from_round(v.id, agronomist='Tester')
        frozen_liters = order.total_liters
        frozen_beds = order.total_standard_beds

        self.assertIsNotNone(order.order_number)
        self.assertGreater(frozen_liters, 0)

        # The frozen order must NOT change
        persisted_order = FumigationOrder.query.get(order.id)
        self.assertEqual(persisted_order.total_liters, frozen_liters)
        self.assertEqual(persisted_order.total_standard_beds, frozen_beds)

    def test_integer_rounding_for_cc_and_g_units(self):
        from app.shared.utils import format_product_amount, is_integer_unit, round_product_amount
        
        # Helper check
        self.assertTrue(is_integer_unit('CC'))
        self.assertTrue(is_integer_unit('cc'))
        self.assertTrue(is_integer_unit('G'))
        self.assertTrue(is_integer_unit('GR'))
        self.assertTrue(is_integer_unit('ML'))
        self.assertTrue(is_integer_unit('PST'))
        self.assertFalse(is_integer_unit('LT'))
        self.assertFalse(is_integer_unit('KG'))

        # Formatter check
        self.assertEqual(format_product_amount(150.7, 'CC'), '151')
        self.assertEqual(format_product_amount(37.2, 'cc'), '37')
        self.assertEqual(format_product_amount(100.0, 'CC'), '100')
        self.assertEqual(format_product_amount(2.54, 'LT'), '2.5')

        # Rounding check
        self.assertEqual(round_product_amount(150.7, 'CC'), 151.0)
        self.assertEqual(round_product_amount(37.2, 'cc'), 37.0)
        self.assertEqual(round_product_amount(2.54, 'LT'), 2.54)

if __name__ == '__main__':
    unittest.main()
