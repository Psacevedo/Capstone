# Calibracion secuencial Black-Litterman

## Ganadores por etapa
- stage1_familia_view: **Desempleo macro asumido** (`stage1_desempleo`), score robusto 0.595, Sharpe medio 1.579, delta Sharpe vs Markowitz 0.076.
- stage2_estructura_P: **Desempleo macro asumido** (`stage2_unemp_U0.04_B1.5`), score robusto 0.650, Sharpe medio 1.713, delta Sharpe vs Markowitz 0.009.
- stage3_intensidad_Q: **Desempleo macro asumido** (`stage3_q_scale_1.5`), score robusto 0.650, Sharpe medio 1.715, delta Sharpe vs Markowitz 0.010.
- stage4_confianza_Omega: **Desempleo macro asumido** (`stage4_conf_0.20`), score robusto 0.650, Sharpe medio 1.722, delta Sharpe vs Markowitz 0.017.
- stage5_tau: **Desempleo macro asumido** (`stage5_tau_0.200`), score robusto 0.976, Sharpe medio 1.730, delta Sharpe vs Markowitz 0.025.

## Configuracion final
- Familia: unemployment; desempleo asumido=4.0%; desempleo neutral=5.0%; beta macro=1.5; q_scale=1.5; confianza=0.2; tau=0.2. La matriz P favorece sectores ciclicos frente a defensivos bajo desempleo menor al neutral.

## Recomendacion por perfil
- con_pandemia / Arriesgado: Sharpe BL 1.71 vs Markowitz 1.17; mejora 46.7%; drawdown BL -11.9%; Recomendado.
- con_pandemia / Conservador: Sharpe BL 1.78 vs Markowitz 1.78; mejora 0.2%; drawdown BL -9.0%; Recomendado.
- con_pandemia / Muy arriesgado: Sharpe BL 1.08 vs Markowitz 0.71; mejora 51.7%; drawdown BL -24.7%; Recomendado.
- con_pandemia / Muy conservador: Sharpe BL 1.77 vs Markowitz 1.79; mejora -0.9%; drawdown BL -8.9%; No dominante.
- con_pandemia / Neutro: Sharpe BL 1.79 vs Markowitz 1.66; mejora 7.8%; drawdown BL -9.3%; Recomendado.
- sin_pandemia / Arriesgado: Sharpe BL 1.57 vs Markowitz 1.51; mejora 3.5%; drawdown BL -12.6%; Recomendado.
- sin_pandemia / Conservador: Sharpe BL 1.72 vs Markowitz 1.73; mejora -0.5%; drawdown BL -10.2%; No dominante.
- sin_pandemia / Muy arriesgado: Sharpe BL 1.16 vs Markowitz 1.20; mejora -3.6%; drawdown BL -22.3%; No dominante.
- sin_pandemia / Muy conservador: Sharpe BL 1.74 vs Markowitz 1.74; mejora 0.1%; drawdown BL -10.2%; Recomendado.
- sin_pandemia / Neutro: Sharpe BL 1.67 vs Markowitz 1.75; mejora -4.5%; drawdown BL -10.3%; No dominante.

## Validacion robusta final
- BL calibrado / Neutro: Sharpe medio 1.44, desv. 0.18, drawdown medio -11.1%.
- Markowitz base / Neutro: Sharpe medio 1.63, desv. 0.14, drawdown medio -13.5%.

## P4 posterior
- Markowitz base / sin_pandemia / Neutro: riqueza USD 2813, retiro 0.9%, utilidad empresa USD 194, score 2998.
- Markowitz base / sin_pandemia / Conservador: riqueza USD 2533, retiro 14.4%, utilidad empresa USD 198, score 2587.
- Markowitz base / con_pandemia / Neutro: riqueza USD 2389, retiro 0.7%, utilidad empresa USD 154, score 2536.
- BL calibrado / sin_pandemia / Conservador: riqueza USD 2457, retiro 14.9%, utilidad empresa USD 194, score 2501.
- Markowitz base / con_pandemia / Conservador: riqueza USD 2384, retiro 10.9%, utilidad empresa USD 191, score 2466.
- BL calibrado / con_pandemia / Conservador: riqueza USD 2393, retiro 13.7%, utilidad empresa USD 189, score 2445.
- BL calibrado / sin_pandemia / Neutro: riqueza USD 2306, retiro 0.9%, utilidad empresa USD 145, score 2442.
- BL calibrado / con_pandemia / Neutro: riqueza USD 2278, retiro 0.4%, utilidad empresa USD 142, score 2417.