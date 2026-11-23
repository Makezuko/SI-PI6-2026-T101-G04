# Aderência documental

O fluxo web recupera evidências por cosseno, submete-as ao Qwen e valida as respostas antes de calcular a aderência em `src/matching/adherence.py`. Condições manuais antigas não influenciam as decisões.

Cada requisito obrigatório pesa **2** e cada desejável pesa **1**:

```text
aderência = 100 × soma dos pesos atendidos / soma dos pesos de todos os requisitos
```

O cosseno não multiplica a contribuição. Pendências permanecem no denominador e geram intervalo provisório: o mínimo considera os pesos atendidos e o máximo também inclui os pendentes. Se todos estiverem pendentes, a interface não apresenta nota final. O ranking usa o mínimo confirmado, menor peso pendente e ID para desempate. Falha técnica não produz nota; ausência de evidência não demonstra incapacidade. Consulte [avaliação contextual](avaliacao-contextual.md).

## Experimento histórico: índice semântico 2.1

`src/matching/score.py` e `scripts/calcular_aderencia.py` preservam o experimento antigo, isolado do MVP. Ele usa a melhor similaridade de cosseno como multiplicador quando atinge 0,50; abaixo disso a contribuição é zero. Por padrão, distribui 90 pontos entre obrigatórios e 10 entre desejáveis. Este índice e sua ordenação não são utilizados pelo fluxo web atual e não são comparáveis à aderência documental.
