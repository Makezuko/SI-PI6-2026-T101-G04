"""Comparação semântica e avaliação de evidências; não calcula aderência final."""
import numpy as np


def cosine_matrix(requirement_vectors, resume_vectors):
    """Normaliza novamente para aceitar também vetores não normalizados."""
    matrices = []
    for values in (requirement_vectors, resume_vectors):
        array = np.asarray(values, dtype=float)
        if array.ndim != 2 or not array.size or not np.isfinite(array).all():
            raise ValueError("Matriz vazia, inválida ou com valores não finitos.")
        norms = np.linalg.norm(array, axis=1, keepdims=True)
        if (norms == 0).any():
            raise ValueError("Embedding com norma zero.")
        matrices.append(array / norms)
    if matrices[0].shape[1] != matrices[1].shape[1]:
        raise ValueError("Dimensões dos embeddings incompatíveis.")
    return np.clip(matrices[0] @ matrices[1].T, -1, 1)


def compare(requirements, requirement_vectors, resume):
    """Uma linha por requisito; agrupa chunks pela entrada original."""
    records = resume['records']
    if len(records) != len(resume['embeddings']):
        raise ValueError("Registros e vetores do currículo não correspondem.")
    matrix = cosine_matrix(requirement_vectors, resume['embeddings'])
    if len(requirements) != len(matrix):
        raise ValueError("Requisitos e vetores não correspondem.")
    result = []
    for requirement, scores in zip(requirements, matrix):
        # Evita contar chunks sobrepostos como evidências independentes.
        grouped = {}
        for index, score in enumerate(scores):
            record = records[index]
            input_id = record['input_index']
            candidate = {'input_index': input_id, 'similarity': float(score),
                         'text': record['text'], 'source': record['source'],
                         'chunk_index': record['chunk_index'],
                         'metadata': record.get('metadata', {})}
            if input_id not in grouped or score > grouped[input_id]['similarity']:
                grouped[input_id] = candidate
        ranked = sorted(grouped.values(), key=lambda item: (-item['similarity'], item['input_index']))
        skill_scores = [float(scores[i]) for i, record in enumerate(records) if record['source'] == 'skill']
        result.append({'id': requirement['id'], 'requirement': requirement['text'],
                       'top_similarity': ranked[0]['similarity'],
                       'skills_only_similarity': max(skill_scores) if skill_scores else None,
                       'ranking': ranked})
    return result, matrix


def evaluate_ranking(results, requirements):
    """Hit@k e MRR nos positivos anotados; sem classificação/limiar.

    [] indica que não há evidência suficiente: item fica fora do ranking
    avaliado, mas permanece na análise visual. null/campo ausente = não anotado.
    """
    if len(results) != len(requirements):
        raise ValueError("Resultados e requisitos não correspondem.")
    per_requirement = []
    for row, requirement in zip(results, requirements):
        gold = requirement.get('acceptable_input_indices')
        if gold is None:
            status = 'não anotado'
        elif not isinstance(gold, list):
            raise ValueError("Anotação deve ser uma lista de input_index.")
        elif not gold:
            status = 'sem evidência anotada'
        else:
            status = 'positivo anotado'
        rank = None
        if status == 'positivo anotado':
            rank = next((position for position, evidence in enumerate(row['ranking'], 1)
                         if evidence['input_index'] in gold), None)
        ranking = row['ranking']
        margin = (ranking[0]['similarity'] - ranking[1]['similarity']) if len(ranking)>1 else None
        per_requirement.append({'id':row['id'], 'annotation_status':status,
                                'first_relevant_rank':rank,
                                'reciprocal_rank':(1/rank if rank else 0) if status=='positivo anotado' else None,
                                'top1_top2_margin':margin})
    positives=[item for item in per_requirement if item['annotation_status']=='positivo anotado']
    ranks=[item['first_relevant_rank'] for item in positives]
    mean=lambda values: float(np.mean(values)) if values else None
    return {'total_requirements':len(results), 'evaluated_positive_count':len(positives),
            'no_evidence_count':sum(item['annotation_status']=='sem evidência anotada' for item in per_requirement),
            'unannotated_count':sum(item['annotation_status']=='não anotado' for item in per_requirement),
            'hit_at_1':mean([rank==1 for rank in ranks]),
            'hit_at_3':mean([rank is not None and rank<=3 for rank in ranks]),
            'mrr':mean([1/rank if rank else 0 for rank in ranks]),
            'per_requirement':per_requirement}
