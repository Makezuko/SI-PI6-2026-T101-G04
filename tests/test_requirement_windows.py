import unittest
import numpy as np
from src.matching.semantic import aggregate_requirement_windows
from src.matching.telemetry import stage


class RequirementWindowTests(unittest.TestCase):
    def test_retokenized_limit_and_coverage_even_for_oversized_word(self):
        from types import SimpleNamespace
        from src.nlp.embeddings import ResumeEmbedder
        class Tokenizer:
            def __call__(self, text, **kwargs):
                if kwargs.get('return_offsets_mapping'):
                    return dict(offset_mapping=[(i, i+1) for i in range(len(text))])
                return dict(input_ids=list(range(len(text)+2)))
        embedder = ResumeEmbedder.__new__(ResumeEmbedder)
        embedder.tokenizer = Tokenizer()
        embedder.model = SimpleNamespace(max_seq_length=16)
        embedder.window_size, embedder.overlap = 14, 3
        text = 'word ' + 'x'*100 + ' end'
        covered = 0
        for record in embedder._split_text(text):
            self.assertLessEqual(record['token_count'], 16)
            self.assertLessEqual(record['start_char'], covered)
            self.assertEqual(record['text'], text[record['start_char']:record['end_char']])
            covered = record['end_char']
        self.assertEqual(covered, len(text))

    def test_windows_group_by_input_index_with_original_id_order(self):
        requirements = [dict(id='a'), dict(id='b')]
        encoded = dict(records=[dict(input_index=1, metadata=dict(requirement_id='b')),
                                dict(input_index=0), dict(input_index=0)],
                       embeddings=[[0, 1], [1, 0], [0, 1]])
        vectors = aggregate_requirement_windows(requirements, encoded)
        np.testing.assert_allclose(vectors, [[2**-.5, 2**-.5], [0, 1]])
        self.assertEqual(len(vectors), len(requirements))

    def test_missing_misaligned_and_invalid_vectors_fail(self):
        for record, vectors in [(dict(input_index=1), [[1, 0]]),
                                (dict(input_index=0, metadata=dict(requirement_id='wrong')), [[1, 0]]),
                                (dict(input_index=0), [[float('nan'), 0]]),
                                (dict(input_index=0), [[0, 0]])]:
            with self.assertRaises(ValueError):
                aggregate_requirement_windows([dict(id='a')], dict(records=[record], embeddings=vectors))
        with self.assertRaises(ValueError):
            aggregate_requirement_windows([dict(id='a')], dict(records=[], embeddings=[]))

    def test_traceback_does_not_log_exception_message(self):
        with self.assertLogs('talentmatch.analysis', level='INFO') as logs:
            with self.assertRaises(ValueError):
                with stage('evidence_embeddings'):
                    raise ValueError('PRIVATE PAYLOAD SECRET')
        output = '\n'.join(logs.output)
        self.assertNotIn('PRIVATE', output)
        for value in ['evidence_embeddings', 'ValueError', 'test_requirement_windows.py', 'line', 'function']:
            self.assertIn(value, output)
