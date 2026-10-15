"""状态建模：把一辆车的充电过程抽象成可推进的会话状态机。

这是整个仓库的核心抽象。调度算法不直接操作原始数据，而是操作"会话"对象——
每个会话自己知道：我还在不在场、我还差多少电、我离截止还有多少时间、
我现在最急迫的程度是多少。这样决策模块只需按紧迫度排序，逻辑非常干净。

**紧迫度**的定义是本项目的关键设计：

    urgency = 剩余需求 / (剩余时段数 x 单桩额定功率 x 时段长度)

它表示"如果从这一刻起一直满功率充，需要占用剩余时间的多大比例"。
urgency 趋近 1 表示必须立刻开始充电；远小于 1 表示还有充裕的腾挪空间。
"""


class ChargingSession:
    """一辆车在场期间的一次充电会话。"""

    def __init__(self, car, stall_power_kw, slot_hours):
        self.id = car["id"]
        self.kind = car.get("kind", "unknown")
        self.arr_slot = car["arr_slot"]
        self.dep_slot = car["dep_slot"]
        self.need_kwh = car["need_kwh"]

        self.stall_power_kw = stall_power_kw
        self.slot_hours = slot_hours

        self.remaining_kwh = car["need_kwh"]
        self.charging_kw = {}

    # ------------------------------------------------------------------
    # 状态查询
    # ------------------------------------------------------------------
    def is_present(self, slot):
        """该时段车辆是否还在场（离开时段本身不计入）。"""
        return self.arr_slot <= slot < self.dep_slot

    def is_full(self):
        return self.remaining_kwh <= 1e-6

    @property
    def delivered_kwh(self):
        return self.need_kwh - self.remaining_kwh

    def slots_available(self, slot):
        """从当前时段起，到车辆离开为止还剩几个时段。"""
        return max(0, self.dep_slot - slot)

    def max_energy_available(self, slot):
        """剩余时间内物理上最多还能充入多少电量（kWh）。"""
        return self.slots_available(slot) * self.stall_power_kw * self.slot_hours

    def power_needed_kw(self):
        """若要在单个时段内把剩余需求全部补齐，需要的功率（kW）。"""
        if self.remaining_kwh <= 1e-6:
            return 0.0
        return min(self.stall_power_kw, self.remaining_kwh / self.slot_hours)

    def urgency(self, slot):
        """紧迫度，取值约在 (0, 1]，越大越急。"""
        capacity = self.max_energy_available(slot)
        if capacity <= 1e-9:
            return float("inf")
        return self.remaining_kwh / capacity

    # ------------------------------------------------------------------
    # 状态推进
    # ------------------------------------------------------------------
    def charge(self, slot, power_kw):
        """在指定时段以给定功率充电，返回实际充入的功率。

        实际值不会超过"一趟充满所需功率"，也不会让剩余需求变成负数，
        这保证了状态机永远处于合法状态。
        """
        deliverable = min(power_kw, self.power_needed_kw())
        if deliverable <= 1e-6:
            return 0.0
        self.remaining_kwh = max(0.0, self.remaining_kwh - deliverable * self.slot_hours)
        self.charging_kw[slot] = self.charging_kw.get(slot, 0.0) + deliverable
        return deliverable

    def charging_slots(self):
        """该车实际充电过的时段编号，升序。"""
        return sorted(self.charging_kw.keys())
