"""一键运行完整实验：场景 -> 调度 -> 指标 -> 图表。

用法::

    python run_experiment.py
    python run_experiment.py --cars 60 --stalls 12
    python run_experiment.py --data 场站数据.csv

运行结果写入 experiments/ 目录：
    summary.csv           三套策略的指标对比（含相对基线的改进幅度）
    schedule.csv          每辆车在各策略下的充电时段安排
    load_curve.csv        96 个时段的负荷、电价、碳强度与光伏出力
    load_curve.svg        负荷与能源曲线图
    demand_forecast.svg   预测模块的预测值与实际值对比
"""

import argparse
import csv
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, "src"))

from config import (DEFAULT_SCENARIO, SLOTS_PER_DAY, SLOT_HOURS,
                    carbon_at, price_at, pv_at)
from data.loader import load_cars_from_file
from data.scenario import generate_cars, summarize_cars
from decision.strategies import STRATEGIES, STRATEGY_LABELS, simulate
from metrics.evaluate import (METRIC_ROWS, evaluate,
                              improvement_over_baseline)
from predict.demand import backtest, build_history, forecast_mean
from viz.svg_chart import line_chart


def slot_label(slot):
    """时段编号 -> "08:30" 形式的时刻标签。"""
    if slot >= SLOTS_PER_DAY:
        return "24:00"
    return "%02d:%02d" % (slot // 4, (slot % 4) * 15)


def compress_slots(slots):
    """把连续的充电时段压缩成 "12:15-14:30; 16:00-16:15" 这样的区间串。"""
    if not slots:
        return ""
    ordered = sorted(slots)
    ranges = []
    start = prev = ordered[0]
    for i in range(1, len(ordered) + 1):
        if i < len(ordered) and ordered[i] == prev + 1:
            prev = ordered[i]
            continue
        ranges.append("%s-%s" % (slot_label(start), slot_label(prev + 1)))
        if i < len(ordered):
            start = prev = ordered[i]
    return "; ".join(ranges)


def parse_args():
    parser = argparse.ArgumentParser(description="电动汽车充电调度对比实验")
    parser.add_argument("--cars", type=int, default=DEFAULT_SCENARIO["n_cars"],
                        help="需要充电的车辆数")
    parser.add_argument("--stalls", type=int, default=DEFAULT_SCENARIO["n_stalls"],
                        help="充电桩数量")
    parser.add_argument("--stall-power", type=float, default=DEFAULT_SCENARIO["stall_power_kw"],
                        help="单桩额定功率 (kW)")
    parser.add_argument("--transformer", type=float, default=DEFAULT_SCENARIO["transformer_kw"],
                        help="变压器容量上限 (kW)")
    parser.add_argument("--pv", type=float, default=DEFAULT_SCENARIO["pv_peak_kw"],
                        help="光伏装机容量 (kWp)")
    parser.add_argument("--need", type=float, default=DEFAULT_SCENARIO["mean_need_kwh"],
                        help="单车平均充电需求 (kWh)")
    parser.add_argument("--seed", type=int, default=DEFAULT_SCENARIO["seed"],
                        help="随机种子")
    parser.add_argument("--history-days", type=int, default=30,
                        help="预测模块使用的历史天数")
    parser.add_argument("--data", type=str, default=None,
                        help="改用官方 CSV 数据（跳过场景生成）")
    return parser.parse_args()


def build_config(args):
    cfg = dict(DEFAULT_SCENARIO)
    cfg.update({
        "n_cars": args.cars,
        "n_stalls": args.stalls,
        "stall_power_kw": args.stall_power,
        "transformer_kw": args.transformer,
        "pv_peak_kw": args.pv,
        "mean_need_kwh": args.need,
        "seed": args.seed,
    })
    return cfg


def print_metrics_table(metrics):
    """在终端打印对比表，并用 * 标出每行的最优值。"""
    print("        %-24s%17s%17s%17s" % (
        "指标", STRATEGY_LABELS["baseline"],
        STRATEGY_LABELS["price"], STRATEGY_LABELS["carbon"]))
    for field, label, digits in METRIC_ROWS:
        values = [metrics[key].get(field, 0.0) for key in STRATEGIES]
        best = max(values) if field == "pv_self_use_pct" else min(values)
        cells = ""
        for value in values:
            mark = "*" if abs(value - best) < 1e-9 else " "
            cells += "%16s%s" % (("%." + str(digits) + "f") % value, mark)
        print("        %-24s%s" % (label, cells))
    print("        （* 表示该指标下的最优值）")


def write_summary(out_dir, metrics):
    path = os.path.join(out_dir, "summary.csv")
    improve = improvement_over_baseline(metrics)
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["指标"] + [STRATEGY_LABELS[k] for k in STRATEGIES])
        for field, label, _digits in METRIC_ROWS:
            writer.writerow([label] + [metrics[k].get(field, "") for k in STRATEGIES])
        writer.writerow([])
        writer.writerow(["相对基线的改进幅度 (%)", "", "", ""])
        for field, label, _digits in METRIC_ROWS:
            values = []
            for key in ("price", "carbon"):
                values.append(improve[key].get(field, ""))
            writer.writerow([label, ""] + values)
    print("        summary.csv            —— 指标对比与改进幅度")


def write_schedule(out_dir, results, cfg):
    path = os.path.join(out_dir, "schedule.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["方案", "车辆编号", "车辆类型", "到达", "离开",
                         "需求电量kWh", "实际充电kWh", "充电时段"])
        for key in STRATEGIES:
            for session in results[key]["sessions"]:
                writer.writerow([
                    STRATEGY_LABELS[key],
                    session.id + 1,
                    session.kind,
                    slot_label(session.arr_slot),
                    slot_label(session.dep_slot),
                    "%.1f" % session.need_kwh,
                    "%.1f" % session.delivered_kwh,
                    compress_slots(session.charging_slots()),
                ])
    print("        schedule.csv           —— 每辆车的充电时段安排")


def write_load_curve(out_dir, cfg, results):
    path = os.path.join(out_dir, "load_curve.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["时刻", "电价", "电网碳强度", "光伏出力kW"]
                        + [STRATEGY_LABELS[k] + " 负荷kW" for k in STRATEGIES])
        for slot in range(SLOTS_PER_DAY):
            hour = slot * SLOT_HOURS
            writer.writerow(
                [slot_label(slot),
                 "%.2f" % price_at(hour),
                 "%.2f" % carbon_at(hour),
                 "%.1f" % pv_at(hour, cfg["pv_peak_kw"])]
                + ["%.1f" % results[k]["load"][slot] for k in STRATEGIES]
            )
    print("        load_curve.csv         —— 96 时段负荷与能源数据")


def write_charts(out_dir, cfg, results, history):
    labels = [slot_label(s) for s in range(SLOTS_PER_DAY)]
    pv_curve = [pv_at(s * SLOT_HOURS, cfg["pv_peak_kw"]) for s in range(SLOTS_PER_DAY)]

    load_series = [
        {"name": "光伏出力", "values": pv_curve, "color": "#21b48a",
         "fill": True, "width": 1.6},
        {"name": "变压器容量", "values": [cfg["transformer_kw"]] * SLOTS_PER_DAY,
         "color": "#9ca3af", "dashed": True, "width": 1.6},
        {"name": STRATEGY_LABELS["baseline"], "values": results["baseline"]["load"],
         "color": "#ef4444"},
        {"name": STRATEGY_LABELS["price"], "values": results["price"]["load"],
         "color": "#f59e0b"},
        {"name": STRATEGY_LABELS["carbon"], "values": results["carbon"]["load"],
         "color": "#16a34a", "width": 2.8},
    ]
    line_chart(os.path.join(out_dir, "load_curve.svg"), load_series,
               title="24 小时充电负荷与能源曲线", y_unit="kW",
               x_labels=labels, x_tick_every=8)

    forecast_series = [
        {"name": "历史均值（预测值）", "values": forecast_mean(history[:-1]),
         "color": "#2563eb", "dashed": True},
        {"name": "当日实际需求", "values": history[-1],
         "color": "#f97316", "width": 2.4},
    ]
    line_chart(os.path.join(out_dir, "demand_forecast.svg"), forecast_series,
               title="逐时段充电需求：预测值 vs 实际值", y_unit="kWh/15min",
               x_labels=labels, x_tick_every=8)
    print("        load_curve.svg         —— 负荷与能源曲线图")
    print("        demand_forecast.svg    —— 预测模块效果图")


def main():
    args = parse_args()
    cfg = build_config(args)
    out_dir = os.path.join(BASE_DIR, "experiments")
    os.makedirs(out_dir, exist_ok=True)

    print("=" * 66)
    print("电动汽车充电调度 · 对比实验")
    print("=" * 66)
    print("场景：%s | %d 辆车 | %d 桩 x %.0f kW | 变压器 %.0f kW | 光伏 %.0f kWp | 种子 %d"
          % (cfg["name"], cfg["n_cars"], cfg["n_stalls"], cfg["stall_power_kw"],
             cfg["transformer_kw"], cfg["pv_peak_kw"], cfg["seed"]))

    # ---- 1 / 5 数据处理 ----
    print("\n[1/5] 数据处理")
    if args.data:
        cars, stats = load_cars_from_file(args.data, cfg)
        print("        来源：官方 CSV 文件 %s" % args.data)
        for key, value in stats.items():
            print("          %s: %s" % (key, value))
    else:
        cars = generate_cars(cfg)
        print("        来源：按公开统计规律合成场景")
        for key, value in summarize_cars(cars).items():
            print("          %s: %s" % (key, value))

    # ---- 2 / 5 预测 ----
    print("\n[2/5] 预测（历史 %d 天）" % args.history_days)
    history = build_history(cfg, days=args.history_days)
    report = backtest(history)
    print("        留一天验证：MAE = %.3f kWh/时段，MAPE = %.2f%%（当日总需求 %.1f kWh）"
          % (report["mae_kwh"], report["mape_pct"], report["test_day_kwh"]))

    # ---- 3 / 5 决策 ----
    print("\n[3/5] 决策")
    results = {}
    for key in STRATEGIES:
        results[key] = simulate(key, cars, cfg)
        print("        %-22s 完成" % STRATEGY_LABELS[key])

    # ---- 4 / 5 指标 ----
    print("\n[4/5] 指标")
    metrics = {key: evaluate(results[key], cfg) for key in STRATEGIES}
    print_metrics_table(metrics)
    improve = improvement_over_baseline(metrics)
    for key in ("price", "carbon"):
        row = improve[key]
        print("        %s 相对基线：峰值 %+.0f%% | 电费 %+.0f%% | 碳排 %+.0f%% | 光伏消纳 %+.0f%%"
              % (STRATEGY_LABELS[key], row["peak_kw"], row["cost_yuan"],
                 row["carbon_kg"], row["pv_self_use_pct"]))

    # ---- 5 / 5 输出 ----
    print("\n[5/5] 输出到 experiments/")
    write_summary(out_dir, metrics)
    write_schedule(out_dir, results, cfg)
    write_load_curve(out_dir, cfg, results)
    write_charts(out_dir, cfg, results, history)
    print("\n完成。")


if __name__ == "__main__":
    main()
