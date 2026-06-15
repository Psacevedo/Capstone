# Validacion tres horizontes Black-Litterman

## Ventanas
- con_pandemia / calibracion: 10 ventanas.
- con_pandemia / test_p4: 4 ventanas.
- con_pandemia / validacion: 3 ventanas.
- sin_pandemia / calibracion: 3 ventanas.
- sin_pandemia / test_p4: 1 ventanas.
- sin_pandemia / validacion: 1 ventanas.

## Ganadores de calibracion
- stage1_familia_view: stage1_mcap20_6m, Sharpe medio 0.718, delta Sharpe 0.023, score 0.500.
- stage2_estructura_P: stage2_mcap_L252_U40_K5_equal, Sharpe medio 0.909, delta Sharpe 0.214, score 0.950.
- stage3_intensidad_Q: stage3_q_scale_1.5, Sharpe medio 0.941, delta Sharpe 0.246, score 0.900.
- stage4_confianza_Omega: stage4_conf_0.80, Sharpe medio 0.958, delta Sharpe 0.263, score 0.750.
- stage5_tau: stage5_tau_0.200, Sharpe medio 0.963, delta Sharpe 0.268, score 0.850.

## Configuracion congelada
- family=marketcap_momentum; unemployment_assumed=4.00%; macro_beta=1.0; q_scale=1.5; confidence=0.8; tau=0.2.

## Validacion y test
- validacion / con_pandemia / Conservador: mejora Sharpe media -0.5%, delta drawdown -0.6%, pct recomendado 33.3%.
- validacion / con_pandemia / Muy conservador: mejora Sharpe media -0.8%, delta drawdown -0.4%, pct recomendado 33.3%.
- validacion / sin_pandemia / Muy conservador: mejora Sharpe media -1.2%, delta drawdown -0.3%, pct recomendado 0.0%.
- validacion / sin_pandemia / Conservador: mejora Sharpe media -2.0%, delta drawdown -0.1%, pct recomendado 0.0%.
- validacion / sin_pandemia / Neutro: mejora Sharpe media -5.9%, delta drawdown 0.0%, pct recomendado 0.0%.
- test_p4 / sin_pandemia / Conservador: mejora Sharpe media 1.5%, delta drawdown 1.1%, pct recomendado 100.0%.
- test_p4 / sin_pandemia / Muy conservador: mejora Sharpe media 0.7%, delta drawdown 0.3%, pct recomendado 100.0%.
- test_p4 / sin_pandemia / Muy arriesgado: mejora Sharpe media -1.1%, delta drawdown 4.7%, pct recomendado 0.0%.
- test_p4 / sin_pandemia / Neutro: mejora Sharpe media -2.2%, delta drawdown 2.9%, pct recomendado 0.0%.
- test_p4 / con_pandemia / Muy arriesgado: mejora Sharpe media -2.5%, delta drawdown -1.4%, pct recomendado 75.0%.

## Dinamica de portafolio
- BL calibrado / test_p4 / con_pandemia / Arriesgado: turnover medio 48.1%, N efectivo 38.9, sector HHI 0.267.
- BL calibrado / test_p4 / con_pandemia / Conservador: turnover medio 12.1%, N efectivo 118.5, sector HHI 0.157.
- BL calibrado / test_p4 / con_pandemia / Muy arriesgado: turnover medio 52.1%, N efectivo 11.5, sector HHI 0.474.
- BL calibrado / test_p4 / con_pandemia / Muy conservador: turnover medio 8.3%, N efectivo 114.5, sector HHI 0.165.
- BL calibrado / test_p4 / con_pandemia / Neutro: turnover medio 24.5%, N efectivo 104.7, sector HHI 0.149.
- BL calibrado / test_p4 / sin_pandemia / Arriesgado: turnover medio 54.2%, N efectivo 109.9, sector HHI 0.196.
- BL calibrado / test_p4 / sin_pandemia / Conservador: turnover medio 12.6%, N efectivo 238.6, sector HHI 0.140.
- BL calibrado / test_p4 / sin_pandemia / Muy arriesgado: turnover medio 61.4%, N efectivo 32.1, sector HHI 0.255.

## P4 limpio
- Markowitz base / sin_pandemia / Muy arriesgado: riqueza 2634, retiro 0.9%, utilidad 331, score 2957.
- BL calibrado / con_pandemia / Muy arriesgado: riqueza 2472, retiro 4.5%, utilidad 310, score 2737.
- BL calibrado / sin_pandemia / Muy arriesgado: riqueza 2300, retiro 0.9%, utilidad 297, score 2588.
- Markowitz base / con_pandemia / Muy arriesgado: riqueza 2292, retiro 3.2%, utilidad 291, score 2551.
- Markowitz base / sin_pandemia / Arriesgado: riqueza 2234, retiro 0.2%, utilidad 295, score 2527.
- Markowitz base / con_pandemia / Arriesgado: riqueza 2222, retiro 0.3%, utilidad 293, score 2512.
- Markowitz base / sin_pandemia / Neutro: riqueza 2080, retiro 0.4%, utilidad 290, score 2366.
- Markowitz base / con_pandemia / Neutro: riqueza 2013, retiro 0.4%, utilidad 284, score 2293.

Tiempo total: 423.6 segundos.