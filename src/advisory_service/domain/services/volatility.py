"""일봉 종가로 연율화된 변동성을 계산하는 순수 도메인 함수."""

import math
import statistics
from collections.abc import Sequence
from itertools import pairwise


def annualized_volatility(closes: Sequence[int | float]) -> float | None:
    positive = [float(value) for value in closes if value > 0]
    if len(positive) < 3:
        return None

    log_returns = [
        math.log(current / previous)
        for previous, current in pairwise(positive)
    ]
    return round(statistics.stdev(log_returns) * math.sqrt(252) * 100, 5)
