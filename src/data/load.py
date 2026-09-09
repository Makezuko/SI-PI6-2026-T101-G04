import os
import json
import kagglehub


def download_dataturks():
    """Baixa o dataset dataturks/resume-entities-for-ner via kagglehub."""
    path = kagglehub.dataset_download("dataturks/resume-entities-for-ner")
    print("Path to dataset files:", path)
    return path


def inspecionar_pasta(path):
    """Lista os arquivos baixados e seus tamanhos."""
    print("Arquivos encontrados:")
    for item in os.listdir(path):
        caminho_completo = os.path.join(path, item)
        tamanho = os.path.getsize(caminho_completo)
        print(f"  {item} — {tamanho} bytes")


def inspecionar_conteudo(caminho_arquivo, n_linhas=2):
    """Mostra as primeiras linhas de um arquivo de texto/JSON Lines."""
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        for i, linha in enumerate(f):
            if i >= n_linhas:
                break
            print(f"--- Linha {i} ---")
            print(linha[:500])
            print()


def inspecionar_estrutura(caminho_arquivo, n_linhas=1):
    """Mostra as chaves do JSON e a estrutura das anotações de entidade."""
    with open(caminho_arquivo, "r", encoding="utf-8") as f:
        for i, linha in enumerate(f):
            if i >= n_linhas:
                break
            dado = json.loads(linha)
            print(f"--- Linha {i} ---")
            print("Chaves encontradas:", list(dado.keys()))
            print()
            print("Trecho do content:", dado["content"][:200])
            print()
            print("Estrutura da anotação (primeiro item):")
            print(json.dumps(dado["annotation"][0], indent=2, ensure_ascii=False))
            print()
            print("Total de entidades anotadas nesse currículo:", len(dado["annotation"]))


if __name__ == "__main__":
    path = download_dataturks()
    inspecionar_pasta(path)

    caminho_arquivo = os.path.join(path, "Entity Recognition in Resumes.json")
    inspecionar_estrutura(caminho_arquivo)