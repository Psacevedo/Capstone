# Modificaciones al informe FinPUC

## 1. Objetivo del cambio

El informe debe dejar de leerse como una acumulación de cifras y pasar a contar una historia clara:

1. Primero se explica qué problema de negocio se está resolviendo.
2. Luego se muestra cómo se calibra cada metodología.
3. Después se evalúa el efecto en el cliente.
4. Luego se incorpora el abandono semanal.
5. Finalmente se muestra la utilidad para FinPUC por saldo administrado activo.
6. Se cierra con una recomendación explícita: qué metodología usar, por qué y para qué perfil de riesgo.

La conclusión final no debe limitarse a describir resultados. Debe indicar claramente:

> La metodología recomendada es **[metodología ganadora]**, porque mejora el retorno del cliente respecto al caso base **Markowitz** en **[X% o X puntos porcentuales]**, mantiene una probabilidad de abandono semanal aceptable y permite a FinPUC capturar utilidad mediante una comisión mensual de **0,5% sobre el saldo activo administrado**. Esta metodología funciona mejor para los perfiles **[A, B y C]**.

---

## 2. Cambios transversales obligatorios

### 2.1. Cambiar el caso base

Eliminar el modelo **equiponderado** como caso base.

Desde ahora, el caso base debe ser:

> **Markowitz**

Donde diga “equiponderado”, “Equal Weight” o equivalente, debe reemplazarse por **Markowitz**, salvo que se esté mencionando solo como antecedente histórico eliminado.

---

### 2.2. Cambiar la lógica de comisión

Eliminar toda referencia a:

- Comisión de rebalanceo.
- Comisión por transacción.
- Comisión proporcional de 1%.
- Sensibilidad de comisión con valores de `K`.
- Búsqueda de comisión óptima.

La comisión correcta es:

> FinPUC cobra una comisión mensual de **0,5% sobre el saldo del cliente activo**.

La utilidad de la empresa no proviene de cada rebalanceo, sino de mantener clientes activos con saldo administrado.

Fórmula conceptual sugerida:

```text
Utilidad mensual FinPUC = 0,005 * saldo activo del cliente
```

Si se trabaja a nivel semanal, se debe convertir la comisión mensual a una tasa semanal equivalente o acumular la utilidad por meses, dejando explícito el criterio usado.

---

### 2.3. Cambiar la frecuencia operacional

Debe quedar explícito que:

- La **recomendación o rebalanceo** se realiza de forma **semestral**.
- El **abandono del cliente** se evalúa de forma **semanal**.

Frase sugerida:

> El sistema genera recomendaciones de inversión con frecuencia semestral. Sin embargo, el comportamiento del cliente se evalúa semanalmente, ya que el abandono puede ocurrir antes del siguiente rebalanceo si la experiencia acumulada del cliente supera su tolerancia al riesgo o pérdida.

---

### 2.4. Eliminar la optimización multiobjetivo con lambda

Eliminar toda referencia a:

- `lambda`
- `Score_lambda`
- Optimización multiobjetivo cliente empresa.
- Balance entre retorno del cliente y utilidad de FinPUC como objetivo de optimización.

El nuevo objetivo es:

> Maximizar el retorno esperado del cliente.

La utilidad de FinPUC se mide después, como consecuencia del saldo administrado activo, no como parte de la función objetivo principal.

---

### 2.5. Corregir las probabilidades de comportamiento

Las probabilidades actuales de comportamiento están mal planteadas.

Debe eliminarse la lógica de:

- Probabilidad de aceptación `P2`.
- Probabilidad de retiro construida con las fórmulas actuales si no corresponde al modelo usado.
- Comparación entre modelos v1, v1+ y v2.

El informe debe usar solo:

> La probabilidad de abandono definida en la carpeta `views_v1_plus`.

Como no se incluye en el material entregado la fórmula exacta de esa carpeta, el informe debe dejar un espacio controlado para insertar la ecuación real, no inventarla.

Texto recomendado:

> La probabilidad de abandono se calcula usando exclusivamente el modelo implementado en `views_v1_plus`. Este modelo representa la probabilidad semanal de que un cliente abandone la plataforma según su experiencia acumulada y el perfil de riesgo definido. A diferencia de versiones anteriores, no se compara contra modelos alternativos de abandono ni se incorpora una probabilidad separada de aceptación de recomendaciones.

Marcador técnico a completar:

```text
[Insertar aquí la fórmula exacta usada en views_v1_plus]
```

---

## 3. Modificaciones por sección

---

## 3.1. Sección 2.2, Ciclo operacional

### Problema detectado

La sección actual mezcla optimización semestral, evaluación semanal, aceptación de recomendaciones, comisión por transacción y retiro de fondos. Esa lógica ya no corresponde completamente al modelo actual.

### Reemplazo sugerido

```markdown
## 2.2. Ciclo operacional

El sistema opera en dos escalas temporales. En primer lugar, las recomendaciones de inversión se actualizan de forma semestral. En cada semestre se recalibran los parámetros del modelo con la información histórica disponible y se obtiene una nueva recomendación de portafolio para cada perfil de riesgo.

En segundo lugar, el comportamiento del cliente se evalúa semanalmente durante el horizonte de simulación. Esta separación es importante porque el cliente no necesariamente espera hasta el siguiente rebalanceo para abandonar la plataforma. Si durante las semanas intermedias su experiencia acumulada empeora y supera los umbrales definidos por su perfil, puede activarse la probabilidad de abandono semanal.

La utilidad de FinPUC se calcula a partir del saldo administrado de los clientes que permanecen activos. La empresa no cobra una comisión por rebalanceo ni por cada transacción ejecutada. En cambio, cobra una comisión mensual equivalente al 0,5% del saldo activo administrado. Por lo tanto, la sostenibilidad del negocio depende de dos elementos: que el cliente obtenga buenos retornos y que permanezca en la plataforma con saldo administrado.
```

---

## 3.2. Sección 2.5.5, Problema de negocio

### Problema detectado

La sección actual habla de comisión óptima `K` y de balance cliente empresa mediante `lambda`. Ambos elementos deben eliminarse.

### Nuevo enfoque

El problema de negocio ya no es encontrar una comisión óptima ni balancear dos objetivos dentro de una función ponderada. El problema ahora es seleccionar la metodología que maximiza el retorno del cliente y, como consecuencia, favorece la permanencia del cliente y el saldo administrado activo.

### Reemplazo sugerido

```markdown
## 2.5.5. Problema de negocio: retorno del cliente y sostenibilidad por saldo administrado

La fase actual del proyecto busca determinar qué metodología de recomendación entrega el mejor desempeño para el cliente bajo distintos perfiles de riesgo. El objetivo principal es maximizar el retorno esperado del cliente, considerando que una mejor experiencia de inversión debería reducir la probabilidad de abandono y aumentar el saldo administrado activo en la plataforma.

A diferencia de versiones anteriores, la utilidad de FinPUC no se modela como una comisión por transacción ni como una comisión de rebalanceo. La empresa obtiene ingresos mediante una comisión mensual fija equivalente al 0,5% del saldo activo administrado. Por esta razón, la utilidad de FinPUC depende directamente de la capacidad del sistema para mantener clientes activos y con saldos mayores en el tiempo.

El problema central es entonces:

> ¿Qué metodología de recomendación maximiza el retorno del cliente, mantiene controlada la probabilidad de abandono semanal y permite sostener una mayor base de saldo activo administrado?

Para responder esta pregunta se comparan el caso base Markowitz y las metodologías basadas en Black-Litterman con views calibradas de forma independiente. La comparación debe realizarse por perfil de riesgo, considerando retorno, riqueza terminal, abandono semanal y utilidad acumulada para FinPUC por saldo administrado activo.
```

---

## 3.3. Sección 2.5.6, Riesgos y limitaciones de los datos

### Acción requerida

Eliminar completamente esta sección.

### Texto a eliminar

```markdown
## 2.5.6. Riesgos y limitaciones de los datos
```

También deben eliminarse sus viñetas asociadas:

- Posible sesgo de supervivencia.
- Sobrerrepresentación del sector financiero.
- Tratamiento alternativo del periodo 2020-2022.
- Diferencias entre retornos usados en filtrado y análisis final.
- Pérdida de observaciones por uso de `join="inner"`.

---

## 3.4. Sección 3.6.2, Funciones de comportamiento del cliente

### Problema detectado

Las funciones actuales de comportamiento del cliente están mal planteadas. Además, ya no debe existir una probabilidad separada de aceptación de recomendación.

### Reemplazo sugerido

```markdown
## 3.6.2. Función de abandono del cliente

El comportamiento del cliente se modela únicamente mediante una probabilidad de abandono semanal. Esta probabilidad se calcula usando el modelo definido en `views_v1_plus`, el cual representa el riesgo de que un cliente abandone la plataforma según su experiencia acumulada y su perfil de riesgo.

En esta versión del modelo no se incorpora una probabilidad separada de aceptación de recomendaciones. La recomendación de portafolio se genera semestralmente y el cliente se mantiene activo mientras no se active el evento de abandono semanal.

La probabilidad de abandono debe interpretarse como una variable de retención: mientras menor sea el abandono, mayor será el saldo activo administrado y, por lo tanto, mayor será la utilidad esperada de FinPUC.

[Insertar aquí la fórmula exacta de abandono usada en `views_v1_plus`.]
```

### Cambios específicos

Eliminar las ecuaciones actuales de:

```text
P1(x1)
P2(x2)
```

Eliminar también las explicaciones asociadas a:

- Pérdida actual respecto al capital inicial si no corresponde al modelo final.
- Umbral de retorno ofrecido.
- Probabilidad de aceptación de recomendación.

---

## 3.5. Sección 3.9.2, Etapas de calibración

### Problema detectado

El Stage 1 actualmente selecciona una familia de view ganadora. Eso debe cambiar, porque ahora cada view se calibra de forma independiente.

### Reemplazo del Stage 1

```markdown
### Stage 1: Calibración independiente de views

En esta etapa no se selecciona una única familia de view ganadora. En cambio, se calibra cada view de forma independiente para que cada metodología sea evaluada bajo su mejor configuración posible.

Las views consideradas son:

1. Momentum general.
2. Desempleo macro.
3. Momentum top market-cap.

Para cada view se calibran sus parámetros propios dentro del modelo Black-Litterman. Luego, cada metodología calibrada se conserva para la etapa de simulación y comparación final. De esta forma, la evaluación posterior no depende de una selección prematura de views, sino de una comparación directa entre metodologías calibradas bajo el mismo protocolo experimental.
```

### Agregar tabla de calibración por view

Se debe agregar una tabla con los parámetros usados para cada view:

```markdown
| View | Parámetros calibrados | Mejor configuración | Métrica de calibración | Comentario |
|---|---|---:|---:|---|
| Momentum general | [completar] | [completar] | [completar] | [completar] |
| Desempleo macro | [completar] | [completar] | [completar] | [completar] |
| Momentum top market-cap | [completar] | [completar] | [completar] | [completar] |
```

### Cambio narrativo

Reemplazar frases del tipo:

> Se selecciona la familia con mayor score de calibración.

Por:

> Cada view se calibra de forma independiente y pasa a la etapa de simulación con su mejor configuración propia.

---

## 3.6. Sección 3.11.2, Diseño experimental

### Problema detectado

El diseño actual evalúa varios valores de comisión `K` y usa modelos que ya no corresponden, incluyendo el equiponderado.

### Reemplazo sugerido

```markdown
## 3.11.2. Diseño experimental

El diseño experimental evalúa el desempeño de las metodologías de recomendación bajo un horizonte de simulación de 260 semanas, equivalente a cinco años. Las recomendaciones de portafolio se actualizan de forma semestral, mientras que la probabilidad de abandono del cliente se evalúa semanalmente.

La comparación considera el caso base Markowitz y las metodologías Black-Litterman con views calibradas de forma independiente:

1. Markowitz, como caso base.
2. Black-Litterman con Momentum general calibrado.
3. Black-Litterman con Desempleo macro calibrado.
4. Black-Litterman con Momentum top market-cap calibrado.

Para cada metodología se ejecuta una simulación Monte Carlo con trayectorias semanales. En cada trayectoria se registra la evolución de la riqueza del cliente, el evento de abandono semanal, el saldo activo administrado y la utilidad acumulada de FinPUC.

La comisión de FinPUC se fija en 0,5% mensual sobre el saldo del cliente activo. No se evalúan escenarios alternativos de comisión, ya que la comisión está definida exógenamente para esta fase del proyecto.

Las métricas principales de comparación son:

- Retorno esperado del cliente.
- Riqueza terminal del cliente.
- Probabilidad o tasa de abandono semanal acumulada.
- Saldo activo administrado.
- Utilidad acumulada de FinPUC por comisión mensual sobre saldo activo.
- Estabilidad del ranking entre metodologías.
```

### Texto a eliminar

Eliminar la lista de valores:

```text
K ∈ {0.25%, 0.5%, 0.75%, 1%, 1.5%, 2%, 3%, 5%}
```

Eliminar también:

```text
Equiponderado
Comisión inicial de K% sobre C0
Comisión de K% sobre el 5% de la riqueza actual en cada recomendación aceptada
```

---

## 3.7. Sección 3.12, Optimización multiobjetivo de lambda

### Acción requerida

Eliminar la sección actual completa.

Debe eliminarse:

```markdown
## 3.12. Optimización multiobjetivo de λ
## 3.12.1. Objetivo
## 3.12.2. Formulación
```

También deben eliminarse las fórmulas:

```text
S_lambda(w) = lambda * f1(w) + (1 - lambda) * f2(w)
```

Y toda explicación asociada a:

- `lambda`
- `f1(w)` como retorno normalizado dentro de un score multiobjetivo.
- `f2(w)` como utilidad normalizada dentro de un score multiobjetivo.
- Normalización min-max para combinar retorno y utilidad.

### Nueva sección sugerida

```markdown
## 3.12. Métricas de desempeño económico

En esta versión del modelo no se utiliza una optimización multiobjetivo con parámetro lambda. La metodología recomendada se selecciona a partir del desempeño del cliente, medido principalmente por retorno esperado y riqueza terminal.

La utilidad de FinPUC se calcula como una métrica económica posterior, asociada al saldo activo administrado de los clientes que no abandonan la plataforma. Esta utilidad se obtiene aplicando una comisión mensual de 0,5% sobre el saldo administrado activo.

Por lo tanto, el análisis separa dos dimensiones:

1. Objetivo de recomendación: maximizar el retorno del cliente.
2. Métrica de negocio: estimar la utilidad de FinPUC a partir del saldo activo administrado.

Esta separación evita que el modelo recomiende portafolios que sacrifiquen el retorno del cliente para aumentar artificialmente la utilidad de la empresa.
```

---

## 3.8. Sección 3.13.1, Modelos de probabilidad de abandono

### Problema detectado

Ya no se comparan tres modelos de abandono. Solo se usa el modelo de `views_v1_plus`.

### Reemplazo sugerido

```markdown
## 3.13.1. Modelo de probabilidad de abandono

El análisis utiliza un único modelo de probabilidad de abandono semanal, correspondiente a la implementación definida en `views_v1_plus`.

A diferencia de versiones anteriores, no se comparan modelos alternativos de abandono. Por lo tanto, se eliminan las variantes v1, v1+ y v2 como experimentos separados. El objetivo es mantener una única regla de abandono consistente para todas las metodologías evaluadas.

Este modelo se aplica semanalmente durante las 260 semanas de simulación. Si el cliente abandona la plataforma, deja de aportar saldo activo administrado y, desde ese momento, FinPUC deja de recibir la comisión mensual asociada a ese cliente.

Las metodologías se comparan usando la misma función de abandono para evitar que las diferencias de resultado provengan de reglas de comportamiento distintas.
```

### Texto a eliminar

Eliminar la comparación entre:

- v1
- v1+
- v2

Eliminar también la frase:

> Los tres modelos se evalúan bajo el mismo protocolo de validación...

---

## 4. Modificaciones en resultados y análisis

---

## 4.1. Problema actual

La sección de resultados está demasiado densa en números. Falta un hilo conductor que explique qué significa cada resultado y cómo aporta a la recomendación final.

### Cambio requerido

Cada bloque de resultados debe seguir esta estructura:

```markdown
1. Qué se midió.
2. Qué resultado se obtuvo.
3. Qué significa para el cliente.
4. Qué significa para FinPUC.
5. Qué decisión permite tomar.
```

---

## 4.2. Estructura sugerida para la sección 8

```markdown
## 8. Resultados y análisis

### 8.1. Lectura general de los datos de retorno

Objetivo: explicar las características generales del universo de activos antes de comparar metodologías.

Debe incluir:
- Distribución de retornos.
- Volatilidad.
- Asimetría.
- Curtosis.
- Implicancia para la simulación.

Cierre interpretativo obligatorio:
> Estos resultados muestran que el universo de activos no se comporta como una distribución normal simple. Por eso, la comparación entre metodologías debe evaluarse no solo por retorno promedio, sino también por estabilidad, exposición a pérdidas y efecto sobre la permanencia del cliente.

### 8.2. Comparación de metodologías calibradas

Objetivo: comparar Markowitz contra las views Black-Litterman calibradas.

Metodologías:
- Markowitz.
- Black-Litterman con Momentum general calibrado.
- Black-Litterman con Desempleo macro calibrado.
- Black-Litterman con Momentum top market-cap calibrado.

Debe eliminarse el modelo equiponderado.

Cierre interpretativo obligatorio:
> La comparación muestra qué metodología mejora el caso base Markowitz y bajo qué perfil de riesgo esa mejora es más clara.

### 8.3. Resultados por perfil de riesgo

Objetivo: mostrar que la metodología recomendada puede cambiar según el perfil del cliente.

Debe incluir:
- Perfil conservador.
- Perfil moderado.
- Perfil agresivo.
- Retorno esperado.
- Riqueza terminal.
- Abandono semanal acumulado.
- Saldo activo administrado.

Cierre interpretativo obligatorio:
> El resultado relevante no es solo qué metodología tiene mayor retorno promedio, sino cuál mantiene un mejor equilibrio entre retorno, permanencia del cliente y saldo administrado activo.

### 8.4. Abandono semanal y retención

Objetivo: explicar cómo el abandono afecta el resultado del cliente y la utilidad de FinPUC.

Debe incluir:
- Tasa de abandono semanal.
- Abandono acumulado.
- Comparación entre metodologías.
- Impacto en saldo administrado.

Cierre interpretativo obligatorio:
> Una metodología con mayor retorno promedio puede no ser la mejor si aumenta demasiado el abandono. En cambio, una metodología robusta debe mejorar la experiencia del cliente sin elevar de forma excesiva la salida de usuarios.

### 8.5. Utilidad de FinPUC por saldo administrado activo

Objetivo: mostrar que la utilidad de la empresa depende de la permanencia del cliente y del saldo activo administrado.

Debe incluir:
- Comisión mensual de 0,5%.
- Saldo activo administrado.
- Utilidad acumulada por metodología.
- Comparación contra Markowitz.

Cierre interpretativo obligatorio:
> FinPUC no maximiza su utilidad cobrando por rebalanceos, sino manteniendo clientes activos con mayor saldo administrado. Por eso, la metodología recomendada debe mejorar el retorno del cliente y, al mismo tiempo, sostener la retención.

### 8.6. Recomendación final

Objetivo: cerrar el informe con una decisión clara.

Debe responder:
- Qué metodología se recomienda.
- Para qué perfil de riesgo.
- Cuánto mejora frente a Markowitz.
- Qué ocurre con el abandono.
- Qué impacto tiene en la utilidad de FinPUC.
```

---

## 5. Conclusión final sugerida

La conclusión debe escribirse con datos concretos una vez que estén disponibles. La estructura debe ser esta:

```markdown
## 9. Conclusiones

El análisis permite concluir que la metodología **[metodología recomendada]** es la alternativa más conveniente para **[perfil o perfiles de riesgo]**, ya que mejora el retorno del cliente frente al caso base **Markowitz** en **[X% o X puntos porcentuales]** y mantiene una tasa de abandono semanal de **[Y%]**.

Desde la perspectiva del cliente, esta metodología genera una mayor riqueza terminal esperada y una mejor relación entre retorno y riesgo. Esto es relevante porque el objetivo principal del recomendador es maximizar el retorno del cliente, no balancear artificialmente el resultado con la utilidad de la empresa.

Desde la perspectiva de FinPUC, la mejora también es favorable porque la empresa obtiene ingresos a partir del saldo activo administrado. Al mantener clientes activos con mayor saldo, la comisión mensual de 0,5% permite capturar una mayor utilidad acumulada sin introducir comisiones por transacción ni por rebalanceo.

En consecuencia, se recomienda utilizar **[metodología recomendada]** para los perfiles **[A, B y C]**. Para perfiles más conservadores, la recomendación debe validarse con especial cuidado en términos de abandono semanal, mientras que para perfiles de mayor tolerancia al riesgo puede priorizarse la metodología con mayor retorno esperado, siempre que no deteriore de forma significativa la retención.
```

---

## 6. Checklist de cambios concretos

| Elemento | Acción requerida |
|---|---|
| Storytelling | Reordenar resultados con hilo progresivo e interpretación parcial |
| Conclusión | Agregar recomendación final clara por metodología y perfil |
| Caso base | Eliminar equiponderado y usar Markowitz |
| Comisión | Eliminar comisión de rebalanceo y usar 0,5% mensual sobre saldo activo |
| `K` | Eliminar sensibilidad y optimización de comisión |
| `lambda` | Eliminar optimización multiobjetivo |
| Objetivo | Maximizar retorno del cliente |
| Utilidad FinPUC | Calcular como métrica posterior por saldo activo administrado |
| Recomendación | Semestral |
| Abandono | Semanal |
| Probabilidades | Usar solo modelo de abandono de `views_v1_plus` |
| P2 aceptación | Eliminar |
| Modelos v1, v1+, v2 | Eliminar comparación |
| Views Black-Litterman | Calibrar cada view por separado |
| Stage 1 | Cambiar de selección de view ganadora a calibración independiente |
| Views a reportar | Momentum general, desempleo macro, momentum top market-cap |
| Sección 2.5.6 | Eliminar completa |
| Resultados | Sacar equiponderado y comparar contra Markowitz |

---

## 7. Frases que deben reemplazarse

### Reemplazo 1

Antes:

```text
La empresa cobra una comisión proporcional k% = 1% sobre el monto transado.
```

Después:

```text
La empresa cobra una comisión mensual de 0,5% sobre el saldo activo administrado del cliente.
```

---

### Reemplazo 2

Antes:

```text
Se evalúan 8 valores de comisión K.
```

Después:

```text
La comisión se mantiene fija en 0,5% mensual sobre el saldo activo administrado, por lo que no se evalúan escenarios alternativos de comisión.
```

---

### Reemplazo 3

Antes:

```text
El Score P4 pondera retorno del cliente y utilidad de la empresa mediante lambda.
```

Después:

```text
La metodología se selecciona maximizando el retorno del cliente. La utilidad de FinPUC se reporta posteriormente como resultado del saldo activo administrado.
```

---

### Reemplazo 4

Antes:

```text
Se selecciona la familia de view con mayor score de calibración.
```

Después:

```text
Cada view se calibra de forma independiente y se evalúa posteriormente bajo el mismo protocolo de simulación.
```

---

### Reemplazo 5

Antes:

```text
Se comparan tres versiones del modelo de abandono: v1, v1+ y v2.
```

Después:

```text
Se utiliza únicamente el modelo de abandono semanal definido en `views_v1_plus`.
```

---

### Reemplazo 6

Antes:

```text
El caso base es el modelo equiponderado.
```

Después:

```text
El caso base es el modelo Markowitz.
```

---

## 8. Nota técnica pendiente

Para cerrar completamente el informe falta insertar la fórmula exacta de abandono semanal desde la carpeta:

```text
views_v1_plus
```

No conviene reconstruir esa fórmula desde memoria ni desde versiones anteriores, porque el comentario recibido indica explícitamente que las probabilidades de comportamiento actuales están mal.

