# Cambios del docker  
- Cambiar la probabilidad de aceptación de rebalanceo y de abandono. Estamos ocupando la versión V1 de la probabilidad. Como se muestra en la carpeta “views_v1_plus” ubicada en “Entrega_3”.   
- Revisar la calibración de cada view, porque esto se hizo por separado para cada una. Se encuentra en la carpeta “views_v1_plus”  
- Cambiar la métrica de score P4 para rankear las views. Actualmente tenemos   
![score Pa a naveza terminal media + utilidad moresa media • capital nicial • tasa retiro](Attachments/69F46E12-9511-4E9B-9DB4-593C0D762998.png)  
  
Con estos resultados   
![Revisé views_vt_plus . Tomé como score principal la mejora del score Re promedio contra Markowitz, porque es](Attachments/EFF0AF9B-0BB8-44A2-AA3C-F5F1B02FA168.png)  
  
Para no mostrar tanta diferencia en la victoria de Momentum General, la función de score se podría plantear como:  
![Sco tun = medianacz (Wn4 +U8- Korou) - (WsKa+Uxk, - Korux))](Attachments/7602169A-DC09-4B1D-AA76-D86AF9EDA0AC.png)  
![la fórmula calla el score final de una view como Li mediana de tus mejoras P4 frente a Markowitz comparanda](Attachments/FD703997-B814-4DD6-910F-4E9C85A032F5.png)  
![Luego se compara BL contra Markowitz:](Attachments/FFBCAE16-0AB0-4ED6-922E-EE42816B1F00.png)  
  
Entregando como resultado:  
![Score con médiana](Attachments/AF499041-6735-4FCA-A776-757DD7FE3C57.png)  
  
- Revisar la limitación de acciones, que aún salen limitadas  
- Cambiar como gana dinero FinPUC, actualmente solo gana dinero por administración del saldo de los clientes. Se cobra un 0,5% de del saldo administrado de cliente activo  
- Cambiar la estructura de comisiones. Actualmente no hay comisiones, solo se gana por saldo administrado   
