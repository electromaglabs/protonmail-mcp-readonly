"""Tidsmätning för prestandatester som tål långsamma och belastade maskiner.

En absolut gräns ("under 1 s") kalibrerad på en snabb Mac faller på en
långsam eller belastad CI-maskin även när koden är linjär. Testerna ska i
stället jämföra mätningar som görs på samma maskin i samma stund:

- ``assert_linear``: samma arbete för n och 4n. Linjärt ger ≈ 4 gånger så
  lång tid, kvadratiskt ≈ 16. Gränsen 8 (mittemellan, geometriskt) ger
  marginal åt båda hållen. Dimensionera indata så att en kvadratisk variant
  verkligen domineras av den kvadratiska delen vid 4n — kopiering av strängar
  är billig per byte och syns först när raderna/texten är långa.
- ``assert_cheaper_than``: arbetet mot ett referensarbete som ändå måste
  göras (t.ex. att parsa meddelandet en gång).

Varje mätning görs flera gånger och den snabbaste räknas: en tillfällig
fördröjning (GC, en annan process) gör bara en enstaka mätning långsammare.
Korta mätningar upprepas tills de tillsammans tagit MIN_TOTAL sekunder (högst
MAX_RUNS gånger), eftersom ett enda schemaläggningsavbrott på en belastad
maskin annars kan vara lika långt som hela mätningen. Blir kvoten för hög
mäts båda storlekarna om (högst ATTEMPTS omgångar) och de snabbaste tiderna
hittills jämförs: tillfällig last ger en hög kvot en gång, kvadratisk kod
ger den varje gång.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")

FACTOR = 4
MAX_RATIO = 8.0
REPEATS = 3
MIN_TOTAL = 0.25
MAX_RUNS = 50
ATTEMPTS = 3
# Kortare tider än så här mäts inte tillräckligt exakt för en kvot
FLOOR = 0.005


def _more(runs: int, total: float, repeats: int) -> bool:
    return runs < repeats or (total < MIN_TOTAL and runs < MAX_RUNS)


def best_time(func: Callable[[], Any], repeats: int = REPEATS) -> float:
    best, total, runs = float("inf"), 0.0, 0
    while _more(runs, total, repeats):
        start = time.perf_counter()
        func()
        elapsed = time.perf_counter() - start
        best, total, runs = min(best, elapsed), total + elapsed, runs + 1
    return best


async def best_time_async(func: Callable[[], Awaitable[Any]], repeats: int = REPEATS) -> float:
    best, total, runs = float("inf"), 0.0, 0
    while _more(runs, total, repeats):
        start = time.perf_counter()
        await func()
        elapsed = time.perf_counter() - start
        best, total, runs = min(best, elapsed), total + elapsed, runs + 1
    return best


def _ratio_message(n: int, small: float, big: float, factor: int) -> str:
    ratio = big / max(small, FLOOR)
    return (
        f"{factor} gånger så stor indata tog {ratio:.1f} gånger så lång tid "
        f"({small:.3f} s för n={n}, {big:.3f} s för n={n * factor}) — "
        f"linjärt ≈ {factor}, kvadratiskt ≈ {factor * factor}"
    )


def assert_linear(
    func: Callable[[T], Any],
    make_input: Callable[[int], T],
    n: int,
    *,
    factor: int = FACTOR,
    max_ratio: float = MAX_RATIO,
    repeats: int = REPEATS,
) -> None:
    """Kör ``func(make_input(n))`` och ``func(make_input(factor * n))`` och
    kräv att tiden växer linjärt. Indata byggs utanför den mätta tiden.

    Välj n så att den lilla mätningen tar minst några tiotal millisekunder
    på en snabb maskin; annars dominerar fasta kostnader och mätbrus.
    """
    small_input, big_input = make_input(n), make_input(n * factor)
    small = big = float("inf")
    for _ in range(ATTEMPTS):
        small = min(small, best_time(lambda: func(small_input), repeats))
        big = min(big, best_time(lambda: func(big_input), repeats))
        print("tidsmätning:", _ratio_message(n, small, big, factor))
        if big / max(small, FLOOR) < max_ratio:
            return
    raise AssertionError(_ratio_message(n, small, big, factor))


async def assert_linear_async(
    func: Callable[[T], Awaitable[Any]],
    make_input: Callable[[int], T],
    n: int,
    *,
    factor: int = FACTOR,
    max_ratio: float = MAX_RATIO,
    repeats: int = REPEATS,
) -> None:
    """Som ``assert_linear`` för en korutinfunktion."""
    small_input, big_input = make_input(n), make_input(n * factor)
    small = big = float("inf")
    for _ in range(ATTEMPTS):
        small = min(small, await best_time_async(lambda: func(small_input), repeats))
        big = min(big, await best_time_async(lambda: func(big_input), repeats))
        print("tidsmätning:", _ratio_message(n, small, big, factor))
        if big / max(small, FLOOR) < max_ratio:
            return
    raise AssertionError(_ratio_message(n, small, big, factor))


def assert_cheaper_than(elapsed: float, reference: float, max_ratio: float, what: str) -> None:
    """Kräv att ``elapsed`` är högst ``max_ratio`` gånger referensarbetet."""
    ratio = elapsed / max(reference, FLOOR)
    print(f"tidsmätning: {what} {elapsed:.4f} s, referens {reference:.4f} s, kvot {ratio:.1f}")
    assert ratio < max_ratio, (
        f"{what} tog {elapsed:.3f} s, {ratio:.1f} gånger referensarbetet "
        f"({reference:.3f} s); högst {max_ratio} gånger"
    )
