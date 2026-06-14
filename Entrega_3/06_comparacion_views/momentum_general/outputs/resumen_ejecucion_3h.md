# Validacion tres horizontes Black-Litterman

## Ventanas
- con_pandemia / calibracion: 10 ventanas.
- con_pandemia / test_p4: 4 ventanas.
- con_pandemia / validacion: 3 ventanas.
- sin_pandemia / calibracion: 3 ventanas.
- sin_pandemia / test_p4: 1 ventanas.
- sin_pandemia / validacion: 1 ventanas.

## Ganadores de calibracion
- stage1_familia_view: stage1_momentum, Sharpe medio 0.872, delta Sharpe 0.177, score 0.500.
- stage2_estructura_P: stage2_mom_L252_K10_rank, Sharpe medio 0.913, delta Sharpe 0.218, score 0.956.
- stage3_intensidad_Q: stage3_q_scale_1.5, Sharpe medio 0.937, delta Sharpe 0.242, score 0.750.
- stage4_confianza_Omega: stage4_conf_0.80, Sharpe medio 0.991, delta Sharpe 0.297, score 0.766.
- stage5_tau: stage5_tau_0.010, Sharpe medio 0.998, delta Sharpe 0.303, score 0.750.

## Configuracion congelada
- family=momentum; unemployment_assumed=4.00%; macro_beta=1.0; q_scale=1.5; confidence=0.8; tau=0.01.

## Validacion y test
- validacion / con_pandemia / Muy arriesgado: mejora Sharpe media 66.2%, delta drawdown -7.6%, pct recomendado 0.0%.
- validacion / con_pandemia / Arriesgado: mejora Sharpe media 33.6%, delta drawdown -7.7%, pct recomendado 0.0%.
- validacion / con_pandemia / Conservador: mejora Sharpe media 27.7%, delta drawdown -0.9%, pct recomendado 100.0%.
- validacion / con_pandemia / Neutro: mejora Sharpe media 27.7%, delta drawdown -3.0%, pct recomendado 33.3%.
- validacion / con_pandemia / Muy conservador: mejora Sharpe media 19.9%, delta drawdown -0.2%, pct recomendado 100.0%.
- test_p4 / con_pandemia / Muy arriesgado: mejora Sharpe media 75.6%, delta drawdown -13.4%, pct recomendado 0.0%.
- test_p4 / con_pandemia / Conservador: mejora Sharpe media 22.5%, delta drawdown -0.7%, pct recomendado 100.0%.
- test_p4 / con_pandemia / Arriesgado: mejora Sharpe media 22.2%, delta drawdown -9.2%, pct recomendado 0.0%.
- test_p4 / con_pandemia / Muy conservador: mejora Sharpe media 11.3%, delta drawdown -0.7%, pct recomendado 100.0%.
- test_p4 / con_pandemia / Neutro: mejora Sharpe media 9.2%, delta drawdown -4.5%, pct recomendado 0.0%.

## Dinamica de portafolio
- BL calibrado / test_p4 / con_pandemia / Arriesgado: turnover medio 42.1%, N efectivo 16.6, sector HHI 0.352.
- BL calibrado / test_p4 / con_pandemia / Conservador: turnover medio 22.1%, N efectivo 107.9, sector HHI 0.177.
- BL calibrado / test_p4 / con_pandemia / Muy arriesgado: turnover medio 39.7%, N efectivo 6.4, sector HHI 0.545.
- BL calibrado / test_p4 / con_pandemia / Muy conservador: turnover medio 12.7%, N efectivo 113.1, sector HHI 0.175.
- BL calibrado / test_p4 / con_pandemia / Neutro: turnover medio 33.3%, N efectivo 57.4, sector HHI 0.224.
- BL calibrado / test_p4 / sin_pandemia / Arriesgado: turnover medio 59.6%, N efectivo 39.7, sector HHI 0.293.
- BL calibrado / test_p4 / sin_pandemia / Conservador: turnover medio 21.4%, N efectivo 223.4, sector HHI 0.168.
- BL calibrado / test_p4 / sin_pandemia / Muy arriesgado: turnover medio 60.0%, N efectivo 17.4, sector HHI 0.303.

## P4 limpio
- BL calibrado / sin_pandemia / Muy arriesgado: riqueza 1005, retiro 45.3%, utilidad 1, score 553.
- Markowitz base / con_pandemia / Muy arriesgado: riqueza 1007, retiro 47.0%, utilidad 1, score 538.
- Markowitz base / sin_pandemia / Muy arriesgado: riqueza 1006, retiro 48.6%, utilidad 1, score 521.
- Markowitz base / sin_pandemia / Arriesgado: riqueza 1005, retiro 49.0%, utilidad 1, score 516.
- BL calibrado / sin_pandemia / Neutro: riqueza 1005, retiro 49.4%, utilidad 1, score 513.
- Markowitz base / con_pandemia / Arriesgado: riqueza 1006, retiro 49.7%, utilidad 1, score 510.
- BL calibrado / sin_pandemia / Arriesgado: riqueza 1005, retiro 51.2%, utilidad 1, score 494.
- Markowitz base / sin_pandemia / Neutro: riqueza 1005, retiro 51.9%, utilidad 1, score 488.

Tiempo total: 290.4 segundos.