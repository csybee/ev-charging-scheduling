"""指标计算。

八个指标覆盖了"绿色、经济、安全、体验"四个维度，这也是本项目在路演时
最想讲清楚的一组权衡：

* 绿色：碳排放、光伏就地消纳率
* 经济：总电费
* 安全：变压器峰值负荷、变压器过载时长
* 体验：未充满车辆数、未满足电量

其中"光伏就地消纳率"的定义是：充电负荷实际用掉的屋顶光伏电量，
占当天光伏总发电量的比例。电费与碳排都只对**电网购电量**计算——
用掉自己发的电既不计费也不计碳，这正是绿电直供的价值所在。
"""

from config import SLOTS_PER_DAY, SLOT_HOURS, carbon_at, price_at, pv_at

METRIC_ROWS = [
    ("peak_kw",         "变压器峰值负荷 (kW)", 1),
    ("cost_yuan",       "总电费 (元)",         1),
    ("carbon_kg",       "碳排放 (kgCO2)",      1),
    ("pv_self_use_pct", "光伏就地消纳率 (%)",  1),
    ("overload_hours",  "变压器过载时长 (h)",  2),
    ("unmet_cars",      "未充满车辆 (辆)",     0),
    ("unmet_kwh",       "未满足电量 (kWh)",    1),
    ("charged_kwh",     "总充电量 (kWh)",      1),
]


def evaluate(result, cfg):
    """计算一次调度结果的全部指标。"""
    load = result["load"]
    cost = 0.0
    carbon = 0.0
    pv_generated = 0.0
    pv_used = 0.0
    peak_kw = 0.0
    overload_hours = 0.0

    for slot in range(SLOTS_PER_DAY):
        hour = slot * SLOT_HOURS
        pv = pv_at(hour, cfg["pv_peak_kw"])
        power = load[slot]

        pv_generated += pv * SLOT_HOURS
        pv_used += min(power, pv) * SLOT_HOURS

        grid = max(0.0, power - pv)
        cost += grid * SLOT_HOURS * price_at(hour)
        carbon += grid * SLOT_HOURS * carbon_at(hour)

        peak_kw = max(peak_kw, power)
        if power > cfg["transformer_kw"]:
            overload_hours += SLOT_HOURS

    unmet = [s for s in result["sessions"] if s.remaining_kwh > 0.5]

    return {
        "peak_kw": round(peak_kw, 1),
        "cost_yuan": round(cost, 1),
        "carbon_kg": round(carbon, 1),
        "pv_self_use_pct": round(100.0 * pv_used / pv_generated, 1) if pv_generated > 0 else 0.0,
        "overload_hours": round(overload_hours, 2),
        "unmet_cars": len(unmet),
        "unmet_kwh": round(sum(s.remaining_kwh for s in unmet), 1),
        "charged_kwh": round(sum(load) * SLOT_HOURS, 1),
        "pv_generated_kwh": round(pv_generated, 1),
    }


# 这些指标越大越好；其余指标越小越好
HIGHER_IS_BETTER = ("pv_self_use_pct", "charged_kwh")


def improvement_over_baseline(metrics, baseline_key="baseline"):
    """计算各策略相对基线的改进幅度（百分比，正数一律表示"更优"）。"""
    base = metrics[baseline_key]
    out = {}
    for key, m in metrics.items():
        if key == baseline_key:
            continue
        row = {}
        for field, _label, _digits in METRIC_ROWS:
            b = base.get(field, 0.0)
            v = m.get(field, 0.0)
            if not b:
                row[field] = 0.0
            elif field in HIGHER_IS_BETTER:
                row[field] = round((v / b - 1.0) * 100.0, 1)
            else:
                row[field] = round((1.0 - v / b) * 100.0, 1)
        out[key] = row
    return out
