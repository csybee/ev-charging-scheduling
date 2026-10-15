"""预测模块：由历史充电记录预测当日逐时段充电需求。

方法刻意保持简单、可解释——赛前预研阶段的目的是把**接口和评估流程**搭好，
而不是追求预测精度。赛时可以把这个模块整体替换成更强的模型
（梯度提升、时序模型等），而下游的决策模块一行都不用改。

流程：

1. ``daily_demand_curve`` 把一天的车辆列表折算成 96 点的需求曲线；
2. ``build_history`` 生成若干天的历史曲线；
3. ``forecast_mean`` / ``forecast_quantile`` 给出点预测与需求上界；
4. ``backtest`` 用留一天法评估预测误差。
"""

import math

from config import DEFAULT_SCENARIO, SLOTS_PER_DAY
from data.scenario import generate_cars


def daily_demand_curve(cars):
    """把一天的车流量折算成逐时段充电需求量（kWh）。

    做法是把每辆车的需求电量平摊到它在场的所有时段上，得到一条
    "如果完全不调度、随时都在充"的原始需求分布。预测模块要预测的正是这条曲线。
    """
    curve = [0.0] * SLOTS_PER_DAY
    for car in cars:
        span = max(1, car["dep_slot"] - car["arr_slot"])
        per_slot = car["need_kwh"] / float(span)
        for slot in range(car["arr_slot"], car["dep_slot"]):
            curve[slot] += per_slot
    return curve


def build_history(cfg, days=30):
    """生成多天的历史需求曲线，模拟"历史上的充电记录"。"""
    history = []
    for day in range(days):
        day_cfg = dict(DEFAULT_SCENARIO)
        day_cfg.update(cfg)
        day_cfg["seed"] = cfg["seed"] + day * 7919
        history.append(daily_demand_curve(generate_cars(day_cfg)))
    return history


def forecast_mean(history):
    """点预测：历史曲线在同一时段上的算术平均。"""
    n = len(history)
    if n == 0:
        raise ValueError("历史数据为空")
    return [sum(curve[s] for curve in history) / float(n) for s in range(SLOTS_PER_DAY)]


def forecast_quantile(history, q=0.8):
    """需求上界：历史曲线在同一时段上的 q 分位数，供调度策略预留裕度。"""
    result = []
    for slot in range(SLOTS_PER_DAY):
        column = sorted(curve[slot] for curve in history)
        index = int(math.ceil(q * len(column))) - 1
        index = max(0, min(index, len(column) - 1))
        result.append(column[index])
    return result


def backtest(history):
    """留一天法评估：用前 n-1 天预测最后一天，报告 MAE 与 MAPE。"""
    if len(history) < 2:
        return {"mae_kwh": 0.0, "mape_pct": 0.0, "test_day_kwh": 0.0}

    train = history[:-1]
    test = history[-1]
    pred = forecast_mean(train)

    abs_err = sum(abs(pred[s] - test[s]) for s in range(SLOTS_PER_DAY))
    mae = abs_err / float(SLOTS_PER_DAY)
    mean_actual = sum(test) / float(SLOTS_PER_DAY)
    mape = (mae / mean_actual * 100.0) if mean_actual > 0 else 0.0

    return {
        "mae_kwh": round(mae, 3),
        "mape_pct": round(mape, 2),
        "test_day_kwh": round(sum(test), 1),
    }
