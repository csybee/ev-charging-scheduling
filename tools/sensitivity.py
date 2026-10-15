"""灵敏度分析：车辆数变化时，三套策略的相对优势如何变化。

这个脚本回答一个对策略选型很关键的问题：
"智能调度"的优势是不是在所有场景下都成立？边界在哪里？

用法::

    python tools/sensitivity.py
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from config import DEFAULT_SCENARIO
from data.scenario import generate_cars
from decision.strategies import STRATEGIES, STRATEGY_LABELS, simulate
from metrics.evaluate import evaluate

# 覆盖"容量宽松"到"容量紧张"的完整区间：
# 桩数为 16，单车需求约 16 kWh，车辆数 12 时几乎不排队；60 时严重争抢
CAR_COUNTS = [12, 20, 28, 36, 44, 52, 60]


def find_best(values, higher_is_better=False):
    return max(values) if higher_is_better else min(values)


def main():
    print("=" * 78)
    print("灵敏度分析：车辆数 vs 三套策略的表现")
    print("=" * 78)
    print("%-8s%-20s%10s%12s%12s%12s" % ("车辆数", "策略", "峰值kW", "电费元", "碳排kg", "光伏%"))
    print("-" * 78)

    for n_cars in CAR_COUNTS:
        cfg = dict(DEFAULT_SCENARIO)
        cfg["n_cars"] = n_cars
        cars = generate_cars(cfg)

        metrics = {}
        for key in STRATEGIES:
            metrics[key] = evaluate(simulate(key, cars, cfg), cfg)

        best_peak = find_best([metrics[k]["peak_kw"] for k in STRATEGIES])
        best_cost = find_best([metrics[k]["cost_yuan"] for k in STRATEGIES])
        best_carbon = find_best([metrics[k]["carbon_kg"] for k in STRATEGIES])
        best_pv = find_best([metrics[k]["pv_self_use_pct"] for k in STRATEGIES],
                            higher_is_better=True)

        for key in STRATEGIES:
            m = metrics[key]
            mark = lambda value, best: ("*" if abs(value - best) < 1e-9 else " ")
            print("%-8d%-20s%9.1f%s%11.1f%s%11.1f%s%11.1f%s" % (
                n_cars, STRATEGY_LABELS[key],
                m["peak_kw"], mark(m["peak_kw"], best_peak),
                m["cost_yuan"], mark(m["cost_yuan"], best_cost),
                m["carbon_kg"], mark(m["carbon_kg"], best_carbon),
                m["pv_self_use_pct"], mark(m["pv_self_use_pct"], best_pv),
            ))
        print("-" * 78)

    print("（* 表示该行所属场景下的最优值）")


if __name__ == "__main__":
    main()
