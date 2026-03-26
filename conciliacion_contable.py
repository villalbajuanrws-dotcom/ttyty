#!/usr/bin/env python3
"""
Conciliación contable por CODADM.

Uso rápido:
  python conciliacion_contable.py \
    --movimientos movimientos.csv \
    --equivalencias equivalencias_codadm.csv \
    --salida reporte_conciliacion.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
import re


@dataclass
class FilaConciliacion:
    codadm_a: str
    monto_a: Decimal
    codadm_b: str
    monto_b: Decimal

    @property
    def diferencia(self) -> Decimal:
        # Si un banco cobra (+) y otro paga (-), el cierre debería ser 0.
        return self.monto_a + self.monto_b


@dataclass
class Compensacion:
    codadm_a_1: str
    codadm_b_1: str
    diferencia_1: Decimal
    codadm_a_2: str
    codadm_b_2: str
    diferencia_2: Decimal

    @property
    def saldo(self) -> Decimal:
        return self.diferencia_1 + self.diferencia_2


def parse_numero_latam(valor: str) -> Decimal:
    """Convierte números estilo LATAM a Decimal."""
    texto = valor.strip()
    if not texto:
        return Decimal("0")

    if "." in texto and "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return Decimal(texto)
    except InvalidOperation as exc:
        raise ValueError(f"No se pudo parsear el monto '{valor}'.") from exc


def formato_latam(numero: Decimal) -> str:
    """Formatea Decimal con miles '.' y decimal ',' (2 decimales)."""
    cuantizado = numero.quantize(Decimal("0.01"))
    signo = "-" if cuantizado < 0 else ""
    absoluto = abs(cuantizado)

    entero, decimales = f"{absoluto:.2f}".split(".")
    grupos: List[str] = []
    while entero:
        grupos.append(entero[-3:])
        entero = entero[:-3]
    entero_formateado = ".".join(reversed(grupos))
    return f"{signo}{entero_formateado},{decimales}"




def detectar_delimitador(path: Path, preferido: str) -> str:
    """Detecta delimitador cuando se usa --delim-mov auto / --delim-eq auto."""
    if preferido.lower() != "auto":
        return preferido

    muestra = path.read_text(encoding="utf-8-sig", errors="ignore")[:4096]
    candidatos = [";", ",", "\t", "|"]

    try:
        dialect = csv.Sniffer().sniff(muestra, delimiters="".join(candidatos))
        return dialect.delimiter
    except csv.Error:
        # fallback: elegimos el delimitador que más apariciones tenga en la cabecera
        primera = muestra.splitlines()[0] if muestra.splitlines() else ""
        elegido = max(candidatos, key=lambda d: primera.count(d))
        return elegido if primera.count(elegido) > 0 else ";"

def leer_movimientos(
    path: Path,
    delimitador: str = ",",
    columna_codadm: str = "CODADM",
    columna_monto: str = "MONTO NETO",
) -> Dict[str, Decimal]:
    totales: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimitador)
        campos = {c.strip().upper(): c for c in (reader.fieldnames or [])}

        key_codadm = columna_codadm.strip().upper()
        key_monto = columna_monto.strip().upper()

        if key_codadm not in campos or key_monto not in campos:
            disponibles = ", ".join(reader.fieldnames or [])
            raise ValueError(
                f"No encontré columnas '{columna_codadm}' y/o '{columna_monto}'. "
                f"Columnas disponibles: {disponibles}"
            )

        for fila in reader:
            codadm = str(fila[campos[key_codadm]]).strip()
            monto = parse_numero_latam(str(fila[campos[key_monto]]))
            if codadm:
                totales[codadm] += monto

    return dict(totales)


def leer_movimientos_fijos(path: Path, regex_linea: str) -> Dict[str, Decimal]:
    """
    Lee archivos TXT sin delimitador (formato fijo) usando regex.

    El regex debe capturar:
      - grupo 1: CODADM
      - grupo 2: monto_1
      - grupo 3 (opcional): monto_2

    Si existe monto_2, se calcula neto = monto_1 - monto_2.
    """
    patron = re.compile(regex_linea)
    totales: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
        for linea in f:
            m = patron.search(linea)
            if not m:
                continue

            codadm = m.group(1).strip()
            monto_1 = Decimal(m.group(2))
            if m.lastindex and m.lastindex >= 3 and m.group(3):
                monto_2 = Decimal(m.group(3))
                neto = monto_1 - monto_2
            else:
                neto = monto_1

            if codadm:
                totales[codadm] += neto

    return dict(totales)


def leer_equivalencias(path: Path, delimitador: str = ",") -> List[Tuple[str, str]]:
    pares: List[Tuple[str, str]] = []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimitador)
        campos = {c.strip().upper(): c for c in (reader.fieldnames or [])}

        if "CODADM_A" not in campos or "CODADM_B" not in campos:
            raise ValueError(
                "El archivo de equivalencias debe tener columnas 'CODADM_A' y 'CODADM_B'."
            )

        for fila in reader:
            a = str(fila[campos["CODADM_A"]]).strip()
            b = str(fila[campos["CODADM_B"]]).strip()
            if a and b:
                pares.append((a, b))

    return pares


def construir_conciliacion(
    totales: Dict[str, Decimal], equivalencias: Iterable[Tuple[str, str]]
) -> List[FilaConciliacion]:
    filas: List[FilaConciliacion] = []

    for cod_a, cod_b in equivalencias:
        filas.append(
            FilaConciliacion(
                codadm_a=cod_a,
                monto_a=totales.get(cod_a, Decimal("0")),
                codadm_b=cod_b,
                monto_b=totales.get(cod_b, Decimal("0")),
            )
        )

    return filas


def detectar_compensaciones(diferencias_no_cero: List[FilaConciliacion]) -> Tuple[List[Compensacion], List[FilaConciliacion]]:
    """
    Busca pares de diferencias opuestas (mismo importe absoluto y signo contrario).

    Ejemplo: +22.105,66 se compensa con -22.105,66.
    """
    bucket: Dict[Decimal, List[FilaConciliacion]] = defaultdict(list)
    compensadas: List[Compensacion] = []
    no_compensadas: List[FilaConciliacion] = []

    for fila in diferencias_no_cero:
        clave = fila.diferencia.quantize(Decimal("0.01"))
        opuesta = (-clave).quantize(Decimal("0.01"))

        if bucket[opuesta]:
            pareja = bucket[opuesta].pop()
            compensadas.append(
                Compensacion(
                    codadm_a_1=pareja.codadm_a,
                    codadm_b_1=pareja.codadm_b,
                    diferencia_1=pareja.diferencia,
                    codadm_a_2=fila.codadm_a,
                    codadm_b_2=fila.codadm_b,
                    diferencia_2=fila.diferencia,
                )
            )
        else:
            bucket[clave].append(fila)

    for pendientes in bucket.values():
        no_compensadas.extend(pendientes)

    return compensadas, no_compensadas


def escribir_reporte(path: Path, filas: List[FilaConciliacion]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["CODADM_A", "MONTO NETO A", "CODADM_B", "MONTO NETO B", "DIFERENCIA"])
        for fila in filas:
            writer.writerow(
                [
                    fila.codadm_a,
                    formato_latam(fila.monto_a),
                    fila.codadm_b,
                    formato_latam(fila.monto_b),
                    formato_latam(fila.diferencia),
                ]
            )


def escribir_no_mapeados(path: Path, totales: Dict[str, Decimal], equivalencias: List[Tuple[str, str]]) -> None:
    mapeados = {c for par in equivalencias for c in par}
    no_mapeados = sorted(
        ((cod, monto) for cod, monto in totales.items() if cod not in mapeados),
        key=lambda x: x[0],
    )

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["CODADM", "MONTO NETO"])
        for cod, monto in no_mapeados:
            writer.writerow([cod, formato_latam(monto)])


def escribir_compensaciones(path: Path, compensadas: List[Compensacion], no_compensadas: List[FilaConciliacion]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "CODADM_A_1",
                "CODADM_B_1",
                "DIFERENCIA_1",
                "CODADM_A_2",
                "CODADM_B_2",
                "DIFERENCIA_2",
                "SALDO",
                "ESTADO",
            ]
        )

        for c in compensadas:
            writer.writerow(
                [
                    c.codadm_a_1,
                    c.codadm_b_1,
                    formato_latam(c.diferencia_1),
                    c.codadm_a_2,
                    c.codadm_b_2,
                    formato_latam(c.diferencia_2),
                    formato_latam(c.saldo),
                    "COMPENSADA",
                ]
            )

        for fila in no_compensadas:
            writer.writerow(
                [
                    fila.codadm_a,
                    fila.codadm_b,
                    formato_latam(fila.diferencia),
                    "",
                    "",
                    "",
                    formato_latam(fila.diferencia),
                    "PENDIENTE",
                ]
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Concilia montos por equivalencias de CODADM y detecta diferencias contables."
    )
    parser.add_argument("--movimientos", required=True, type=Path, help="CSV de movimientos.")
    parser.add_argument(
        "--tipo-movimientos",
        choices=["csv", "fijo"],
        default="csv",
        help="Formato de movimientos: csv (con delimitador) o fijo (TXT sin delimitadores).",
    )
    parser.add_argument(
        "--equivalencias",
        required=True,
        type=Path,
        help="CSV editable de pares CODADM_A/CODADM_B.",
    )
    parser.add_argument("--salida", required=True, type=Path, help="CSV de conciliación.")
    parser.add_argument(
        "--salida-no-mapeados",
        type=Path,
        default=Path("codadm_no_mapeados.csv"),
        help="CSV con CODADM presentes en movimientos pero no mapeados.",
    )
    parser.add_argument(
        "--salida-compensaciones",
        type=Path,
        default=Path("diferencias_compensadas.csv"),
        help="CSV con diferencias compensadas entre sí y pendientes.",
    )
    parser.add_argument(
        "--delim-mov",
        default="auto",
        help="Delimitador de movimientos (coma, punto y coma, tab, pipe o auto).",
    )
    parser.add_argument(
        "--col-codadm",
        default="CODADM",
        help="Nombre de columna de CODADM en movimientos (por defecto: CODADM).",
    )
    parser.add_argument(
        "--col-monto",
        default="MONTO NETO",
        help="Nombre de columna de monto en movimientos (por defecto: MONTO NETO).",
    )
    parser.add_argument(
        "--regex-fijo",
        default=r"^\s*\d+\s+([A-Z0-9]{3})(\d+\.\d{2})(\d+\.\d{2})",
        help=(
            "Regex para tipo 'fijo'. Grupo1=CODADM, grupo2=monto_1, "
            "grupo3 opcional=monto_2 (neto=monto_1-monto_2)."
        ),
    )
    parser.add_argument(
        "--delim-eq",
        default="auto",
        help="Delimitador de equivalencias (coma, punto y coma, tab, pipe o auto).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    delim_mov = detectar_delimitador(args.movimientos, args.delim_mov)
    delim_eq = detectar_delimitador(args.equivalencias, args.delim_eq)

    if args.tipo_movimientos == "csv":
        totales = leer_movimientos(
            args.movimientos,
            delimitador=delim_mov,
            columna_codadm=args.col_codadm,
            columna_monto=args.col_monto,
        )
    else:
        totales = leer_movimientos_fijos(args.movimientos, args.regex_fijo)
    equivalencias = leer_equivalencias(args.equivalencias, delimitador=delim_eq)

    filas = construir_conciliacion(totales, equivalencias)
    escribir_reporte(args.salida, filas)
    escribir_no_mapeados(args.salida_no_mapeados, totales, equivalencias)

    diferencias_no_cero = [fila for fila in filas if fila.diferencia != 0]
    compensadas, pendientes = detectar_compensaciones(diferencias_no_cero)
    escribir_compensaciones(args.salida_compensaciones, compensadas, pendientes)

    print(f"Delimitador movimientos: {repr(delim_mov)}")
    print(f"Delimitador equivalencias: {repr(delim_eq)}")
    print(f"Filas conciliadas: {len(filas)}")
    print(f"Diferencias no cero: {len(diferencias_no_cero)}")
    print(f"Diferencias compensadas: {len(compensadas)}")
    print(f"Diferencias pendientes: {len(pendientes)}")
    print(f"Reporte: {args.salida}")
    print(f"No mapeados: {args.salida_no_mapeados}")
    print(f"Compensaciones: {args.salida_compensaciones}")

    if pendientes:
        print("\nDiferencias pendientes (no compensadas):")
        for fila in pendientes:
            print(f" - {fila.codadm_a} vs {fila.codadm_b}: {formato_latam(fila.diferencia)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
