"""Забег рельсовых нитей — продольное несовпадение торцов левой и правой нити.

Забег считается РАЗНОСТЬЮ двух засечек, снятых практически в одной точке ленты,
поэтому накопленная ошибка масштаба энкодера (0.2% ≈ 50 мм на 25 м) в ней
сокращается: 0.2% от 30 мм = 0.06 мм.

Длину по тем же полям считать НЕЛЬЗЯ: mmAlongRail сбрасывается при мигании
лазера, из-за чего Start и End могут оказаться с разными нулями (ADR-0010).
Длина считается по traversed_mm.
"""

from __future__ import annotations

# Забег физически не бывает больше полуметра. Всё, что больше, — сбой засечки:
# торец не пойман (поле осталось 0), сброс mmAlongRail между Start и End,
# мусор из прошивки.
OVERHANG_SANITY_MM = 500


def overhang_mm(left: int | None, right: int | None) -> int | None:
    """Забег = левая нить − правая. Знак «+» — левая забежала вперёд.

    Возвращает None, если данных нет (старая прошивка сборщика) или разность
    неправдоподобна. None означает «не измерено» — вызывающий код НЕ пишет
    метрику и НЕ заводит Error.
    """
    if left is None or right is None:
        return None
    delta = int(left) - int(right)
    if abs(delta) > OVERHANG_SANITY_MM:
        return None
    return delta


def overhangs_from_edges(
    edges: tuple[int, int, int, int] | None,
) -> tuple[int | None, int | None]:
    """(забег в начале, забег в конце) из (start_l, start_r, end_l, end_r).

    Правило про нулевой торец конца. Прошивка инициализирует поля нулями и
    заполняет End только после прохода торца. Если торец не пойман (проход
    оборвался, лазер мигнул на выходе), в End остаются нули — и разность 0−0
    прошла бы sanity-отсечку, записав ложный «забег 0» вместо «не измерено».
    Реальный торец конца на нулевой отметке невозможен, поэтому любой ноль в
    паре End = не измерено.

    К Start это правило НЕ применяется: mmAlongRail отсчитывается ОТ начала
    РШР, поэтому оба торца начала законно лежат около нуля, и 0/0 там означает
    ровно то, что написано — нити вровень. Рельс, не проходивший пост 1,
    вообще не имеет edges (last_rail_edges остаётся None).
    """
    if edges is None:
        return None, None
    start_left, start_right, end_left, end_right = edges
    start = overhang_mm(start_left, start_right)
    end = None if (end_left == 0 or end_right == 0) else overhang_mm(end_left, end_right)
    return start, end
