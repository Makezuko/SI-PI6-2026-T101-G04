import unittest
import numpy as np
from src.matching.semantic import cosine_matrix, compare, evaluate_ranking
class SemanticStageTests(unittest.TestCase):
    def test_math(self):
        np.testing.assert_allclose(cosine_matrix([[2,0],[0,3]],[[1,0],[0,1]]),np.eye(2))
        for a,b in [([[0,0]],[[1,0]]),([[1,0]],[[1,0,0]]),([[float('nan'),1]],[[1,0]])]:
            with self.assertRaises(ValueError): cosine_matrix(a,b)
    def test_chunks(self):
        resume={'records':[{'input_index':0,'chunk_index':0,'source':'skill','text':'A'},{'input_index':0,'chunk_index':1,'source':'skill','text':'A2'},{'input_index':1,'chunk_index':0,'source':'project','text':'B'}],'embeddings':[[1,0],[1,0],[0,1]]}
        rows,_=compare([{'id':'R','text':'A'}],[[1,0]],resume)
        self.assertEqual(len(rows[0]['ranking']),2)
        self.assertEqual(rows[0]['ranking'][0]['input_index'],0)
    def test_metrics(self):
        results=[{'id':'R1','ranking':[{'input_index':0,'similarity':.9},{'input_index':1,'similarity':.8}]},
                 {'id':'R2','ranking':[{'input_index':0,'similarity':.7}]},
                 {'id':'R3','ranking':[{'input_index':0,'similarity':.2}]}]
        req=[{'acceptable_input_indices':[1]},{'acceptable_input_indices':[]},{}]
        m=evaluate_ranking(results,req)
        self.assertEqual(m['evaluated_positive_count'],1)
        self.assertEqual(m['no_evidence_count'],1)
        self.assertEqual(m['unannotated_count'],1)
        self.assertEqual(m['hit_at_1'],0)
        self.assertEqual(m['hit_at_3'],1)
        self.assertEqual(m['mrr'],.5)
        self.assertAlmostEqual(m['per_requirement'][0]['top1_top2_margin'],.1)
        self.assertIsNone(m['per_requirement'][1]['top1_top2_margin'])
        self.assertIsNone(evaluate_ranking(results[1:],req[1:])['mrr'])
        missing=evaluate_ranking(results[:1],[{'acceptable_input_indices':[99]}])
        self.assertEqual(missing['mrr'],0)
if __name__=='__main__': unittest.main()
