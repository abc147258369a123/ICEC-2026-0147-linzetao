# -*- coding: utf-8 -*-
"""
plotlib.py —— 极简 PNG 图表渲染库（仅依赖 Pillow）

## 为什么不用 matplotlib

本机 Python 环境未安装 matplotlib，且 pip 安装被沙箱拦截。
但本项目要求「图表必须能从原始数据一键复现」，
因此这里手写一个零额外依赖的绘图模块，只依赖 Pillow。

好处：
1. 任何装了 Python + Pillow 的机器都能直接重跑，不需要联网装包；
2. 渲染逻辑完全可控，图风格统一；
3. 与本人 `crop.js`（手写 PNG 解析与重编码）同一种「不依赖现成轮子」的思路。

## 支持能力

- 多面板布局（一个 Figure 内并排放多个绘图区）
- 双 Y 轴（主轴 + 次轴），左右独立刻度
- 折线 / 散点 / 柱状图 / 瀑布图（用柱状叠加实现）
- 垂直与水平参考线（支持虚线）
- 自动「好看」刻度（1 / 2 / 2.5 / 5 / 10 步进）
- 中文标题、副标题、轴标签、图例、数据点标注
- 4 倍超采样抗锯齿（supersample）

## 用法

    fig = Figure(1600, 900, title='标题', subtitle='副标题')
    p = fig.panel((0.08, 0.12, 0.92, 0.80), ylabel='电压 (V)', xlabel='时间 (s)')
    p.plot(xs, ys, color='#2563eb', label='电压')
    p.vline(7258, color='#dc2626', dash=True, label='输出截止')
    fig.save('out.png')
"""

import math
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------- 字体

FONT_CANDIDATES = {
    False: [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\Deng.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ],
    True: [
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
    ],
}

_font_cache = {}


def font(size, bold=False):
    """按需加载并缓存 TTF 字体。"""
    key = (int(size), bool(bold))
    if key in _font_cache:
        return _font_cache[key]
    f = None
    for path in FONT_CANDIDATES[bold]:
        try:
            f = ImageFont.truetype(path, int(size))
            break
        except Exception:
            continue
    if f is None:
        f = ImageFont.load_default()
    _font_cache[key] = f
    return f


# ---------------------------------------------------------------- 刻度

def nice_ticks(lo, hi, target=6):
    """生成「好看」的刻度序列：步长取 1/2/2.5/5/10 × 10^n。"""
    if not (hi > lo):
        hi = lo + 1.0
    span = hi - lo
    raw = span / max(target, 1)
    try:
        mag = 10.0 ** math.floor(math.log10(raw))
    except ValueError:
        mag = 1.0
    step = mag * 10.0
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            step = m * mag
            break
    start = math.ceil(lo / step) * step
    ticks = []
    v = start
    guard = 0
    while v <= hi + step * 1e-6 and guard < 1000:
        ticks.append(round(v, 10))
        v += step
        guard += 1
    if len(ticks) < 2:
        ticks = [lo, hi]
        step = hi - lo
    return ticks, step


def _decimals(step):
    if step >= 1:
        return 0
    if step >= 0.1:
        return 1
    if step >= 0.01:
        return 2
    return 3


# ---------------------------------------------------------------- 绘图区

class Panel:
    """一个绘图区：负责数据坐标 → 像素坐标的映射与所有图元绘制。"""

    def __init__(self, fig, rect, title="", xlabel="", ylabel="", y2label="",
                 xlim=None, ylim=None, y2lim=None,
                 xticks=None, yticks=None, y2ticks=None, xticklabels=None,
                 xtarget=8, ytarget=6):
        W, H = fig.px_w, fig.px_h
        l, t, r, b = rect
        self.fig = fig
        # 绘图区像素边界
        self.x0, self.y0 = l * W, t * H
        self.x1, self.y1 = r * W, b * H
        self.title, self.xlabel, self.ylabel, self.y2label = title, xlabel, ylabel, y2label
        self.series = []
        self.guides = []
        self.notes = []
        self.bars = []
        self.legend_items = []
        self._xlim = xlim
        self._ylim = ylim
        self._y2lim = y2lim
        # 供 _map / limits 直接访问；次轴未指定时退化为与主轴同范围
        self.xlim = xlim
        self.ylim = ylim
        self.y2lim = y2lim if y2lim is not None else ylim
        self._has_y2 = y2lim is not None
        self._xticks = xticks
        self._xticklabels = xticklabels
        self._yticks = yticks
        self._y2ticks = y2ticks
        self.xtarget, self.ytarget = xtarget, ytarget
        # 基准字号按 CSS 像素计；渲染时统一乘 ss 转成设备像素
        self.base_font = max(11, int(self.fig.w / 105))

    # -------- 数据坐标 → 像素

    def limits(self, axis="y"):
        if axis == "x":
            return self.xlim
        if axis == "y":
            return self.ylim
        return self.y2lim

    def _map(self, x, y, axis="y"):
        xlo, xhi = self.xlim
        ylo, yhi = self.limits(axis)
        px = self.x0 + (x - xlo) / (xhi - xlo) * (self.x1 - self.x0)
        py = self.y1 - (y - ylo) / (yhi - ylo) * (self.y1 - self.y0)
        return px, py

    # -------- 图元

    def plot(self, xs, ys, color="#2563eb", width=2, label=None, axis="y",
             dash=False, alpha_dash=None):
        pts = []
        for x, y in zip(xs, ys):
            if y is None or (isinstance(y, float) and math.isnan(y)):
                continue
            pts.append(self._map(x, y, axis))
        if not pts:
            return self
        self.series.append((pts, color, max(1, int(width * self.fig.ss)),
                            dash))
        if label:
            self.legend_items.append((color, label, "line"))
        return self

    def scatter(self, xs, ys, color="#2563eb", radius=3, label=None, axis="y"):
        r = max(2, int(radius * self.fig.ss))
        pts = [self._map(x, y, axis) for x, y in zip(xs, ys)]
        self.series.append(("scatter", pts, color, r))
        if label:
            self.legend_items.append((color, label, "dot"))
        return self

    def bar(self, x_center, width, bottom, top, color="#2563eb", label=None, axis="y"):
        """柱状图 / 瀑布图用：给定底与顶的数值。"""
        p0 = self._map(x_center - width / 2, bottom, axis)
        p1 = self._map(x_center + width / 2, top, axis)
        self.bars.append((p0[0], p1[0], p0[1], p1[1], color))
        if label:
            self.legend_items.append((color, label, "box"))
        return self

    def vline(self, x, color="#dc2626", dash=True, width=1.5, label=None):
        p0 = self._map(x, self.ylim[0])
        p1 = self._map(x, self.ylim[1])
        self.guides.append(("v", p0[0], p0[1], p1[1], color,
                            max(1, int(width * self.fig.ss)), dash))
        if label:
            self.legend_items.append((color, label, "dash"))
        return self

    def hline(self, y, color="#94a3b8", dash=True, width=1.5, label=None, axis="y"):
        p0 = self._map(self.xlim[0], y, axis)
        p1 = self._map(self.xlim[1], y, axis)
        self.guides.append(("h", p0[0], p0[1], p1[0], color,
                            max(1, int(width * self.fig.ss)), dash))
        if label:
            self.legend_items.append((color, label, "dash"))
        return self

    def annotate(self, x, y, text, color="#0f172a", axis="y", dx=0, dy=-18,
                 anchor="mb", size=None):
        px, py = self._map(x, y, axis)
        self.notes.append((px + dx * self.fig.ss, py + dy * self.fig.ss,
                           text, color, anchor, size or self.base_font))
        return self

    def text_at(self, fx, fy, text, color="#0f172a", anchor="la", size=None, bold=False):
        """按绘图区相对坐标（0~1）放文字。"""
        px = self.x0 + fx * (self.x1 - self.x0)
        py = self.y0 + fy * (self.y1 - self.y0)
        self.notes.append((px, py, text, color, anchor, size or self.base_font, bold))
        return self

    # -------- 自动范围

    def autoscale(self):
        xs, ys, y2s = [], [], []
        for s in self.series:
            if s[0] == "scatter":
                _, pts, _c, _r = s
                for px, py in pts:
                    pass
            else:
                pts = s[0]
                for px, py in pts:
                    pass
        # 直接由原始数据计算更可靠，故记录原始值
        return

    # -------- 渲染

    def render(self, img, draw):
        ss = self.fig.ss
        d = draw

        # --- 取范围（由调用方传入）
        if self._xlim is None or self._ylim is None:
            raise RuntimeError("Panel 需要显式传入 xlim / ylim（本库不做自动缩放）")

        # --- 网格与刻度
        xt = self._xticks or nice_ticks(*self.xlim, target=self.xtarget)[0]
        yt = self._yticks or nice_ticks(*self.ylim, target=self.ytarget)[0]
        grid_color = (226, 232, 240)
        axis_color = (100, 116, 139)
        txt_color = (51, 65, 85)

        f_axis = font(self.base_font * ss)

        # 横向网格线
        for yv in yt:
            _px, py = self._map(self.xlim[0], yv)
            d.line([(self.x0, py), (self.x1, py)], fill=grid_color,
                   width=max(1, int(0.6 * ss)))
        # 纵向网格线
        for xv in xt:
            px, _py = self._map(xv, self.ylim[0])
            d.line([(px, self.y0), (px, self.y1)], fill=grid_color,
                   width=max(1, int(0.6 * ss)))

        # --- 柱状
        for bx0, bx1, by0, by1, color in self.bars:
            d.rectangle([min(bx0, bx1), min(by0, by1), max(bx0, bx1), max(by0, by1)],
                        fill=color)

        # --- 折线 / 散点
        for s in self.series:
            if s[0] == "scatter":
                _, pts, color, r = s
                for px, py in pts:
                    d.ellipse([px - r, py - r, px + r, py + r], fill=color)
            else:
                pts, color, w, dashed = s
                if dashed:
                    _draw_dashed(d, pts, color, w, 6 * ss, 5 * ss)
                else:
                    d.line(pts, fill=color, width=w, joint="curve")

        # --- 参考线
        for g in self.guides:
            if g[0] == "v":
                _, px, ya, yb, color, w, dashed = g
                seg = [(px, ya), (px, yb)]
            else:
                _, xa, py, xb, color, w, dashed = g
                seg = [(xa, py), (xb, py)]
            if dashed:
                _draw_dashed(d, seg, color, w, 7 * ss, 6 * ss)
            else:
                d.line(seg, fill=color, width=w)

        # --- 边框
        for seg in [((self.x0, self.y0), (self.x1, self.y0)),
                    ((self.x1, self.y0), (self.x1, self.y1)),
                    ((self.x1, self.y1), (self.x0, self.y1)),
                    ((self.x0, self.y1), (self.x0, self.y0))]:
            d.line(list(seg), fill=axis_color, width=max(1, int(1.1 * ss)))

        # --- X 轴刻度标签
        dec_x = _decimals(xt[1] - xt[0] if len(xt) > 1 else 1)
        for k, xv in enumerate(xt):
            px, _py = self._map(xv, self.ylim[0])
            d.line([(px, self.y1), (px, self.y1 + 5 * ss)], fill=axis_color,
                   width=max(1, int(1.1 * ss)))
            if self._xticklabels and k < len(self._xticklabels):
                label = str(self._xticklabels[k])
            else:
                label = f"{xv:.{dec_x}f}"
            d.text((px, self.y1 + 9 * ss), label, font=f_axis,
                   fill=txt_color, anchor="ma")

        # --- 左轴刻度标签
        dec_y = _decimals(yt[1] - yt[0] if len(yt) > 1 else 1)
        for yv in yt:
            _px, py = self._map(self.xlim[0], yv)
            d.line([(self.x0 - 5 * ss, py), (self.x0, py)], fill=axis_color,
                   width=max(1, int(1.1 * ss)))
            d.text((self.x0 - 9 * ss, py), f"{yv:.{dec_y}f}", font=f_axis,
                   fill=txt_color, anchor="rm")

        # --- 右轴刻度标签（次轴）
        if self._has_y2:
            y2t = self._y2ticks or nice_ticks(*self.y2lim, target=self.ytarget)[0]
            dec_y2 = _decimals(y2t[1] - y2t[0] if len(y2t) > 1 else 1)
            for yv in y2t:
                _px, py = self._map(self.xlim[1], yv, "y2")
                d.line([(self.x1, py), (self.x1 + 5 * ss, py)], fill=axis_color,
                       width=max(1, int(1.1 * ss)))
                d.text((self.x1 + 9 * ss, py), f"{yv:.{dec_y2}f}", font=f_axis,
                       fill=txt_color, anchor="lm")

        # --- 轴标题（仅 X 轴；Y 轴单位改由系列标签体现，避免与面板标题打架）
        f_lab = font(self.base_font * 1.05 * ss)
        if self.xlabel:
            d.text(((self.x0 + self.x1) / 2, self.y1 + 34 * ss), self.xlabel,
                   font=f_lab, fill=txt_color, anchor="ma")

        # --- 标注
        for n in self.notes:
            if len(n) == 7:
                px, py, text, color, anchor, size, bold = n
                f = font(size * ss, bold)
            else:
                px, py, text, color, anchor, size = n
                f = font(size * ss)
            d.text((px, py), text, font=f, fill=color, anchor=anchor)

        # --- 面板标题（绘图区上方第一行）
        if self.title:
            d.text((self.x0, self.y0 - 56 * ss), self.title,
                   font=font(self.base_font * 1.2 * ss, True),
                   fill=(15, 23, 42), anchor="la")

        # --- 图例（绘图区上方第二行，紧贴绘图区，左对齐，不遮挡数据）
        if self.legend_items:
            self._render_legend(d)

    def _render_legend(self, d):
        """图例画在绘图区上方的专属条带里，左对齐、单行排布，绝不压数据。"""
        ss = self.fig.ss
        f = font(self.base_font * 0.95 * ss)
        sw = 24 * ss          # 样例线宽
        gap = 18 * ss         # 项间距
        y = self.y0 - 24 * ss
        cx = self.x0
        for color, label, shape in self.legend_items:
            tw = d.textlength(label, font=f)
            if cx + sw + 8 * ss + tw > self.x1:
                break
            if shape == "line":
                d.line([(cx, y), (cx + sw, y)], fill=color, width=max(1, int(2 * ss)))
            elif shape == "dash":
                _draw_dashed(d, [(cx, y), (cx + sw, y)], color,
                             max(1, int(1.6 * ss)), 5 * ss, 4 * ss)
            elif shape == "dot":
                r_ = 4 * ss
                d.ellipse([cx + sw / 2 - r_, y - r_, cx + sw / 2 + r_, y + r_], fill=color)
            elif shape == "box":
                d.rectangle([cx, y - 6 * ss, cx + sw, y + 6 * ss], fill=color)
            d.text((cx + sw + 8 * ss, y), label, font=f,
                   fill=(51, 65, 85), anchor="lm")
            cx += sw + 8 * ss + tw + gap


def _draw_dashed(d, pts, color, width, on, off):
    """在折线路径上按 on/off 长度绘制虚线。"""
    if len(pts) < 2:
        return
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        dx, dy = x1 - x0, y1 - y0
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            continue
        ux, uy = dx / dist, dy / dist
        pos = 0.0
        draw_on = True
        while pos < dist:
            seg = on if draw_on else off
            seg = min(seg, dist - pos)
            if draw_on:
                d.line([(x0 + ux * pos, y0 + uy * pos),
                        (x0 + ux * (pos + seg), y0 + uy * (pos + seg))],
                       fill=color, width=width)
            pos += seg
            draw_on = not draw_on


# ---------------------------------------------------------------- 画布

class Figure:
    """整张图：标题、副标题、多个 Panel、统一保存。"""

    def __init__(self, width=1600, height=900, title="", subtitle="",
                 bg=(255, 255, 255), supersample=2, footer=""):
        self.ss = supersample
        self.px_w = width * self.ss
        self.px_h = height * self.ss
        self.w, self.h = width, height
        self.img = Image.new("RGB", (self.px_w, self.px_h), bg)
        self.draw = ImageDraw.Draw(self.img)
        self.title = title
        self.subtitle = subtitle
        self.footer = footer
        self.panels = []

    def panel(self, rect, **kw):
        p = Panel(self, rect, **kw)
        self.panels.append(p)
        return p

    def save(self, path):
        ss = self.ss
        d = self.draw
        # 标题区：按标题字高动态下移副标题，避免两行压字
        y = 0.040 * self.px_h
        t_size = int(self.w / 40)
        if self.title:
            d.text((0.055 * self.px_w, y), self.title,
                   font=font(t_size * ss, True), fill=(15, 23, 42), anchor="la")
            y += t_size * ss + 10 * ss
        if self.subtitle:
            s_size = int(self.w / 78)
            d.text((0.055 * self.px_w, y), self.subtitle,
                   font=font(s_size * ss), fill=(100, 116, 139), anchor="la")
        for p in self.panels:
            p.render(self.img, d)
        if self.footer:
            d.text((0.06 * self.px_w, self.px_h - 34 * ss), self.footer,
                   font=font(int(self.w / 92) * ss), fill=(148, 163, 184), anchor="la")
        # 降采样抗锯齿
        out = self.img.resize((self.w, self.h), Image.LANCZOS)
        out.save(path, "PNG", optimize=True)
        return path
