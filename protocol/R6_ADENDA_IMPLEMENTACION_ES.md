# R6 — adenda de implementación previa a cualquier cálculo

Confirmación humana recibida el 2026-10-24T02:00:53.978Z. Precisa el diseño registrado en c5ee258, cuyo texto original se conserva intacto. No se ha ejecutado ajuste, NLL, RNG científico, simulación, cubo ni puntuación R6.

## Seis arranques ETAS históricos

Referencia R4 bfcef175; best_x de Q1 oficial sensitivity_2016_2023 para n=0.99 y d0=0.3; Sobol originales índices 1/4/7, semilla 20261020, escalados a las cotas R6. Total seis; mismo L-BFGS-B y presupuesto R4. Q1 se usa solo para estos dos vectores iniciales explícitamente fijados, no para escoger cotas, criterios o periodos.

- q1_d0_0.3: C:\Users\gjm31\Documents\Codex\article202_panama_probabilistic_20261020\amendment_R5\intake_w4_w5_20261023\w3_original_verified\r5_q1\out_v3_W3\sensitivity_2016_2023\d0\point_0.3\POINT_RESULT.json; SHA-256 16db1c59cb9989460eee19d4291fde94320adeaad5b89cbd20f44158e426af5e; vector [-0.7280733819314348,0.95,0.4911580956591866,1.1036797706231738,-5.855097031305783,1.0809454056041954,1.711929619328556,-1.2039728043259361,0.5171067843541692]
- q1_n_0.99: C:\Users\gjm31\Documents\Codex\article202_panama_probabilistic_20261020\amendment_R5\intake_w2_20261023\w2_original_verified\r5_q1\out_v3_W2\sensitivity_2016_2023\n\point_0.99\POINT_RESULT.json; SHA-256 4f7db3d56784481dd8a106a26139f71b75db370129b14190b9a9e7709ad9decf; vector [-0.7107643180746691,0.99,0.48226658956822155,1.0915135728915752,-5.920913246158963,1.0778628984865832,2.067820921636907,-0.6931471805599453,0.4045781750169556]

## Descomposición del pronóstico diario

Parte analítica R5 (fondo más disparo de historia congelada), evaluada con los nuevos parámetros R6, más media de J=500 de eventos descendientes intradiarios de generaciones >=1. Los inmigrantes del fondo y los hijos directos de la historia anterior al día son generación 0: se simulan para sembrar cascadas, pero no se cuentan en el complemento. Se cuentan todas sus generaciones descendientes dentro de las 4296 celdas; las trayectorias se generan en el disco parental, también fuera de la máscara.

La z de X1 se calcula exclusivamente con la historia anterior al inicio del día, tanto en la parte analítica como en la simulación. No se actualiza con eventos intradiarios. Se declara esa limitación. Mismas semillas ETAS/X1. No medias Monte Carlo crudas, pseudocuentas, recortes o renormalización.

Esta precisión reemplaza la propuesta preliminar de z dinámica/media cruda; esa propuesta no se ejecutó. La parte analítica positiva evita medias cero. El término Rao-Blackwell suministrado por el autor se usa para esta descomposición; no implica una nueva prueba de validez independiente.

## Convención de semillas propuesta para revisión exacta

Fecha ISO diaria UTC YYYY-MM-DD; primeros 8 bytes SHA256(R6|+fecha), big-endian. SeedSequence(semilla diaria).spawn(500), un uint64 por réplica, idénticos para ambos modelos. No RNG se ejecuta durante esta preparación. Claude deberá revisar expresamente estos bytes antes del lanzamiento.

R4 sigue HOLD_NO_SEAL_NO_FORECAST. R6 es robustez posterior al resultado Q2 conocido, no validación ciega/prospectiva.
