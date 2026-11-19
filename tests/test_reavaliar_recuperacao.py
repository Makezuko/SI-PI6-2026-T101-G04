import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.reavaliar_recuperacao import aggregate, calculate, fingerprint, load_verified, score_requirement


def requirement(gold, failure=False, original=True):
    return dict(acceptable_input_indices=gold, extraction_failure=failure, evidence_in_original=original)


def ranking(*indices):
    return [dict(input_index=i) for i in indices]


class RecoveryMetricsTests(unittest.TestCase):
    def test_multiple_relevant_ideal_uses_all_gold(self):
        r = score_requirement(requirement([1, 3, 5, 7]), ranking(1, 3, 9))
        self.assertEqual(r['hit_at_3'], 1)
        self.assertAlmostEqual(r['precision_at_3'], 2/3)
        self.assertEqual(r['recall_at_3'], .5)
        self.assertAlmostEqual(r['ndcg_at_3'], (1+1/math.log2(3))/(1+1/math.log2(3)+.5))

    def test_single_gold_at_positions(self):
        for order, expected in [((1,8,9),1), ((8,1,9),1/math.log2(3)), ((8,9,1),.5)]:
            with self.subTest(order=order):
                r = score_requirement(requirement([1]), ranking(*order))
                self.assertEqual(r['precision_at_3'], 1/3)
                self.assertEqual(r['recall_at_3'], 1)
                self.assertAlmostEqual(r['ndcg_at_3'], expected)

    def test_miss_short_and_duplicates(self):
        r = score_requirement(requirement([1]), ranking(7, 8, 9))
        self.assertEqual((r['hit_at_3'], r['precision_at_3'], r['recall_at_3'], r['ndcg_at_3']), (0, 0, 0, 0))
        r = score_requirement(requirement([1, 3]), ranking(1, 1, 3))
        self.assertEqual(r['entradas_top3'], 2)
        self.assertTrue(r['ranking_curto'])
        self.assertEqual(r['precision_at_3'], 2/3)
        self.assertEqual(r['recall_at_3'], 1)
        self.assertEqual(r['ndcg_at_3'], 1)

    def test_loss_negative_pending_macro(self):
        a = score_requirement(requirement([1]), ranking(1))
        b = score_requirement(requirement([1, 3]), ranking(3, 9, 8))
        lost = score_requirement(requirement([], failure=True), ranking(9))
        negative = score_requirement(requirement([], original=False), ranking(9))
        pending = score_requirement(requirement(None), ranking(9))
        self.assertIsNone(lost['relevantes_anotados'])
        self.assertIsNone(lost['precision_at_3'])
        self.assertIsNone(lost['ndcg_at_3'])
        g = aggregate([a,b,lost,negative,pending])
        self.assertEqual((g['denominador_recuperavel'], g['hit_denominador_ponta_a_ponta']), (2,3))
        self.assertEqual((g['sem_evidencia'], g['pendentes'], g['falhas_extracao']), (1,1,1))
        self.assertAlmostEqual(g['hit_at_3_ponta_a_ponta'], 2/3)
        self.assertEqual(g['precision_at_3'], 1/3)
        self.assertEqual(g['recall_at_3'], .75)
        self.assertEqual(g['rankings_curtos'], 1)

    def test_frozen_inputs_without_models_and_reject_tampering(self):
        with TemporaryDirectory() as directory:
            root=Path(directory); folder=root/'sample'/'cv'; folder.mkdir(parents=True)
            inputs=[dict(input_index=0), dict(input_index=1)]
            req=dict(id='r', category='literal', **requirement([1]))
            review=dict(completed=True, reviewer='human')
            annotation=dict(resume_id='cv', inputs_sha256=fingerprint(inputs), requirements=[req], human_review=review)
            (folder/'entradas.json').write_text(json.dumps(inputs), encoding='utf8')
            (folder/'anotacoes.json').write_text(json.dumps(annotation), encoding='utf8')
            data=dict(manifest=dict(selected_resumes=[dict(resume_id='cv', inputs_sha256=fingerprint(inputs))]),
                      annotations_sha256={'cv': fingerprint(annotation)}, rows=[dict(resume_id='cv', requirement=req,
                      human_review=review, result=dict(id='r', ranking=ranking(1, 0)))])
            source=root/'results.json'; source.write_text(json.dumps(data), encoding='utf8')
            loaded, hashes=load_verified(source, root/'sample')
            self.assertEqual(calculate(loaded)['geral']['hit_at_3'], 1)
            self.assertEqual(len(hashes), 3)
            annotation['requirements'][0]['acceptable_input_indices'] = [0]
            (folder/'anotacoes.json').write_text(json.dumps(annotation), encoding='utf8')
            with self.assertRaises(ValueError):
                load_verified(source, root/'sample')


if __name__ == '__main__':
    unittest.main()
