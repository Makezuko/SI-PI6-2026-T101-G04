"""
Validação, correção e preparação das anotações do dataset Dataturks.

Esta etapa realiza:

1. Download e leitura do dataset original.
2. Verificação dos offsets de cada entidade.
3. Realinhamento automático de offsets incorretos.
4. Remoção de anotações exatamente duplicadas.
5. Resolução de entidades sobrepostas.
6. Conversão dos offsets para o padrão de fim exclusivo:
       content[start:end]
7. Salvamento do dataset limpo para o treinamento e data augmentation.

Por que resolver sobreposições?
-------------------------------
Modelos tradicionais de NER por token normalmente atribuem somente um rótulo
para cada token. Assim, duas entidades não podem ocupar os mesmos caracteres.

Quando duas entidades se sobrepõem, este script mantém o span mais completo,
isto é, a entidade com maior quantidade de caracteres. Essa decisão é
especialmente adequada ao Dataturks, que frequentemente anota seções completas,
como o bloco de Skills.
"""

import json
import os
from typing import Optional


def corrigir_offset(
    content: str,
    texto_esperado: str,
    start_aproximado: int,
    janela: int = 100,
) -> Optional[tuple[int, int]]:
    """
    Procura a posição correta de uma entidade próxima ao offset original.

    Parâmetros
    ----------
    content:
        Texto completo do currículo.

    texto_esperado:
        Texto que deveria existir na posição anotada.

    start_aproximado:
        Posição inicial informada pela anotação original.

    janela:
        Quantidade de caracteres pesquisados antes e depois da posição
        inicialmente indicada.

    Retorno
    -------
    Uma tupla no formato:

        (novo_start, novo_end)

    O novo_end é exclusivo, ou seja, a entidade pode ser recuperada com:

        content[novo_start:novo_end]

    Caso o texto não seja encontrado, retorna None.
    """
    texto_esperado_limpo = texto_esperado.strip()

    if not texto_esperado_limpo:
        return None

    inicio_busca = max(
        0,
        start_aproximado - janela,
    )

    fim_busca = min(
        len(content),
        start_aproximado
        + janela
        + len(texto_esperado_limpo),
    )

    trecho = content[inicio_busca:fim_busca]

    posicao_relativa = trecho.find(
        texto_esperado_limpo
    )

    if posicao_relativa == -1:
        return None

    novo_start = (
        inicio_busca
        + posicao_relativa
    )

    novo_end = (
        novo_start
        + len(texto_esperado_limpo)
    )

    return novo_start, novo_end


def intervalos_sobrepostos(
    entidade_a: dict,
    entidade_b: dict,
) -> bool:
    """
    Verifica se duas entidades ocupam pelo menos um caractere em comum.

    Os offsets utilizam fim exclusivo:

        [start, end)

    Portanto, os intervalos [0, 5) e [5, 10) são consecutivos, mas não
    estão sobrepostos.
    """
    return (
        entidade_a["start"] < entidade_b["end"]
        and entidade_b["start"] < entidade_a["end"]
    )


def remover_duplicidades(
    entidades: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Remove entidades exatamente duplicadas.

    Duas entidades são consideradas duplicadas quando possuem:

    - mesmo start;
    - mesmo end;
    - mesmo label.

    Retorna:
    - entidades únicas;
    - entidades duplicadas removidas.
    """
    entidades_unicas = []
    entidades_duplicadas = []
    chaves_encontradas = set()

    for entidade in entidades:
        chave = (
            entidade["start"],
            entidade["end"],
            entidade["label"],
        )

        if chave in chaves_encontradas:
            entidades_duplicadas.append(entidade)
            continue

        chaves_encontradas.add(chave)
        entidades_unicas.append(entidade)

    return entidades_unicas, entidades_duplicadas


def resolver_sobreposicoes(
    entidades: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Remove duplicidades e resolve entidades sobrepostas.

    Estratégia
    ----------
    1. Remove entidades exatamente duplicadas.
    2. Ordena as entidades da maior para a menor.
    3. Mantém primeiro os spans mais completos.
    4. Descarta uma entidade quando ela se sobrepõe a outra já mantida.
    5. Reordena o resultado pela posição no currículo.

    Essa transformação é necessária para preparar o dataset para um modelo
    de NER plano, no qual cada token recebe apenas um rótulo.

    Retorna
    -------
    entidades_mantidas:
        Entidades finais, sem duplicidade e sem sobreposição.

    entidades_duplicadas:
        Anotações exatamente duplicadas que foram removidas.

    conflitos_sobreposicao:
        Registros das entidades descartadas por sobreposição e das entidades
        que foram mantidas no lugar delas.
    """
    (
        entidades_unicas,
        entidades_duplicadas,
    ) = remover_duplicidades(entidades)

    # Ordena primeiro pelo tamanho do span, do maior para o menor.
    #
    # Se duas entidades tiverem o mesmo tamanho, a ordenação original
    # é preservada, porque o sorted() do Python é estável.
    entidades_por_tamanho = sorted(
        entidades_unicas,
        key=lambda entidade: -(
            entidade["end"]
            - entidade["start"]
        ),
    )

    entidades_mantidas = []
    conflitos_sobreposicao = []

    for candidata in entidades_por_tamanho:
        entidade_em_conflito = None

        for mantida in entidades_mantidas:
            if intervalos_sobrepostos(
                candidata,
                mantida,
            ):
                entidade_em_conflito = mantida
                break

        if entidade_em_conflito is None:
            entidades_mantidas.append(candidata)

        else:
            conflitos_sobreposicao.append(
                {
                    "entidade_descartada": candidata,
                    "entidade_mantida": entidade_em_conflito,
                }
            )

    # O treinamento e o augmentation precisam receber as entidades na
    # mesma ordem em que elas aparecem no currículo.
    entidades_mantidas.sort(
        key=lambda entidade: (
            entidade["start"],
            entidade["end"],
        )
    )

    return (
        entidades_mantidas,
        entidades_duplicadas,
        conflitos_sobreposicao,
    )


def validar_entidades_finais(
    content: str,
    entidades: list[dict],
) -> list[str]:
    """
    Valida as entidades depois das correções.

    Verifica:

    - offsets inteiros;
    - intervalos dentro do texto;
    - start menor que end;
    - entidade não vazia;
    - ausência de sobreposição.
    """
    erros = []

    entidades_ordenadas = sorted(
        entidades,
        key=lambda entidade: (
            entidade["start"],
            entidade["end"],
        ),
    )

    final_anterior = 0

    for indice, entidade in enumerate(
        entidades_ordenadas
    ):
        start = entidade.get("start")
        end = entidade.get("end")
        label = entidade.get("label")

        if not isinstance(start, int):
            erros.append(
                f"Entidade {indice}: start não é inteiro."
            )
            continue

        if not isinstance(end, int):
            erros.append(
                f"Entidade {indice}: end não é inteiro."
            )
            continue

        if not isinstance(label, str) or not label.strip():
            erros.append(
                f"Entidade {indice}: label inválido."
            )

        if start < 0:
            erros.append(
                f"Entidade {indice}: start negativo."
            )
            continue

        if end <= start:
            erros.append(
                f"Entidade {indice}: end menor ou igual ao start."
            )
            continue

        if end > len(content):
            erros.append(
                f"Entidade {indice}: end ultrapassa o tamanho do texto."
            )
            continue

        texto_entidade = content[start:end]

        if not texto_entidade.strip():
            erros.append(
                f"Entidade {indice}: texto vazio."
            )

        if start < final_anterior:
            erros.append(
                f"Entidade {indice}: sobreposição ainda existente."
            )

        final_anterior = max(
            final_anterior,
            end,
        )

    return erros


def validar_offsets(
    caminho_arquivo: str,
) -> tuple[list[dict], list[dict]]:
    """
    Valida e corrige todas as entidades do dataset.

    Para cada anotação:

    1. Verifica se content[start:end] corresponde ao texto anotado.
    2. Caso não corresponda, procura o texto em uma janela próxima.
    3. Converte o end original inclusivo para end exclusivo.
    4. Remove duplicidades.
    5. Resolve sobreposições.
    6. Executa uma validação final.

    Retorna:
    - currículos e entidades validadas;
    - entidades que não puderam ser recuperadas.
    """
    total_curriculos = 0
    total_entidades = 0

    entidades_ok_original = 0
    entidades_recuperadas = 0

    total_duplicadas_removidas = 0
    total_sobrepostas_descartadas = 0
    total_entidades_finais = 0

    entidades_validadas = []
    entidades_descartadas = []

    exemplos_duplicidades = []
    exemplos_sobreposicoes = []

    with open(
        caminho_arquivo,
        "r",
        encoding="utf-8",
    ) as arquivo:
        for numero_linha, linha in enumerate(arquivo):
            linha = linha.strip()

            if not linha:
                continue

            dado = json.loads(linha)

            content = dado.get(
                "content",
                "",
            )

            anotacoes = dado.get(
                "annotation",
                [],
            )

            total_curriculos += 1

            entidades_deste_curriculo = []

            for anotacao in anotacoes:
                labels = anotacao.get(
                    "label",
                    [],
                )

                label = (
                    labels[0]
                    if labels
                    else "SEM_LABEL"
                )

                label_invalido = (
                    not isinstance(label, str)
                    or not label.strip()
                    or label.strip().upper()
                    in {"UNKNOWN", "SEM_LABEL"}
                )

                pontos = anotacao.get(
                    "points",
                    [],
                )

                for ponto in pontos:
                    total_entidades += 1
                    if label_invalido:
                        entidades_descartadas.append(
                            {
                                "linha": numero_linha,
                                "motivo": "rótulo ausente ou desconhecido",
                                "label": label,
                                "start": ponto.get("start"),
                                "end": ponto.get("end"),
                                "esperado": ponto.get("text", "")[:80],
                            }
                        )
                        continue

                    start = ponto.get("start")
                    end = ponto.get("end")

                    texto_esperado = ponto.get(
                        "text",
                        "",
                    )

                    # Proteção contra anotações sem offsets.
                    if (
                        not isinstance(start, int)
                        or not isinstance(end, int)
                    ):
                        entidades_descartadas.append(
                            {
                                "linha": numero_linha,
                                "motivo": "offset ausente ou inválido",
                                "label": label,
                                "start": start,
                                "end": end,
                                "esperado": texto_esperado[:80],
                            }
                        )

                        continue

                    # No arquivo original do Dataturks, o end é inclusivo.
                    texto_real = content[
                        start:end + 1
                    ]

                    if (
                        texto_real.strip()
                        == texto_esperado.strip()
                    ):
                        entidades_ok_original += 1

                        entidades_deste_curriculo.append(
                            {
                                "start": start,

                                # Conversão para fim exclusivo.
                                "end": end + 1,

                                "label": label,
                            }
                        )

                        continue

                    resultado = corrigir_offset(
                        content=content,
                        texto_esperado=texto_esperado,
                        start_aproximado=start,
                        janela=300,
                    )

                    if resultado is not None:
                        novo_start, novo_end = resultado

                        entidades_recuperadas += 1

                        entidades_deste_curriculo.append(
                            {
                                "start": novo_start,
                                "end": novo_end,
                                "label": label,
                            }
                        )

                    else:
                        entidades_descartadas.append(
                            {
                                "linha": numero_linha,
                                "motivo": (
                                    "texto não encontrado para "
                                    "realinhamento"
                                ),
                                "label": label,
                                "start": start,
                                "end": end,
                                "esperado": texto_esperado[:80],
                                "encontrado": texto_real[:80],
                            }
                        )

            # -------------------------------------------------------------
            # REMOÇÃO DE DUPLICIDADES E SOBREPOSIÇÕES
            # -------------------------------------------------------------

            (
                entidades_sem_conflitos,
                duplicadas,
                conflitos,
            ) = resolver_sobreposicoes(
                entidades_deste_curriculo
            )

            total_duplicadas_removidas += len(
                duplicadas
            )

            total_sobrepostas_descartadas += len(
                conflitos
            )

            total_entidades_finais += len(
                entidades_sem_conflitos
            )

            # Guarda poucos exemplos para documentação e inspeção.
            for duplicada in duplicadas[:3]:
                exemplos_duplicidades.append(
                    {
                        "linha": numero_linha,
                        "entidade": duplicada,
                        "texto": content[
                            duplicada["start"]:
                            duplicada["end"]
                        ][:80],
                    }
                )

            for conflito in conflitos[:3]:
                descartada = conflito[
                    "entidade_descartada"
                ]

                mantida = conflito[
                    "entidade_mantida"
                ]

                exemplos_sobreposicoes.append(
                    {
                        "linha": numero_linha,
                        "descartada": {
                            **descartada,
                            "texto": content[
                                descartada["start"]:
                                descartada["end"]
                            ][:80],
                        },
                        "mantida": {
                            **mantida,
                            "texto": content[
                                mantida["start"]:
                                mantida["end"]
                            ][:80],
                        },
                    }
                )

            # -------------------------------------------------------------
            # VALIDAÇÃO FINAL DO CURRÍCULO
            # -------------------------------------------------------------

            erros_finais = validar_entidades_finais(
                content=content,
                entidades=entidades_sem_conflitos,
            )

            if erros_finais:
                raise ValueError(
                    "Falha após a resolução das entidades "
                    f"no currículo da linha {numero_linha}:\n"
                    + "\n".join(erros_finais)
                )

            entidades_validadas.append(
                {
                    "content": content,
                    "entidades": entidades_sem_conflitos,
                }
            )

    # Entidades recuperadas ou originalmente corretas antes da resolução
    # das duplicidades e sobreposições.
    total_offsets_recuperados = (
        entidades_ok_original
        + entidades_recuperadas
    )

    taxa_offsets_validos = (
        total_offsets_recuperados
        / total_entidades
        if total_entidades
        else 0
    )

    taxa_final_aproveitamento = (
        total_entidades_finais
        / total_entidades
        if total_entidades
        else 0
    )

    print("\n===== RESULTADO DA LIMPEZA =====")

    print(
        f"Total de currículos: "
        f"{total_curriculos}"
    )

    print(
        f"Total de entidades originais: "
        f"{total_entidades}"
    )

    print(
        f"Entidades válidas originalmente: "
        f"{entidades_ok_original}"
    )

    print(
        f"Entidades recuperadas por realinhamento: "
        f"{entidades_recuperadas}"
    )

    print(
        "Entidades não recuperáveis por offset: "
        f"{len(entidades_descartadas)}"
    )

    print(
        f"Taxa de offsets recuperados: "
        f"{taxa_offsets_validos:.2%}"
    )

    print(
        f"Entidades duplicadas removidas: "
        f"{total_duplicadas_removidas}"
    )

    print(
        f"Entidades sobrepostas descartadas: "
        f"{total_sobrepostas_descartadas}"
    )

    print(
        f"Entidades finais prontas para o NER: "
        f"{total_entidades_finais}"
    )

    print(
        f"Taxa final de aproveitamento após todos os tratamentos: "
        f"{taxa_final_aproveitamento:.2%}"
    )

    print(
        "\nExemplos de entidades duplicadas removidas:"
    )

    if exemplos_duplicidades:
        for exemplo in exemplos_duplicidades[:5]:
            print(exemplo)
    else:
        print("Nenhuma duplicidade exata encontrada.")

    print(
        "\nExemplos de sobreposições resolvidas:"
    )

    if exemplos_sobreposicoes:
        for exemplo in exemplos_sobreposicoes[:5]:
            print(exemplo)
    else:
        print("Nenhuma sobreposição encontrada.")

    return (
        entidades_validadas,
        entidades_descartadas,
    )


def salvar_processado(
    entidades_validadas: list[dict],
    caminho_saida: str,
) -> None:
    """
    Salva os currículos validados e sem sobreposição.

    O arquivo resultante utiliza offsets com fim exclusivo e está pronto
    para o split, data augmentation e conversão para o formato do modelo.
    """
    pasta = os.path.dirname(
        caminho_saida
    )

    os.makedirs(
        pasta,
        exist_ok=True,
    )

    with open(
        caminho_saida,
        "w",
        encoding="utf-8",
    ) as arquivo:
        json.dump(
            entidades_validadas,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"\nDados processados salvos em: "
        f"{caminho_saida}"
    )


if __name__ == "__main__":
    from src.data.load import download_dataturks

    caminho_dataset = download_dataturks()

    caminho_arquivo = os.path.join(
        caminho_dataset,
        "Entity Recognition in Resumes.json",
    )

    (
        entidades_validadas,
        entidades_descartadas,
    ) = validar_offsets(
        caminho_arquivo
    )

    print(
        "\nExemplos de entidades não recuperáveis:"
    )

    if entidades_descartadas:
        for erro in entidades_descartadas[:5]:
            print(erro)
    else:
        print(
            "Todas as entidades tiveram offsets recuperáveis."
        )

    caminho_saida = os.path.join(
        "data",
        "processed",
        "dataturks_limpo.json",
    )

    salvar_processado(
        entidades_validadas,
        caminho_saida,
    )