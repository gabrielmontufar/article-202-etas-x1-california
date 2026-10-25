# R6 — preregistro propuesto (pendiente de la firma de Gabriel)

24/10/2026. Autor: Claude, a partir del borrador de Codex (`borrador_R6_20261023`). **NO
APROBADO TODAVÍA. No autoriza cálculos hasta que Gabriel lo apruebe por escrito en el chat.**

## Pregunta

¿Se mantiene el negativo de R5-Q2 (X1 no mejora a ETAS) cuando ETAS está mejor especificado,
es decir, con cotas ampliadas y réplicas intradiarias simuladas?

R6 es un **análisis de robustez** de un resultado ya conocido. El periodo 2024–2026 ya se
puntuó en Q2, así que R6 no es una prueba nueva ni virgen de X1, y se declarará así en el
artículo.

## Diseño (decisiones propuestas)

1. **Datos, máscara y épocas:** los mismos de R5 (keep_unknown, 4.296 celdas, M ≥ 2,5, 0–70 km).
   El ajuste se hace en 2016–2023 y la evaluación en [2024-01-01; 2026-10-21T03:21:46Z), con
   N = 2.122.
2. **Cotas nuevas:** n ∈ [0,01; 0,99] (subcrítico, < 1) y d0 ∈ [0,1; 50] km. Las demás cotas
   se mantienen como en R4.
3. **Ajuste:** se reajusta ETAS en 2016–2023 con el código R4 y las cotas nuevas (R4 ajustaba
   con n ≤ 0,95 y d0 ≥ 0,5 km). Arranques: los 5 de Q1 (referencia, vecino y Sobol 1/4/7,
   semilla 20261020). Se registra si el óptimo vuelve a caer en una cota y eso no detiene R6:
   se informa. Después se reajusta γ de X1 sobre ese ETAS con `cell_order=4`.
4. **Pronóstico diario con cascadas:** la historia se congela al inicio del día, se simulan
   las réplicas intradiarias por ETAS hasta el final del día y la media se toma sobre
   J = 500 simulaciones por día. La semilla de cada día es SHA-256('R6|'+fecha). Se usan las
   **mismas semillas** para ETAS y X1, lo que da variables comunes y reduce la varianza de la
   diferencia.
5. **Puntuación:** Poisson conjunta diaria e IG = (LL_X1 − LL_ETAS)/N, con el mismo bootstrap-t
   (L = 7 y 14, 9.999 remuestreos, semilla 20261020). Las pruebas N y S son descriptivas.
6. **Lectura preregistrada:**
   - **«Negativo robusto»** si el IC95 bootstrap-t de IG con L = 7 y con L = 14 queda por
     debajo de 0,05.
   - **«Negativo no robusto»** si alguno de los dos límites superiores es ≥ 0,05. En ese caso
     se informa y no se reinterpreta Q2.
   - Además se informa si la prueba N mejora respecto a R5 (lo esperado con cascadas).
7. **Controles numéricos:** los de R5 Q2 en su versión final (`5fd3fecd`), incluidos los
   controles agregados. Cualquier fallo detiene el proceso y se decide antes de abrir blancos.
8. **Orden:** ajuste → simulación y cubos → cierre y hash → puntuación. Se conservan todos los
   fallos.

## Coste y ejecución

El coste no está medido. Se estima en varias horas de ajuste más varias horas de simulación.
Codex no tiene uso hasta el 29/10. Claude prepara los scripts y Gabriel los lanza en Windows
con PowerShell, como en Q2. Otra opción es ejecutar en la nube de Claude, con una revisión
específica del cambio de ejecutor.

## Decisiones que Gabriel confirma al aprobar

- Las cotas n ≤ 0,99 y d0 ≥ 0,1 km.
- J = 500 simulaciones por día.
- Que R6 se presente como robustez, no como prueba nueva.
- Que el resultado se informe sea cual sea.

R4 sigue en HOLD_NO_SEAL_NO_FORECAST. No hay pronósticos operativos, sellos, publicación ni
correos.
