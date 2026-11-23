# Apresentação da aderência

## Causa e alteração

O HTML anterior misturava nós de texto, `strong`, quebras de linha e múltiplos
`details` dentro de `.req-item`. Essa classe usa `display:flex` com direção padrão
em linha e alinhamento central, comprimindo cada filho em uma coluna estreita.
A página também tinha largura máxima de 700 px e uma barra lateral fixa de 236 px
sem adaptação móvel.

Os requisitos agora usam artigos próprios em fluxo vertical, aproveitando a
largura disponível. `.req-item` permanece intacta para os outros componentes.
As regras móveis da estrutura são restritas a `.candidate-page`; a navegação
passa para cima do conteúdo. Cores, família de fontes e componentes existentes
foram preservados.

Cada artigo apresenta requisito completo, nível e status simples, justificativa
existente, primeira evidência citada (quando há), origem traduzida e contribuição
em pontos percentuais. Trechos acima de 360 caracteres têm uma prévia explicitada
por reticências e link que abre o único expansor do requisito. O texto completo,
demais evidências, citações, similaridades disponíveis, método e rastreamento
ficam nesse expansor. Campos técnicos vazios são omitidos. IDs da análise e da
execução ficam em Informações técnicas.

O resumo usa score, máximo e contagem de pendências já calculados. Não houve
alteração de modelos, decisões, fórmula, pesos ou persistência. O protetor
`candidate_text` atua apenas na exibição, ocultando identificadores pessoais
conhecidos e contatos nos textos da seção durante a triagem às cegas; não
modifica o resultado salvo. Mantém a política de identificação após aprovação.

## Verificação

Chrome headless real via Playwright, com HTML renderizado pelo Flask e CSS real,
sem banco ou autenticação remota. Fixture sintética: oito requisitos, evidência
de 22 linhas, outro trecho com palavra de 400 caracteres, IDs de 180 caracteres,
três estados e três pendências. Nomes e e-mails foram inseridos propositalmente
na evidência para testar anonimização.

Larguras verificadas: **1280, 390 e 320 px**, altura 900 px. Em todas:

- largura do documento igual à viewport; nenhum transbordamento nos artigos,
  evidências e informações técnicas, inclusive com todos os expansores abertos;
- texto completo preservado no expansor e link da prévia funcional;
- `summary` nativo alcançável por teclado;
- nome e e-mail sintéticos ausentes do HTML inteiro, inclusive detalhes fechados;
- resumo com 61,54%, três pendências e máximo condicionado de 84,62%.

Inspeção visual das capturas desktop e móvel confirmou leitura vertical,
bordas, cores e quebra de texto. A referência a Inter permanece no CSS; o teste
offline bloqueia recursos externos e pode usar a fonte alternativa configurada.
Não representa um teste com dados reais autenticados.

Reprodução (Playwright é ferramenta local de validação, não dependência da aplicação):

```powershell
.\.venv-contextual\Scripts\python.exe -m scripts.verificar_apresentacao_aderencia
.\.venv-contextual\Scripts\python.exe -m unittest discover -s tests
```

Capturas e medições: `reports/presentation/`, incluindo `1280-closed.png`,
`1280-open.png`, `390-closed.png`, `390-open.png`, `320-full.png` e `checks.json`.
O servidor foi iniciado com a alteração na porta 5002; basta abrir novamente
o candidato. Reprocessamento não é necessário para mudar a apresentação.
