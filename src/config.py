"""场景参数与能源模型。

全仓库共用一套时间离散约定：一天切分为 96 个 15 分钟时段，
时段编号 0 表示 00:00-00:15，编号 95 表示 23:45-24:00。

能源模型（分时电价、电网碳强度、光伏出力）在赛前是**假设值**，
赛时若主办方给出真实数据，只需替换本文件中的三个函数即可，
其余模块无需改动。
"""

import math

SLOTS_PER_DAY = 96
SLOT_HOURS = 0.25


DEFAULT_SCENARIO = {
    "name": "办公楼停车场",
    "n_cars": 40,            # 当日需要充电的车辆数
    "n_stalls": 16,          # 交流充电桩数量
    "stall_power_kw": 11.0,  # 单桩额定功率
    "transformer_kw": 100.0, # 变压器容量上限
    "pv_peak_kw": 100.0,     # 屋顶光伏装机容量
    "mean_need_kwh": 16.0,   # 单车平均充电需求
    "seed": 20261031,        # 固定随机种子，保证结果可复现
}


def slot_to_hour(slot):
    """时段编号 -> 该时段的起始小时数（浮点）。"""
    return slot * SLOT_HOURS


def price_at(hour):
    """分时电价，元 / kWh。

    谷 0.35（21:00-08:00）· 峰 1.05（08:00-11:00、17:00-21:00）
    尖峰 1.25（11:00-13:00）· 平 0.65（13:00-17:00、21:00-24:00）
    """
    if hour < 8:
        return 0.35
    if hour < 11:
        return 1.05
    if hour < 13:
        return 1.25
    if hour < 17:
        return 0.65
    if hour < 21:
        return 1.05
    return 0.65


def carbon_at(hour):
    """电网碳排放强度，kgCO2 / kWh。

    夜间以煤电为主偏高；午间光伏大发时全网碳强度最低。
    """
    if hour < 7:
        return 0.80
    if hour < 11:
        return 0.65
    if hour < 15:
        return 0.35
    if hour < 18:
        return 0.55
    if hour < 21:
        return 0.70
    return 0.75


def pv_at(hour, pv_peak_kw):
    """光伏出力，kW。06:30 开始发电，12:30 前后达到峰值，18:30 停止。"""
    if hour < 6.5 or hour > 18.5:
        return 0.0
    x = (hour - 6.5) / 12.0
    return pv_peak_kw * math.sin(math.pi * x) ** 1.6
