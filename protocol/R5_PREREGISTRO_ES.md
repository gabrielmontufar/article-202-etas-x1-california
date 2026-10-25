# R5 — enmienda preregistrada: perfil de identificabilidad y prueba seudoprospectiva 2024–corte

Redactada por Claude el 23/10/2026 por encargo de Gabriel («sigamos investigando»),
**antes de cualquier cálculo R5**. Ningún resultado R5 existe al registrar este texto.

## 0. Lo que no cambia

- R4 queda cerrado como `HOLD_NO_SEAL_NO_FORECAST`. Ningún resultado R5 lo reescribe
  ni lo convierte en PASS. Sus fallos (cotas activas, potencia sin N*, cobertura
  0,920<0,93) se conservan y se reportan tal cual.
- Se mantienen el blanco (ComCat estándar M≥2,5, 0–70 km, unión terrestre SCSN/NCSN de
  4.296 celdas), los modelos ETAS y ETAS-X1, el código de verosimilitud, las cotas
  originales, el corte exclusivo 2026-10-21T03:21:46.320144Z y la captura admitida.
- Se mantienen los criterios: IG>0,05 nats/evento con el límite inferior del IC95 >0,05
  en bloques de 7 **y** 14 días; potencia ≥80 % (Wilson95 inferior); cobertura ≥0,93;
  falso éxito Wilson95 superior ≤0,07. No hay relajación, tercera opción inferencial
  ni selección posterior de escenario, bloque, época, variante o subperíodo.
- R5 no emite pronósticos, no sella, no publica, no envía correos y no activa R3.

## 1. Preguntas

- **Q1 Identificabilidad.** ¿Las cotas activas n=0,95 y d0=0,5 km reflejan que la
  verosimilitud empuja fuera del rango, o el perfil es plano dentro de él?
- **Q2 Habilidad fuera de muestra.** Con parámetros congelados de 2016–2023, ¿ETAS-X1
  supera a ETAS por más de 0,05 nats/evento en pronósticos diarios
  seudoprospectivos desde el 2024-01-01 hasta el corte?
- **Q3 Calibración.** ¿El IC bootstrap-t por bloques ya fijado en R4 alcanza cobertura
  ≥0,93 y potencia suficiente al N realizado de Q2, con ventana fija?

## 2. Q1 — perfil de verosimilitud (diagnóstico)

Épocas principal_2024 y sensitivity_2016_2023, con el mismo código y la misma máscara.
Se hacen dos perfiles unidimensionales; en cada punto se fija el parámetro y los demás
se reoptimizan dentro de sus cotas originales:

- n ∈ {0,70; 0,80; 0,85; 0,90; 0,93; 0,95; 0,97; 0,99}
- d0 (km) ∈ {0,10; 0,20; 0,30; 0,50; 0,75; 1,0; 2,0}

Arranques por punto: el cálido desde la referencia, el cálido desde el punto vecino ya
resuelto y los arranques 1, 4 y 7 del conjunto original de ocho. Gana el de menor NLL.
Todos se informan, con su convergencia.

El conjunto de perfil al 95 % es {ΔNLL ≤ 1,921}. Clasificación por parámetro y época:

- `IDENTIFICADO_DENTRO_DE_COTA`: el mínimo es interior y el conjunto queda dentro de las
  cotas originales.
- `LIMITADO_POR_COTA`: el conjunto alcanza o cruza una cota original.
- `NO_IDENTIFICADO`: ΔNLL ≤1,921 en todo el rango examinado.

Los valores n≥1 no se examinan, porque la región supercrítica no es estacionaria: es un
límite estructural del modelo, no un ajuste fino. Los valores d0<0,5 km quedan por
debajo del error típico de localización; se informan solo como diagnóstico y no se
adoptan para pronosticar. **Q1 no altera las cotas usadas en Q2.**

## 3. Q2 — prueba seudoprospectiva (no prospectiva)

**Ajuste.** ETAS usa la referencia congelada sensitivity_2016_2023 (cápsula
`bfcef1758a7f…`), sin reajuste. ETAS-X1 usa el ajuste gamma sobre la misma época con el
código R4. Si ese ajuste no existe, se calcula **una vez** sobre 2016–2023, se registra
su hash y solo después se abre la evaluación. No se usa el ajuste principal_2024.

**Evaluación.**
- Pronósticos diarios en las 4.296 celdas, para cada día del intervalo
  [2024-01-01, 2026-10-21) (1.024 días completos más la fracción final ya definida).
- Historia de condicionamiento: todos los eventos anteriores al inicio del día, con
  las reglas de padres y el margen de 500 km de R4.
- Puntuación: log-verosimilitud Poisson conjunta diaria, con ceros e integral incluidos.
  IG = (LL_X1 − LL_ETAS)/N.

**Decisión.** `PASS_SEUDOPROSPECTIVO` si se cumplen las tres condiciones:
1. IG puntual >0,05;
2. límite inferior del IC95 bootstrap-t >0,05 con L=7 **y** con L=14 (9.999 remuestreos,
   semilla 20261020);
3. Q3 = PASS.

Si no se cumplen las tres, el resultado es `FAIL_SEUDOPROSPECTIVO` o
`INCONCLUSIVO_POR_CALIBRACION` (cuando falla Q3), sin otra lectura.

**Descriptivos.** No cambian la decisión: pruebas N y S de consistencia para ambos
modelos, IG por año calendario y el percentil original de R4.

**Limitaciones declaradas de antemano.**
1. Los datos 2024–corte ya fueron capturados y usados para ajustar principal_2024, pero
   nunca se puntuaron pronósticos sobre ellos.
2. Si la forma de X1 se diseñó viendo el catálogo completo, Q2 es evidencia
   retrospectiva fuera de muestra, no prospectiva.
3. El cambio entre épocas de log(mu) y p penaliza a ambos modelos congelados y se
   informa.

Un PASS solo justifica proponer a Gabriel una prueba prospectiva preregistrada. No es
pronóstico, eficacia ni levantamiento del HOLD de R4.

## 4. Q3 — calibración al N realizado (antes de abrir puntuaciones)

Primero se **cuenta** el N realizado de eventos blanco en el intervalo de Q2 (contar no
es puntuar). Se estima del orden de 2.000: SCSN 1.070 + NCSN 1.011 estándar fuente.

Con ese N y ventana fija de 1.024 días (sin censura de 12 meses) se repiten los ocho
escenarios sintéticos de R4:
- mecanismos: tasa y dos celdas;
- dependencia: independiente y Cox de 7 días;
- IG verdadero: 0,05 y 0,10.

Etapas:
1. Cribado con 1.000 catálogos y 1.999 remuestreos, etiqueta `r5_screen`.
2. Validación independiente con 1.000 catálogos nuevos y 9.999 remuestreos, etiqueta
   `r5_independent_validation`.

Q3 = PASS si en la validación todos los escenarios cumplen: cobertura ≥0,93 con L=7 y
con L=14; potencia Wilson95 inferior ≥0,80 en IG=0,10; falso éxito Wilson95 superior
≤0,07 en IG=0,05. No se elige otro N ni otro bloque.

## 5. Orden obligatorio y entregables

1. Registrar este archivo por SHA-256 y commit local **antes de cualquier cálculo R5**.
2. Q3: contar N, hacer el cribado y la validación, y registrar el resultado.
3. Q1: perfiles en ambas épocas.
4. Q2: solo después del registro de Q3, generar y puntuar los pronósticos.
5. Producir `R5_DECISION.json`, las tablas CSV de perfil, IG, consistencia y
   calibración, y un informe en español para Gabriel. Conservar logs, semillas y
   manifiestos SHA-256, y todos los fallos y advertencias.

Cualquier fallo numérico se conserva y no autoriza cambiar el modelo, los datos, las
cotas o el presupuesto para obtener éxito.
