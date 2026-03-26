# Conciliación contable por CODADM

Script en Python para detectar diferencias contables entre pares de códigos `CODADM`.

## Archivos

- `conciliacion_contable.py`: script principal.
- `equivalencias_codadm.csv`: tabla editable de equivalencias (`CODADM_A`, `CODADM_B`).
- `ejemplo_movimientos.csv`: ejemplo de movimientos con formato LATAM y delimitador `;`.
- `ejemplo_movimientos_diseno.csv`: ejemplo con otro diseño de columnas.
- `ejemplo_movimientos.txt`: ejemplo en TXT tabulado.

## Uso básico (CSV/TXT delimitado)

```bash
python conciliacion_contable.py \
  --movimientos ejemplo_movimientos.csv \
  --equivalencias equivalencias_codadm.csv \
  --salida reporte_conciliacion.csv
```

> El delimitador es `auto` por defecto (`;`, `,`, tab o `|`).

## Uso con otro diseño de input

Si tu archivo tiene otros nombres de columna, podés mapearlos con argumentos:

```bash
python conciliacion_contable.py \
  --movimientos ejemplo_movimientos_diseno.csv \
  --col-codadm 'CODIGO_ADMIN' \
  --col-monto 'IMPORTE_NETO' \
  --equivalencias equivalencias_codadm.csv \
  --salida reporte_conciliacion.csv
```

## Uso con TXT fijo (sin delimitadores)

Si tu TXT viene en líneas compactas (como el archivo del clearing), usá `--tipo-movimientos fijo` y un regex.

```bash
python conciliacion_contable.py \
  --tipo-movimientos fijo \
  --movimientos VISBPR1.TCRVISA.TS530100.RC00.N \
  --regex-fijo '^\s*\d+\s+([A-Z0-9]{3})(\d+\.\d{2})(\d+\.\d{2})' \
  --equivalencias equivalencias_codadm.csv \
  --salida reporte_conciliacion.csv
```

Regla del regex en modo `fijo`:
- Grupo 1 = `CODADM`
- Grupo 2 = `monto_1`
- Grupo 3 (opcional) = `monto_2`
- Neto calculado = `monto_1 - monto_2`

## Salidas

- `reporte_conciliacion*.csv`: montos por par y `DIFERENCIA`.
- `codadm_no_mapeados.csv`: códigos presentes en movimientos que no están en equivalencias.
- `diferencias_compensadas.csv`: diferencias que se compensan entre sí (+X con -X) y pendientes.

## Cómo agregar más CODADM

Agregá nuevas filas en `equivalencias_codadm.csv`:

```csv
CODADM_A,CODADM_B
AAA,BBB
```

Volvé a ejecutar el script.
