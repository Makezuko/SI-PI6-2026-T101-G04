# Estado do projeto

O MVP recebe PDFs e requisitos revisados, aplica NER, anonimização e extração híbrida, recupera evidências por embeddings e cosseno e usa Qwen local para avaliar sustentação. A resposta é validada; a fórmula ponderada (obrigatório 2, desejável 1) produz aderência e ranking. Gemini fornece parecer textual opcional sem alterar a nota. O índice antigo de cossenos é apenas histórico.

A aplicação oferece vagas, currículos, evidências, intervalo provisório e persistência Supabase. Falhas contextuais impedem nova nota. Análises anteriores permanecem no banco e podem exigir reprocessamento. A decisão de entrevista continua independente.

Ainda são necessárias validação com currículos reais, confirmação das migrações e políticas RLS no Supabase real e controles de revisão humana das decisões. Prepare modelos e runtime conforme o [README](../README.md). Veja [avaliação contextual](avaliacao-contextual.md) e [integração](integracao-aderencia.md).

## Histórico de testes e diagnósticos

Em 17/11/2026, foram relatados testes de cálculo e integração e três erros em testes semânticos. Uma atualização posterior da versão documental 3.1 relatou 171 testes e os mesmos três erros; a data dessa atualização não foi registrada. Esses relatos descrevem versões anteriores e não validam a versão atual.
