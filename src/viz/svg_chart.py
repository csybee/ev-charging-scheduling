"""零依赖 SVG 折线图。

不引入 matplotlib，原因和 requirements.txt 里说明的一致：
队友 clone 下来直接出图，赛时也能把绘图代码整体移植进主办方的基线系统。
"""


def _escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def line_chart(path, series, width=980, height=440, title="", y_unit="",
               x_tick_every=8, x_labels=None):
    """把若干条曲线画到一张 SVG 上。

    参数
        path         输出文件路径
        series       [{"name": 图例名, "values": [数值...],
                       "color": "#rrggbb", "dashed": bool,
                       "fill": bool, "width": 线宽}, ...]
        x_labels     每个横坐标点的标签（如 "08:30"）
    """
    if not series:
        raise ValueError("series 不能为空")

    n = len(series[0]["values"])
    pad_l, pad_r, pad_t, pad_b = 74, 186, 48, 44
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    y_max = max(max(s["values"]) for s in series)
    y_max = y_max * 1.12 if y_max > 0 else 1.0

    def x_of(i):
        return pad_l + plot_w * i / float(max(1, n - 1))

    def y_of(value):
        return pad_t + plot_h * (1.0 - min(max(value, 0.0), y_max) / y_max)

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
        'font-family="Segoe UI, Microsoft YaHei, sans-serif">' % (width, height, width, height),
        '<rect width="%d" height="%d" fill="#ffffff"/>' % (width, height),
    ]

    if title:
        parts.append('<text x="%d" y="28" font-size="16" font-weight="600" fill="#1f2937">%s</text>'
                     % (pad_l, _escape(title)))

    # 横向网格线与纵轴刻度
    ticks = 5
    for k in range(ticks + 1):
        value = y_max * k / float(ticks)
        y = y_of(value)
        parts.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e5e7eb" stroke-width="1"/>'
                     % (pad_l, y, pad_l + plot_w, y))
        parts.append('<text x="%d" y="%.1f" font-size="11" fill="#6b7280" text-anchor="end">%.0f</text>'
                     % (pad_l - 8, y + 4, value))

    # 横轴刻度
    if x_labels:
        for i in range(0, n, x_tick_every):
            x = x_of(i)
            parts.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#d1d5db" stroke-width="1"/>'
                         % (x, pad_t + plot_h, x, pad_t + plot_h + 5))
            parts.append('<text x="%.1f" y="%d" font-size="11" fill="#6b7280" text-anchor="middle">%s</text>'
                         % (x, pad_t + plot_h + 20, _escape(x_labels[i])))

    # 坐标轴
    parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#9ca3af" stroke-width="1.2"/>'
                 % (pad_l, pad_t + plot_h, pad_l + plot_w, pad_t + plot_h))
    parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#9ca3af" stroke-width="1.2"/>'
                 % (pad_l, pad_t, pad_l, pad_t + plot_h))

    # 曲线
    for s in series:
        values = s["values"]
        points = " ".join("%.1f,%.1f" % (x_of(i), y_of(v)) for i, v in enumerate(values))
        color = s.get("color", "#2563eb")
        if s.get("fill"):
            area = "%.1f,%.1f " % (x_of(0), y_of(0)) + points + \
                   " %.1f,%.1f" % (x_of(n - 1), y_of(0))
            parts.append('<polygon points="%s" fill="%s" opacity="0.13"/>' % (area, color))
        dash = ' stroke-dasharray="6 4"' if s.get("dashed") else ""
        parts.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="%.1f"%s/>'
                     % (points, color, s.get("width", 2.2), dash))

    # 图例
    legend_x = pad_l + plot_w + 20
    for i, s in enumerate(series):
        y = pad_t + 10 + i * 23
        color = s.get("color", "#2563eb")
        parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="3"/>'
                     % (legend_x, y, legend_x + 20, y, color))
        parts.append('<text x="%d" y="%d" font-size="12" fill="#374151">%s</text>'
                     % (legend_x + 26, y + 4, _escape(s["name"])))

    if y_unit:
        parts.append('<text x="%d" y="%d" font-size="11" fill="#6b7280">%s</text>'
                     % (pad_l - 52, pad_t + 12, _escape(y_unit)))

    parts.append("</svg>")

    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(parts))
    return path
