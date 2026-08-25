import unittest
from app import create_app
from app.extensions import db
from app.shared.models import User

class TestAuthRolesAndPermissions(unittest.TestCase):

    def setUp(self):
        self.app = create_app()
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        self.app_context.pop()

    def test_admin_permissions(self):
        admin = User(username='admin_test', full_name='Admin Test', role='ADMIN')
        self.assertTrue(admin.has_permission('fumigacion'))
        self.assertTrue(admin.has_permission('drench'))
        self.assertTrue(admin.has_permission('trichos'))
        self.assertTrue(admin.has_permission('desinfecciones'))
        self.assertTrue(admin.has_permission('ordenes_ver'))
        self.assertTrue(admin.has_permission('salidas_ver'))
        self.assertTrue(admin.has_permission('catalogos'))

    def test_agronomo_permissions(self):
        # Agronomist with only Drench & Trichos
        agro_bio = User(
            username='agro_bio',
            full_name='Ing. Biológicos',
            role='AGRONOMO',
            permissions=['drench', 'trichos']
        )
        self.assertTrue(agro_bio.has_permission('drench'))
        self.assertTrue(agro_bio.has_permission('trichos'))
        self.assertFalse(agro_bio.has_permission('fumigacion'))
        self.assertFalse(agro_bio.has_permission('desinfecciones'))

        # Agronomist with Fumigacion (inherits sub-features)
        agro_fumi = User(
            username='agro_fumi',
            full_name='Ing. Fumigación',
            role='AGRONOMO',
            permissions=['fumigacion', 'catalogos']
        )
        self.assertTrue(agro_fumi.has_permission('fumigacion'))
        self.assertTrue(agro_fumi.has_permission('ordenes_ver'))
        self.assertTrue(agro_fumi.has_permission('ordenes_imprimir'))
        self.assertTrue(agro_fumi.has_permission('salidas_ver'))
        self.assertTrue(agro_fumi.has_permission('salidas_imprimir'))
        self.assertTrue(agro_fumi.has_permission('aplicaciones_extras'))
        self.assertTrue(agro_fumi.has_permission('catalogos'))
        self.assertFalse(agro_fumi.has_permission('drench'))

    def test_asistente_permissions(self):
        asist = User(
            username='asist_bodega',
            full_name='Asistente Bodega',
            role='ASISTENTE',
            permissions=['ordenes_ver', 'ordenes_imprimir', 'salidas_ver', 'salidas_imprimir']
        )
        self.assertTrue(asist.has_permission('ordenes_ver'))
        self.assertTrue(asist.has_permission('ordenes_imprimir'))
        self.assertTrue(asist.has_permission('salidas_ver'))
        self.assertTrue(asist.has_permission('salidas_imprimir'))
        self.assertFalse(asist.has_permission('fumigacion'))
        self.assertFalse(asist.has_permission('drench'))
        self.assertFalse(asist.has_permission('trichos'))
        self.assertFalse(asist.has_permission('catalogos'))
        self.assertFalse(asist.has_permission('importador'))

    def test_inactive_user(self):
        user = User(username='inactive_user', full_name='Inactive', role='ADMIN', is_active=False)
        self.assertFalse(user.has_permission('fumigacion'))
        self.assertFalse(user.has_permission('ordenes_ver'))

    def test_password_hashing(self):
        user = User(username='pwd_test', full_name='Pwd Test')
        user.set_password('SecretPass!2026')
        self.assertTrue(user.check_password('SecretPass!2026'))
        self.assertFalse(user.check_password('WrongPass'))
    def test_unauthenticated_redirect_to_login(self):
        res = self.client.get('/', follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/auth/login', res.headers['Location'])

        res_fumi = self.client.get('/fumigacion/rotaciones', follow_redirects=False)
        self.assertEqual(res_fumi.status_code, 302)
        self.assertIn('/auth/login', res_fumi.headers['Location'])

    def test_login_view_has_no_sidebar(self):
        res = self.client.get('/auth/login')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertNotIn('sidebar-wrapper', html)
        self.assertNotIn('sidebar-toggle', html)
