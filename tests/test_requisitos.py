"""Testes da regra de requisitos de vaga (sem Flask nem Supabase)."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from werkzeug.datastructures import MultiDict

from app.requisitos import (MAX_ITEMS, MAX_TEXT, build_requirements, draft_from_description,
                            parse_requirements, rows_from_form, serialize)


def row(text, tipo='tecnico', nivel='obrigatorio', id=''):
    return {'id': id, 'text': text, 'tipo': tipo, 'nivel': nivel}


class RequisitosTestCase(unittest.TestCase):
    def test_build_normalizes_and_assigns_sequential_ids(self):
        result = build_requirements([row('  Python   3 '), row('', 'tecnico'), row('Comunicação', 'comportamental', 'desejavel')])
        self.assertEqual(result['status'], 'revisado')
        self.assertEqual([(i['id'], i['text']) for i in result['items']], [('R1', 'Python 3'), ('R2', 'Comunicação')])

    def test_blank_rows_only_gives_pending_empty(self):
        result = build_requirements([row(''), row('   ')])
        self.assertEqual(result, {'versao': 2, 'status': 'pendente_revisao', 'items': []})

    def test_requires_valid_type_and_level(self):
        with self.assertRaises(ValueError):
            build_requirements([row('Python', tipo='')])
        with self.assertRaises(ValueError):
            build_requirements([row('Python', tipo='outro')])
        with self.assertRaises(ValueError):
            build_requirements([row('Python', nivel='talvez')])

    def test_limits(self):
        with self.assertRaises(ValueError):
            build_requirements([row('x' * (MAX_TEXT + 1))])
        build_requirements([row('x' * MAX_TEXT)])
        with self.assertRaises(ValueError):
            build_requirements([row(f'Item {n}') for n in range(MAX_ITEMS + 1)])

    def test_duplicates_are_dropped_but_same_text_with_other_type_is_kept(self):
        result = build_requirements([row('Python'), row('python'), row('Python', 'comportamental')])
        self.assertEqual([(i['text'], i['tipo']) for i in result['items']], [('Python', 'tecnico'), ('Python', 'comportamental')])

    def test_ids_are_kept_and_never_reused(self):
        result = build_requirements([row('A', id='R1'), row('Novo')], known_ids=['R1', 'R2'])
        self.assertEqual([i['id'] for i in result['items']], ['R1', 'R3'])

    def test_duplicate_or_invalid_submitted_ids_are_reassigned(self):
        result = build_requirements([row('A', id='R1'), row('B', id='R1'), row('C', id='x')])
        ids = [i['id'] for i in result['items']]
        self.assertEqual(ids[0], 'R1')
        self.assertEqual(len(set(ids)), 3)

    def test_parse_roundtrip(self):
        built = build_requirements([row('Python'), row('Empatia', 'comportamental', 'desejavel')])
        self.assertEqual(parse_requirements(serialize(built)), built)

    def test_parse_step1_draft_is_pending_and_untyped(self):
        legacy = '{"status": "pendente_revisao", "items": [{"id": "R1", "text": "Python"}, {"id": "R2", "text": "SQL"}]}'
        parsed = parse_requirements(legacy)
        self.assertEqual(parsed['status'], 'pendente_revisao')
        self.assertEqual([(i['id'], i['tipo']) for i in parsed['items']], [('R1', None), ('R2', None)])

    def test_parse_tolerates_garbage(self):
        for raw in [None, '', '   ', '[]', '{"items": 3}', 'null', 7]:
            self.assertEqual(parse_requirements(raw)['items'], [])
        plain = parse_requirements('Python\n\nSQL')
        self.assertEqual([i['text'] for i in plain['items']], ['Python', 'SQL'])
        self.assertEqual(plain['status'], 'pendente_revisao')

    def test_parse_ignores_invalid_entries(self):
        parsed = parse_requirements({'items': [{'text': ''}, 5, {'text': 'Go', 'tipo': 'x', 'nivel': 'y'}, 'Rust']})
        self.assertEqual([(i['text'], i['tipo'], i['nivel']) for i in parsed['items']],
                         [('Go', None, 'obrigatorio'), ('Rust', None, 'obrigatorio')])

    def test_draft_from_description(self):
        draft = draft_from_description('Python\n\n  SQL  \n')
        self.assertEqual([(i['id'], i['text']) for i in draft['items']], [('R1', 'Python'), ('R2', 'SQL')])
        self.assertEqual(draft['status'], 'pendente_revisao')

    def test_rows_from_form_requires_aligned_columns(self):
        form = MultiDict([('req_id', ''), ('req_text', 'Python'), ('req_tipo', 'tecnico'), ('req_nivel', 'obrigatorio')])
        self.assertEqual(rows_from_form(form), [row('Python')])
        form.setlist('req_tipo', [])
        with self.assertRaises(ValueError):
            rows_from_form(form)


if __name__ == '__main__':
    unittest.main()
