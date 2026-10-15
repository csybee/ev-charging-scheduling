"""赛题数据接入。

主办方给出的充电数据格式在赛时才会公开。为了让本仓库的算法内核能直接吃
官方数据，这里实现一个**容错性较强的 CSV 导入器**：

* 表头中英文都能识别（到达 / arr / start、离开 / dep / end、电量 / kwh …）；
* 列顺序不敏感，识别不出的列按"第 2、3、4 列"兜底；
* 时间支持 ``08:30``、``8:30:00``、``8.5`` 三种写法；
* 无效行会被跳过并计数，不会让整个文件失败。

典型用法::

    cars, stats = load_cars_from_file("station_a.csv", cfg)
"""

import csv
import io
import math

from config import SLOTS_PER_DAY, SLOT_HOURS

_ARR_KEYS = ("到达", "arr", "start", "进入")
_DEP_KEYS = ("离开", "离场", "驶离", "dep", "end", "结束")
_NEED_KEYS = ("电量", "需求", "kwh", "energy", "度")


def parse_time(value):
    """把 ``08:30`` / ``8:30:00`` / ``8.5`` 统一解析成小时数（浮点）。"""
    text = str(value).strip().strip('"')
    if not text:
        return None
    if ":" in text:
        parts = text.split(":")
        try:
            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2]) if len(parts) > 2 else 0.0
        except ValueError:
            return None
        return hours + minutes / 60.0 + seconds / 3600.0
    try:
        return float(text)
    except ValueError:
        return None


def _looks_like_header(row):
    """表头行一定含有非数字、非冒号的字符（例如"到达时间"）。"""
    joined = "".join(str(cell) for cell in row)
    for ch in joined:
        if ch.isdigit() or ch in " \t:.-+":
            continue
        return True
    return False


def _detect_columns(header):
    """在表头中定位到达、离开、需求三列，识别不出的位置跳过。"""
    idx = {"arr": -1, "dep": -1, "need": -1}
    for i, cell in enumerate(header):
        text = str(cell).lower()
        if idx["arr"] < 0 and any(k in text for k in _ARR_KEYS):
            idx["arr"] = i
        elif idx["dep"] < 0 and any(k in text for k in _DEP_KEYS):
            idx["dep"] = i
        elif idx["need"] < 0 and any(k in text for k in _NEED_KEYS):
            idx["need"] = i

    used = set(v for v in idx.values() if v >= 0)
    for fallback in (1, 2, 3):
        if fallback in used:
            continue
        for key in ("arr", "dep", "need"):
            if idx[key] < 0:
                idx[key] = fallback
                used.add(fallback)
                break
    return idx


def _to_slots(arr_hour, dep_hour):
    arr_slot = int(math.floor(arr_hour * 4))
    arr_slot = max(0, min(arr_slot, SLOTS_PER_DAY - 1))
    dep_slot = int(math.ceil(dep_hour * 4))
    dep_slot = max(arr_slot + 1, min(dep_slot, SLOTS_PER_DAY))
    return arr_slot, dep_slot


def load_cars(text, cfg):
    """从 CSV 文本解析车辆列表。

    返回 ``(cars, stats)``；``stats`` 记录跳过的无效行数与被发电量上限截断的车数，
    便于在实验报告中如实披露数据清洗过程。
    """
    rows = [r for r in csv.reader(io.StringIO(text)) if any(str(c).strip() for c in r)]
    if not rows:
        raise ValueError("CSV 内容为空")

    if _looks_like_header(rows[0]):
        header, body = rows[0], rows[1:]
    else:
        header, body = None, rows
    if not body:
        raise ValueError("CSV 只有表头，没有数据行")

    idx = _detect_columns(header) if header else {"arr": 1, "dep": 2, "need": 3}

    cars = []
    skipped = 0
    capped = 0
    for row in body:
        try:
            arr_hour = parse_time(row[idx["arr"]])
            dep_hour = parse_time(row[idx["dep"]])
            need_text = str(row[idx["need"]]).strip().strip('"')
            need_kwh = float(need_text)
        except (IndexError, ValueError):
            skipped += 1
            continue

        if arr_hour is None or dep_hour is None or need_kwh <= 0 or dep_hour <= arr_hour:
            skipped += 1
            continue

        arr_slot, dep_slot = _to_slots(arr_hour, dep_hour)
        max_chargeable = (dep_slot - arr_slot) * SLOT_HOURS * cfg["stall_power_kw"]
        if need_kwh > max_chargeable:
            need_kwh = max_chargeable
            capped += 1

        cars.append({
            "id": len(cars),
            "kind": "file",
            "arr_slot": arr_slot,
            "dep_slot": dep_slot,
            "need_kwh": round(need_kwh, 1),
        })

    if not cars:
        raise ValueError("没有解析出有效数据行，请对照 docs/02-数据说明.md 检查列内容")

    stats = {"总行数": len(body), "有效车辆": len(cars), "跳过行数": skipped, "按上限截断": capped}
    return cars, stats


def load_cars_from_file(path, cfg):
    """从磁盘上的 CSV 文件读取车辆列表。"""
    with open(path, "r", encoding="utf-8-sig") as handle:
        return load_cars(handle.read(), cfg)
