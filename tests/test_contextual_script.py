import json
import os
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import testar_fluxo_contextual


class ContextualScriptTests(unittest.TestCase):
    def test_long_requirement_windows_are_aggregated_before_comparison(self):
        class Embedder:
            def __init__(self, path):
                pass

            def encode(self, entries):
                if entries[0]['source'] == 'requirement':
                    self_requirement_id = entries[0]['requirement_id']
                    return dict(records=[dict(input_index=0, metadata=dict(requirement_id=self_requirement_id))] * 2,
                                embeddings=[[1, 0], [0, 1]])
                return dict(records=[], embeddings=[])

        class Predictor:
            def __init__(self, **kwargs):
                pass

            def predict(self, **kwargs):
                return {'entities': []}

        with TemporaryDirectory() as directory, chdir(directory):
            root = Path(directory)
            manifest = root / 'models/contextual/manifest.json'
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({'evaluator': {'path': 'model', 'revision': 'r'},
                                            'retrieval': {'path': 'embedding'}}), encoding='utf-8')
            resume = root / 'resume.txt'
            resume.write_text('example', encoding='utf-8')
            output = root / 'output.json'
            with patch.dict(os.environ), \
                 patch('sys.argv', ['script', '--input', str(resume), '--limit', '1', '--output', str(output)]), \
                 patch('src.nlp.inference.ResumeNERPredictor', Predictor), \
                 patch('src.nlp.embeddings.ResumeEmbedder', Embedder), \
                 patch('src.data.privacy.anonymize_for_analysis', return_value='example'), \
                 patch('src.nlp.skills_extractor.extract_skills', return_value={'semantic_inputs': [{'text': 'example', 'source': 'experience'}]}), \
                 patch('src.data.privacy.sanitize_semantic_inputs', side_effect=lambda entries: entries), \
                 patch('src.matching.semantic.compare', return_value=([], {})) as compare, \
                 patch('src.matching.contextual.create_adapter'), \
                 patch('src.matching.contextual.evaluate_batch', return_value={'details': [], 'score': 0, 'maximum_score': 100}):
                testar_fluxo_contextual.main()
            vectors = compare.call_args.args[1]
            self.assertEqual(len(vectors), 1)
            self.assertAlmostEqual(vectors[0][0], 2 ** -.5)
            self.assertAlmostEqual(vectors[0][1], 2 ** -.5)


if __name__ == '__main__':
    unittest.main()
