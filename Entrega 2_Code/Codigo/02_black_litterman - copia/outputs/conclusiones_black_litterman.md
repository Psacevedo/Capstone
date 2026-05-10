# Conclusiones Black-Litterman

- Experimento central Sin pandemia / momentum_top20_6m: lidera Neutro con Sharpe rebalanceado 2.46, retorno total 72.3% y drawdown -12.9%.
- Experimento central Sin pandemia / desempleo: lidera Neutro con Sharpe rebalanceado 2.44, retorno total 63.1% y drawdown -10.4%.
- Experimento central Sin pandemia / momentum: lidera Muy conservador con Sharpe rebalanceado 2.38, retorno total 64.0% y drawdown -10.1%.
- Experimento central Con pandemia / momentum_top20_6m: lidera Neutro con Sharpe rebalanceado 2.38, retorno total 69.5% y drawdown -11.7%.
- Experimento central Con pandemia / desempleo: lidera Arriesgado con Sharpe rebalanceado 2.36, retorno total 71.9% y drawdown -13.3%.
- Experimento central Sin pandemia / momentum_top20_bottom20_1y: lidera Conservador con Sharpe rebalanceado 2.35, retorno total 63.1% y drawdown -10.7%.
- Experimento central Con pandemia / momentum_top20_bottom20_1y: lidera Neutro con Sharpe rebalanceado 2.20, retorno total 65.6% y drawdown -12.8%.
- Experimento central Con pandemia / momentum: lidera Conservador con Sharpe rebalanceado 2.06, retorno total 56.4% y drawdown -10.3%.

## Comparativa especifica de momentum market-cap
- En Sin pandemia, entre las variantes market-cap gana BL Momentum Top20 6M con perfil Neutro: Sharpe 2.46, retorno total 72.3%, volatilidad anual 11.9% y drawdown -12.9%. Frente al benchmark cambia Sharpe en +0.41, retorno total en -29.2%, volatilidad en -7.6% y drawdown en +9.0%.
- En Con pandemia, entre las variantes market-cap gana BL Momentum Top20 6M con perfil Neutro: Sharpe 2.38, retorno total 69.5%, volatilidad anual 11.9% y drawdown -11.7%. Frente al benchmark cambia Sharpe en +0.32, retorno total en -31.9%, volatilidad en -7.6% y drawdown en +10.2%.
- BL Momentum Top20 6M usa las 20 mayores capitalizaciones disponibles y separa 10 ganadoras contra 10 perdedoras por momentum de 126 dias; es la variante mas concentrada y reactiva.
- BL Momentum Top20-Bottom20 1Y usa las 40 mayores capitalizaciones disponibles y separa 20 ganadoras contra 20 perdedoras por momentum de 252 dias; es la variante mas diversificada y lenta.
- Comparacion contra Markowitz: la mayor mejora BL aparece en Con pandemia / desempleo / Arriesgado, con delta Sharpe 1.19.
- Benchmark: al ser equiponderado top-20, no depende de las views BL; su delta Sharpe promedio contra el CSV Markowitz es 0.0000.
- Justificacion comparativa: el benchmark suele capturar mas retorno bruto cuando concentra riesgo en las megacaps, mientras que las variantes BL se justifican si elevan Sharpe o reducen drawdown; por eso la conclusion prioriza rendimiento ajustado por riesgo y no solo retorno total.
- Rebalanceo: todas las views BL se actualizan cada segmento semestral de 126 dias habiles y se reportan metricas agregadas del camino rebalanceado.