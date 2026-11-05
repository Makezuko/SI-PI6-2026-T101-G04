"""Regressão da apresentação de datas, sem conexão com o Supabase."""
import os
import unittest

os.environ.setdefault('FLASK_SECRET_KEY', 'test-only-secret-not-for-deployment')

from app.repositories import format_display_date, job_for_template, resume_for_template


class FormatDisplayDateTests(unittest.TestCase):
    def test_valid_iso(self):
        self.assertEqual(format_display_date('2026-11-04T14:30:00+00:00'), '04/11/2026')

    def test_missing_date(self):
        self.assertEqual(format_display_date(None), '—')

    def test_invalid_date(self):
        for value in ('inválida', '2026-02-30', 42):
            with self.subTest(value=value):
                self.assertEqual(format_display_date(value), '—')

    def test_empty_date(self):
        self.assertEqual(format_display_date(''), '—')

    def test_iso_with_z(self):
        self.assertEqual(format_display_date('2026-11-04T23:30:00Z'), '04/11/2026')

    def test_template_dates(self):
        # Texto vazio evita executar os extratores de currículo; só a data varia.
        cases = (
            ('2026-11-04T14:30:00', '04/11/2026'),
            ('2026-11-04T23:30:00Z', '04/11/2026'),
            ('2026-11-04T00:30:00+03:00', '04/11/2026'),
            (None, '—'), ('', '—'), ('inválida', '—'), (42, '—'),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                job = job_for_template({
                    'id': 1, 'titulo': 'Teste', 'descricao': 'Python',
                    'requisitos': '', 'criado_em': value,
                })
                resume = resume_for_template({'id': 2, 'enviado_em': value})
                self.assertEqual(job['created_at'], expected)
                self.assertEqual(resume['submitted_at'], expected)

    def test_absent_template_date_fields(self):
        job = job_for_template({
            'id': 1, 'titulo': 'Teste', 'descricao': 'Python', 'requisitos': '',
        })
        self.assertEqual(job['created_at'], '—')
        self.assertEqual(resume_for_template({'id': 2})['submitted_at'], '—')


if __name__ == '__main__':
    unittest.main()
