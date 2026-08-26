"""Юнит-тест забега. Запуск: python3 scripts/test_rshr_overhang.py (из tochnost/)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from rshr_core.rshr_overhang import OVERHANG_SANITY_MM, overhang_mm, overhangs_from_edges

FAILED = 0


def check(got, want, label):
    global FAILED
    if got == want:
        print(f"  ok   {label}")
    else:
        FAILED += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


check(overhang_mm(None, 1000), None, "старая прошивка: левый None")
check(overhang_mm(1000, None), None, "старая прошивка: правый None")
check(overhang_mm(None, None), None, "старая прошивка: оба None")
check(overhang_mm(1012, 1000), 12, "левая нить забежала на 12 мм")
check(overhang_mm(1000, 1012), -12, "правая нить забежала на 12 мм")
check(overhang_mm(1000, 1000), 0, "торцы вровень")
check(overhang_mm(0, 0), 0, "нулевая ось — валидный забег 0")
check(overhang_mm(1000 + OVERHANG_SANITY_MM, 1000), OVERHANG_SANITY_MM, "ровно на границе sanity — принимаем")
check(overhang_mm(1000 + OVERHANG_SANITY_MM + 1, 1000), None, "за границей sanity — отбрасываем")
check(overhang_mm(1000, 1000 + OVERHANG_SANITY_MM + 1), None, "за границей sanity в минус — отбрасываем")
check(overhang_mm(24000, 0), None, "торец конца не пойман (End=0) — отбрасываем")

print()
check(overhangs_from_edges(None), (None, None), "нет edges (рельс не проходил пост 1)")
check(overhangs_from_edges((112, 100, 24092, 24100)), (12, -8), "нормальный проход: +12 / -8")
check(overhangs_from_edges((112, 100, 0, 0)), (12, None), "торец конца не пойман (0/0) → конец None")
check(overhangs_from_edges((112, 100, 24000, 0)), (12, None), "правый торец конца не пойман → конец None")
check(overhangs_from_edges((112, 100, 0, 24000)), (12, None), "левый торец конца не пойман → конец None")
check(overhangs_from_edges((0, 0, 24000, 24000)), (0, 0), "начало 0/0 — законный забег 0, не None")
check(overhangs_from_edges((12, 0, 25012, 25000)), (12, 12), "ось от начала РШР: start 12/0")
check(overhangs_from_edges((1000, 100, 24000, 24000)), (None, 0), "начало вне sanity → None, конец считается")

if FAILED:
    print(f"\n{FAILED} тест(ов) упало")
    sys.exit(1)
print("\nвсе тесты прошли")
