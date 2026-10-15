"""充电场景生成。

赛前拿不到主办方的真实充电场站数据，因此按公开的出行统计规律合成场景：

* **通勤车（约 75%）**：早高峰陆续到达（08:30 前后），傍晚离开（17:30 前后），
  停留时间长、调度弹性大；
* **短时访客车（约 25%）**：白天随机到达，停留 1-4.5 小时，时间紧、必须优先满足。

两种车混合，恰好构成本问题最核心的矛盾：弹性需求要往绿电时段挪，
刚性需求不能挪。调度策略必须同时照顾这两类车。
"""

import math

from config import SLOTS_PER_DAY, SLOT_HOURS
from rng import SimpleRandom


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def generate_cars(cfg):
    """生成当日待充电车辆列表。

    返回的每辆车包含：
        id        车辆编号
        kind      车辆类型（commute / visitor）
        arr_slot  到达时段
        dep_slot  离开时段（不包含）
        need_kwh  需要充入的电量
    """
    rnd = SimpleRandom(cfg["seed"])
    raw = []

    n_short = int(round(cfg["n_cars"] * 0.25))
    n_long = cfg["n_cars"] - n_short

    # 通勤车：到达时间集中在早高峰，离开时间集中在傍晚
    for _ in range(n_long):
        arr_h = _clamp(8.5 + rnd.gauss() * 0.75, 6.5, 11.5)
        dep_h = _clamp(17.5 + rnd.gauss() * 0.9, 15.5, 21.0)
        raw.append(("commute", arr_h, dep_h))

    # 访客车：白天随机到达，停留时间短
    for _ in range(n_short):
        arr_h = 8.0 + rnd.random() * 12.0
        dep_h = _clamp(arr_h + 1.0 + rnd.random() * 3.5, arr_h + 0.75, 23.0)
        raw.append(("visitor", arr_h, dep_h))

    cars = []
    for idx, (kind, arr_h, dep_h) in enumerate(raw):
        need_kwh = _clamp(cfg["mean_need_kwh"] + rnd.gauss() * 7.0, 4.0, 45.0)

        arr_slot = int(math.floor(arr_h * 4))
        dep_slot = int(math.ceil(dep_h * 4))
        dep_slot = max(arr_slot + 2, min(dep_slot, SLOTS_PER_DAY))

        # 需求不能超过停留时间内物理上可充入的上限，否则该车永远无法满足
        max_chargeable = (dep_slot - arr_slot) * SLOT_HOURS * cfg["stall_power_kw"]
        if need_kwh > max_chargeable:
            need_kwh = max_chargeable * 0.9

        cars.append({
            "id": idx,
            "kind": kind,
            "arr_slot": arr_slot,
            "dep_slot": dep_slot,
            "need_kwh": round(need_kwh * 10) / 10,
        })
    return cars


def summarize_cars(cars):
    """输出场景的概要统计，用于实验记录。"""
    total_need = sum(c["need_kwh"] for c in cars)
    commute = sum(1 for c in cars if c["kind"] == "commute")
    avg_stay = sum((c["dep_slot"] - c["arr_slot"]) * SLOT_HOURS for c in cars) / max(1, len(cars))
    return {
        "车辆总数": len(cars),
        "通勤车": commute,
        "访客车": len(cars) - commute,
        "总充电需求 (kWh)": round(total_need, 1),
        "平均停留时长 (h)": round(avg_stay, 2),
    }
