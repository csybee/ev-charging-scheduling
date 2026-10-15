"""决策模块：三套调度策略。

**策略 baseline（即插即充基线）**
车主插上枪就满功率充电，先到先服务，不看电价、不看碳强度、不受变压器约束。
这是最贴近现实"没有做任何调度"的场景，也是对照组。

**策略 price（策略A · 电价优化）**
传统有序充电做法：只看分时电价，把充电挪到电价低谷。

**策略 carbon（策略B · 碳光协同）**
本方案：按电网碳强度排序，把充电挪到绿电最充沛的时段。
由于午间光伏出力最高、碳强度最低，充电负荷自然与光伏出力重合，
用的是自己屋顶发的电，于是**同时压低了电费和碳排**。

三种策略共用同一套调度内核：

1. 把 96 个时段按"吸引力"从优到劣排序；
2. 依次处理每个时段，把当期的可用容量分配给在场的车辆；
3. 同一时段内部按**紧迫度**降序分配，紧迫的车永远优先拿到功率。

这样设计的好处是：弹性需求会被自动推后到绿电时段，而刚性需求（例如只停
1 小时的访客车）永远能第一时间充上电，不会出现"为了减碳把车主耽误了"。
"""

from config import SLOTS_PER_DAY, SLOT_HOURS, carbon_at, price_at
from model.session import ChargingSession

STRATEGIES = ("baseline", "price", "carbon")

STRATEGY_LABELS = {
    "baseline": "即插即充基线",
    "price": "策略A · 电价优化",
    "carbon": "策略B · 碳光协同",
}


def _slot_score(strategy, slot):
    """时段吸引力，越大越适合充电。"""
    hour = slot * SLOT_HOURS
    if strategy == "price":
        return -price_at(hour)
    return -carbon_at(hour)


def _dispatch(slot, ordered, capacity_kw, cfg, load, assignment):
    """把一个时段的可用容量按顺序分配给车辆。"""
    budget = capacity_kw
    stalls_left = cfg["n_stalls"]

    for session in ordered:
        if budget <= 1e-6 or stalls_left <= 0:
            break
        want = session.power_needed_kw()
        if want <= 1e-6:
            continue
        give = min(want, budget)
        actual = session.charge(slot, give)
        if actual <= 1e-6:
            continue
        load[slot] += actual
        assignment[slot].append(session.id)
        budget -= actual
        stalls_left -= 1


def simulate(strategy, cars, cfg):
    """跑一遍调度，返回负荷曲线、会话状态与逐时段分配。

    返回字段：
        strategy   策略名
        load       96 点负荷曲线（kW）
        sessions   车辆会话列表（含最终充电结果）
        assignment 每个时段被分配的车辆编号
    """
    if strategy not in STRATEGIES:
        raise ValueError("未知策略：%s" % strategy)

    sessions = [
        ChargingSession(car, cfg["stall_power_kw"], SLOT_HOURS) for car in cars
    ]
    load = [0.0] * SLOTS_PER_DAY
    assignment = [[] for _ in range(SLOTS_PER_DAY)]

    capacity_kw = cfg["n_stalls"] * cfg["stall_power_kw"]
    if strategy != "baseline":
        # 只有做了调度的策略才会主动把负荷压在变压器容量以下
        capacity_kw = min(capacity_kw, cfg["transformer_kw"])

    if strategy == "baseline":
        for slot in range(SLOTS_PER_DAY):
            present = [s for s in sessions if s.is_present(slot) and not s.is_full()]
            present.sort(key=lambda s: (s.arr_slot, s.id))
            _dispatch(slot, present, capacity_kw, cfg, load, assignment)
    else:
        slot_order = list(range(SLOTS_PER_DAY))
        slot_order.sort(key=lambda s: (-_slot_score(strategy, s), s))
        for slot in slot_order:
            present = [s for s in sessions if s.is_present(slot) and not s.is_full()]
            present.sort(key=lambda s: (-s.urgency(slot), s.id))
            _dispatch(slot, present, capacity_kw, cfg, load, assignment)

    return {
        "strategy": strategy,
        "load": load,
        "sessions": sessions,
        "assignment": assignment,
    }
