# Validacion tres horizontes Black-Litterman

## Ventanas
- con_pandemia / calibracion: 10 ventanas.
- con_pandemia / test_p4: 4 ventanas.
- con_pandemia / validacion: 3 ventanas.
- sin_pandemia / calibracion: 3 ventanas.
- sin_pandemia / test_p4: 1 ventanas.
- sin_pandemia / validacion: 1 ventanas.

## Ganadores de calibracion
- stage1_familia_view: stage1_desempleo, Sharpe medio 0.854, delta Sharpe 0.159, score 0.500.
- stage2_estructura_P: stage2_unemp_U0.04_B1.5, Sharpe medio 0.855, delta Sharpe 0.160, score 0.650.
- stage3_intensidad_Q: stage3_q_scale_1.5, Sharpe medio 0.855, delta Sharpe 0.160, score 0.650.
- stage4_confianza_Omega: stage4_conf_0.50, Sharpe medio 0.855, delta Sharpe 0.160, score 0.950.
- stage5_tau: stage5_tau_0.200, Sharpe medio 0.857, delta Sharpe 0.162, score 0.723.

## Configuracion congelada
- family=unemployment; unemployment_assumed=4.00%; macro_beta=1.5; q_scale=1.5; confidence=0.5; tau=0.2.

## Validacion y test
- validacion / con_pandemia / Muy arriesgado: mejora Sharpe media 3.0%, delta drawdown 6.3%, pct recomendado 66.7%.
- validacion / sin_pandemia / Muy conservador: mejora Sharpe media -0.4%, delta drawdown -0.0%, pct recomendado 0.0%.
- validacion / con_pandemia / Muy conservador: mejora Sharpe media -1.6%, delta drawdown -0.1%, pct recomendado 33.3%.
- validacion / sin_pandemia / Conservador: mejora Sharpe media -2.2%, delta drawdown 0.6%, pct recomendado 0.0%.
- validacion / con_pandemia / Conservador: mejora Sharpe media -3.0%, delta drawdown -0.1%, pct recomendado 33.3%.
- test_p4 / con_pandemia / Muy arriesgado: mejora Sharpe media 23.1%, delta drawdown 4.7%, pct recomendado 100.0%.
- test_p4 / con_pandemia / Arriesgado: mejora Sharpe media 19.9%, delta drawdown 7.6%, pct recomendado 75.0%.
- test_p4 / sin_pandemia / Arriesgado: mejora Sharpe media 3.2%, delta drawdown 6.1%, pct recomendado 100.0%.
- test_p4 / sin_pandemia / Muy conservador: mejora Sharpe media 0.2%, delta drawdown 0.1%, pct recomendado 100.0%.
- test_p4 / sin_pandemia / Conservador: mejora Sharpe media -0.6%, delta drawdown 0.8%, pct recomendado 0.0%.

## Dinamica de portafolio
- BL calibrado / test_p4 / con_pandemia / Arriesgado: turnover medio 7.0%, N efectivo 205.7, sector HHI 0.135.
- BL calibrado / test_p4 / con_pandemia / Conservador: turnover medio 6.2%, N efectivo 118.1, sector HHI 0.166.
- BL calibrado / test_p4 / con_pandemia / Muy arriesgado: turnover medio 9.9%, N efectivo 121.0, sector HHI 0.214.
- BL calibrado / test_p4 / con_pandemia / Muy conservador: turnover medio 6.3%, N efectivo 112.6, sector HHI 0.169.
- BL calibrado / test_p4 / con_pandemia / Neutro: turnover medio 6.4%, N efectivo 136.3, sector HHI 0.158.
- BL calibrado / test_p4 / sin_pandemia / Arriesgado: turnover medio 6.9%, N efectivo 360.5, sector HHI 0.124.
- BL calibrado / test_p4 / sin_pandemia / Conservador: turnover medio 7.0%, N efectivo 233.5, sector HHI 0.144.
- BL calibrado / test_p4 / sin_pandemia / Muy arriesgado: turnover medio 9.2%, N efectivo 163.3, sector HHI 0.178.

## P4 limpio
- BL calibrado / con_pandemia / Muy arriesgado: riqueza 1006, retiro 45.4%, utilidad 1, score 553.
- BL calibrado / sin_pandemia / Muy arriesgado: riqueza 1005, retiro 46.0%, utilidad 1, score 546.
- Markowitz base / con_pandemia / Muy arriesgado: riqueza 1006, retiro 47.4%, utilidad 1, score 533.
- BL calibrado / con_pandemia / Arriesgado: riqueza 1005, retiro 47.5%, utilidad 1, score 531.
- BL calibrado / sin_pandemia / Neutro: riqueza 1004, retiro 47.9%, utilidad 1, score 526.
- Markowitz base / sin_pandemia / Muy arriesgado: riqueza 1008, retiro 48.4%, utilidad 1, score 525.
- Markowitz base / con_pandemia / Arriesgado: riqueza 1005, retiro 48.6%, utilidad 1, score 520.
- BL calibrado / sin_pandemia / Arriesgado: riqueza 1004, retiro 49.2%, utilidad 1, score 513.

Tiempo total: 207.2 segundos.