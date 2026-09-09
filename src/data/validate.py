import os
import json


def corrigir_offset(content, texto_esperado, start_aproximado, janela=100):
    """
    Tenta encontrar a posição real do texto esperado dentro do content,
    buscando numa janela ao redor do start original.
    Retorna (novo_start, novo_end) ou None se não encontrar.
    """
    texto_esperado_limpo = texto_esperado.strip()
    inicio_busca = max(0, start_aproximado - janela)
    fim_busca = start_aproximado + janela

    trecho = content[inicio_busca:fim_busca + len(texto_esperado_limpo)]
    posicao_relativa = trecho.find(texto_esperado_limpo)

    if posicao_relativa == -1:
        return None

    novo_start = inicio_busca + posicao_relativa
    novo_end = novo_start + len(texto_esperado_limpo)
    return novo_start, novo_end


def validar_offsets(caminho_arquivo):
    """
    Verifica, para cada currículo e cada entidade anotada, se o texto
    entre content[start:end] bate exatamente com o texto anotado.
    Quando não bate, tenta recuperar o offset correto buscando o texto
    esperado numa janela próxima da posição original.
    """
    total_curriculos = 0
    total_entidades = 0
    entidades_ok_original = 0
    entidades_recuperadas = 0
    entidades_validadas = []
    entidades_descartadas = []

    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        for i, linha in enumerate(f):
            linha = linha.strip()
            if not linha:
                continue

            dado = json.loads(linha)
            content = dado.get("content", "")
            anotacoes = dado.get("annotation", [])

            total_curriculos += 1
            entidades_deste_curriculo = []

            for anotacao in anotacoes:
                labels = anotacao.get("label", [])
                label = labels[0] if labels else "SEM_LABEL"

                for ponto in anotacao.get("points", []):
                    total_entidades += 1
                    start = ponto.get("start")
                    end = ponto.get("end")
                    texto_esperado = ponto.get("text", "")

                    texto_real = content[start:end + 1]

                    if texto_real.strip() == texto_esperado.strip():
                        entidades_ok_original += 1
                        entidades_deste_curriculo.append({
                            "start": start,
                            "end": end + 1,
                            "label": label,
                        })
                        continue

                    resultado = corrigir_offset(content, texto_esperado, start, janela=300)

                    if resultado is not None:
                        novo_start, novo_end = resultado
                        entidades_recuperadas += 1
                        entidades_deste_curriculo.append({
                            "start": novo_start,
                            "end": novo_end,
                            "label": label,
                        })
                    else:
                        entidades_descartadas.append({
                            "linha": i,
                            "label": label,
                            "start": start,
                            "end": end,
                            "esperado": texto_esperado[:80],
                            "encontrado": texto_real[:80],
                        })

            entidades_validadas.append({
                "content": content,
                "entidades": entidades_deste_curriculo,
            })

    total_ok = entidades_ok_original + entidades_recuperadas

    print(f"Total de currículos: {total_curriculos}")
    print(f"Total de entidades: {total_entidades}")
    print(f"Entidades válidas originalmente: {entidades_ok_original}")
    print(f"Entidades recuperadas por realinhamento: {entidades_recuperadas}")
    print(f"Entidades descartadas (não recuperáveis): {len(entidades_descartadas)}")
    print(f"Taxa final de aproveitamento: {total_ok / total_entidades:.2%}")

    return entidades_validadas, entidades_descartadas


def salvar_processado(entidades_validadas, caminho_saida):
    """Salva os dados já validados/corrigidos em JSON, prontos para o treino."""
    pasta = os.path.dirname(caminho_saida)
    os.makedirs(pasta, exist_ok=True)

    with open(caminho_saida, "w", encoding="utf-8") as f:
        json.dump(entidades_validadas, f, ensure_ascii=False, indent=2)

    print(f"Dados processados salvos em: {caminho_saida}")


if __name__ == "__main__":
    from src.data.load import download_dataturks

    path = download_dataturks()
    caminho_arquivo = os.path.join(path, "Entity Recognition in Resumes.json")

    entidades_validadas, descartadas = validar_offsets(caminho_arquivo)

    print("\nExemplos de entidades descartadas:")
    for erro in descartadas[:5]:
        print(erro)

    caminho_saida = os.path.join("data", "processed", "dataturks_limpo.json")
    salvar_processado(entidades_validadas, caminho_saida)