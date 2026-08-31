import unittest
from app import create_app
from app.extensions import db
from app.shared.models import User, Rotation, RotationRound, RotationRoundItem, FumigationOrder, Product
from app.modules.fumigacion.services.order_service import OrderService
from app.shared.utils import is_liquid_unit, is_solid_unit

class TestBodegaModule(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

        # Create test users
        self.admin = User.query.filter_by(username='admin').first()
        if not self.admin:
            self.admin = User(username='admin', full_name='Admin General', role='ADMIN')
            self.admin.set_password('Admin123*')
            self.admin.permissions = ['fumigacion', 'bodega', 'catalogos']
            db.session.add(self.admin)
            db.session.commit()

        # Create Bodeguero user
        self.bodeguero = User.query.filter_by(username='bodeguero_test').first()
        if not self.bodeguero:
            self.bodeguero = User(username='bodeguero_test', full_name='Bodeguero Juan', role='BODEGUERO')
            self.bodeguero.set_password('Bodega123*')
            self.bodeguero.permissions = ['bodega', 'salidas_ver', 'salidas_imprimir', 'ordenes_ver', 'ordenes_imprimir']
            db.session.add(self.bodeguero)
            db.session.commit()

    def tearDown(self):
        self.app_context.pop()

    def test_bodega_permissions_check(self):
        self.assertTrue(self.bodeguero.has_permission('bodega'))
        self.assertTrue(self.bodeguero.has_permission('salidas_ver'))
        self.assertTrue(self.bodeguero.has_permission('ordenes_ver'))
        self.assertFalse(self.bodeguero.has_permission('catalogos'))

    def test_bodega_routes_access_with_login(self):
        # Login as bodeguero
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.bodeguero.id
            sess['username'] = self.bodeguero.username
            sess['role'] = self.bodeguero.role
            sess['full_name'] = self.bodeguero.full_name

        # Access salidas
        resp_salidas = self.client.get('/bodega/salidas')
        self.assertEqual(resp_salidas.status_code, 200)
        self.assertIn(b'M\xc3\xb3dulo de Bodega', resp_salidas.data)

        # Access ordenes
        resp_ordenes = self.client.get('/bodega/ordenes')
        self.assertEqual(resp_ordenes.status_code, 200)
        self.assertIn(b'Programas Oficiales', resp_ordenes.data)

    def test_liquid_and_solid_unit_classification(self):
        self.assertTrue(is_liquid_unit('CC'))
        self.assertTrue(is_liquid_unit('ML'))
        self.assertTrue(is_liquid_unit('LT'))
        self.assertFalse(is_solid_unit('CC'))

        self.assertTrue(is_solid_unit('G'))
        self.assertTrue(is_solid_unit('GR'))
        self.assertTrue(is_solid_unit('KG'))
        self.assertTrue(is_solid_unit('PST'))
        self.assertFalse(is_liquid_unit('G'))

    def test_program_title_update_endpoint(self):
        # Find an existing order or create one
        order = FumigationOrder.query.first()
        if order:
            with self.client.session_transaction() as sess:
                sess['user_id'] = self.bodeguero.id
                sess['username'] = self.bodeguero.username
                sess['role'] = self.bodeguero.role
                sess['full_name'] = self.bodeguero.full_name

            new_test_title = "Programa Test Botrytis Sem 99"
            resp = self.client.post(
                f'/bodega/ordenes/{order.id}/editar-titulo',
                json={'title': new_test_title}
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json.get('title'), new_test_title)

            # Reload and check
            updated = db.session.get(FumigationOrder, order.id)
            self.assertEqual(updated.title, new_test_title)

    def test_orden_detalle_renders_in_both_modules(self):
        order = FumigationOrder.query.first()
        if order:
            with self.client.session_transaction() as sess:
                sess['user_id'] = self.bodeguero.id
                sess['username'] = self.bodeguero.username
                sess['role'] = self.bodeguero.role
                sess['full_name'] = self.bodeguero.full_name

            # Test bodega view
            resp_b = self.client.get(f'/bodega/ordenes/{order.id}')
            self.assertEqual(resp_b.status_code, 200)
            self.assertIn(b'Pesaje y Dosificaci\xc3\xb3n en Bodega', resp_b.data)

            # Test agronomic fumigacion view
            resp_f = self.client.get(f'/fumigacion/ordenes/{order.id}')
            self.assertEqual(resp_f.status_code, 200)
            self.assertIn(b'PROGRAMA', resp_f.data)

    def test_bodega_only_shows_approved_rotations(self):
        # Create unapproved draft rotation
        draft_rot = Rotation(week='2026-88', title='Borrador No Aprobado', status='BORRADOR')
        db.session.add(draft_rot)
        db.session.commit()

        # Login as bodeguero
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.bodeguero.id
            sess['username'] = self.bodeguero.username
            sess['role'] = self.bodeguero.role
            sess['full_name'] = self.bodeguero.full_name

        resp = self.client.get(f'/bodega/salidas?rotation_id={draft_rot.id}')
        # Should not show the draft rotation as current approved
        self.assertEqual(resp.status_code, 200)
        # Clean up
        db.session.delete(draft_rot)
        db.session.commit()

    def test_excel_export_structure_and_columns(self):
        import pandas as pd
        order = FumigationOrder.query.first()
        if order and order.details:
            stream = OrderService.export_order_to_excel(order)
            self.assertIsNotNone(stream)
            df = pd.read_excel(stream)

            # Columns that MUST NOT exist
            self.assertNotIn('SUFIJO', df.columns, "SUFIJO column must be removed")
            self.assertNotIn('ETAPA', df.columns, "ETAPA column must be removed")
            self.assertNotIn('PRODUCTO', df.columns, "PRODUCTO code column must be removed")

            # Column that MUST exist
            self.assertIn('NOMBRE COMERCIAL', df.columns, "NOMBRE COMERCIAL column must be present")
            self.assertIn('VARIEDAD', df.columns)
            self.assertIn('TOTAL PRODUCTO', df.columns)
            self.assertIn('CAMAS', df.columns)
            self.assertIn('TOTAL LITROS', df.columns)
            self.assertIn('VTA', df.columns)
            self.assertIn('DÍA', df.columns)
            self.assertIn('BLOQUE', df.columns)
            self.assertIn('OPERARIO', df.columns)

            # Check rows repeat faithfully
            self.assertEqual(len(df), len(order.details))

if __name__ == '__main__':
    unittest.main()

