# H08 - Plan de diagnóstico futuro, sin ejecutar

25/10/2026. BORRADOR PARA REVISIÓN. NO APROBADO, NO PREREGISTRADO, NO AUTORIZA CÁLCULOS. No hay trabajo programado ni simulaciones de cascadas iniciadas. El autor indicó declarar H08 como limitación y, si un revisor lo solicita, acordar primero un plan escrito, idealmente en la nube.

## Pregunta y alcance

Estimar la precisión Monte Carlo de las intensidades R6 basadas en J=500 trayectorias diarias y su propagación a IG y a las cotas bootstrap-t, manteniendo fijos datos, ajuste, dominio, corte, z(t,s), regla de decisión y resultado primario cerrado. El diagnóstico será posterior a resultados: no puede convertir R6 en una validación independiente, ciega o prospectiva ni reemplazar NEGATIVO NO ROBUSTO.

## Información disponible y faltante

Se verificaron los 1025 archivos diarios. Cada uno conserva ETAS, ETAS_X1 y la suma de descendientes de cada modelo, junto con semillas en el recibo. No conserva conteos por trayectoria, sumas de cuadrados ni covarianzas emparejadas. No es posible obtener una varianza muestral única a partir de esas sumas; tampoco es válido suponer descendientes Poisson independientes en un proceso de cascadas para rellenar la información faltante.

La precisión de la cola de las 1000 simulaciones de la prueba S es otro objeto. Su comprobación no cuantifica el error de las 500 trayectorias que construyeron los pronósticos y no cierra H08.

## Diseño que deberá fijarse antes de ejecutar

1. Congelar un protocolo fechado y sus hashes, con presupuesto, número de conjuntos independientes, J por conjunto, regla de semillas y criterios de parada por recursos. Esas elecciones quedan pendientes de revisión científica y estimación de coste; no se escogerán según el signo de IG o la proximidad de una cota a 0.05.
2. Preservar los pronósticos originales. Usar copias verificadas, una carpeta nueva y un manifiesto de entradas, motor, dependencias y resultados. No reoptimizar parámetros, seleccionar años ni modificar la geometría.
3. Distinguir dos objetivos: reconstruir las trayectorias originales para obtener momentos dentro de ese conjunto, y usar conjuntos independientes para evaluar repetibilidad entre conjuntos. Las mismas semillas por sí solas no constituyen una réplica independiente.
4. Mantener el emparejamiento ETAS/X1 por réplica y el tratamiento temporal original. Conservar conteos por trayectoria o estadísticas suficientes para las varianzas y covarianzas requeridas, con comprobaciones de equivalencia de medias frente a los archivos originales cuando se reproduzcan las semillas históricas.
5. Medir precisión de tasas por día/celda y de totales. Para IG, declarar previamente si se usa un método de propagación aproximado o recalculación sobre conjuntos independientes; informar sus supuestos y el posible sesgo de transformar estimadores mediante logaritmos. No confundir variabilidad entre eventos con error del simulador.
6. Si se estudia el efecto sobre bootstrap-t, fijar previamente su diseño anidado y separar la incertidumbre por muestreo de días del error de las intensidades simuladas. Repetir sólo bootstrap sobre la misma intensidad no estima H08. Preservar ambos L=7 y L=14 y sus reglas.
7. Informar resultados completos, incluidos fallos, todos los conjuntos, ceros y fracción final. No detenerse cuando una cota cruce 0.05. Presentar el diagnóstico como anexo de precisión, sin reescribir la decisión primaria.

## Entorno, coste y revisión

La generación histórica acumuló 17143.77110450009 segundos de reloj en los recibos diarios, unas 4.8 horas, sin que eso garantice el tiempo de una repetición. El coste aumenta con conjuntos adicionales y con el análisis anidado. Evaluar una ejecución portátil en la nube con límites de memoria, coste y puntos de reanudación antes de contratar o lanzar recursos. La selección de proveedor, transferencia de archivos y presupuesto no están autorizados por este borrador.

El revisor deberá aprobar el diseño concreto y sus supuestos; el autor decidirá si autoriza la ejecución. Mientras tanto, la frase del artículo sigue siendo: «El error Monte Carlo de las 500 trayectorias no está cuantificado (H08); no se usa para rescatar ni debilitar el resultado».
