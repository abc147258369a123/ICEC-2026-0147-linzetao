# -*- coding: utf-8 -*-
"""
make_diagrams.py —— 生成改造方案的系统框图与控制状态图

为什么用脚本画而不是手绘：
  1. 方案改动时（换了主控、加了器件）重跑一次就同步，不会出现图和文字不一致；
  2. 评审可以审「图是怎么来的」，而不是看一张来源不明的图片；
  3. 与本人 crop.js / plotlib.py 同一思路，不依赖任何绘图软件。

输出：
  04-Retrofit-Design/fig_系统框图.png
  04-Retrofit-Design/fig_控制状态图.png

用法：
  python tools/make_diagrams.py
"""

import math
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.normpath(os.path.join(HERE, "..", "04-Retrofit-Design"))

SS = 2  # 超采样倍率

FONT_PATH = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

_fc = {}


def _font(px, bold=False):
    key = (int(px), bold)
    if key in _fc:
        return _fc[key]
    try:
        f = ImageFont.truetype(FONT_BOLD if bold else FONT_PATH, int(px))
    except Exception:
        f = ImageFont.load_default()
    _fc[key] = f
    return f


def F(css_size, bold=False):
    """按 CSS 像素给字号，内部换算成超采样后的实际像素。"""
    return _font(css_size * SS, bold)


# 配色
NAVY = "#1F3864"
BLUE, BLUE_F = "#2E5C8A", "#EAF1F8"
GREEN_L, GREEN_F = "#548235", "#E2EFDA"
AMBER_L, AMBER_F = "#BF8F00", "#FFF2CC"
RED_L, RED_F = "#C00000", "#FCE4E4"
GREY_L, GREY_F = "#7F7F7F", "#F2F2F2"
SUB = "#4B5563"
MUTE = "#6B7280"


def P(v):
    return v * SS


def box(d, x, y, w, h, title, sub="", fill=BLUE_F, line=BLUE,
        tcolor=NAVY, tsize=17, ssize=12, radius=10, lw=2):
    d.rounded_rectangle([P(x), P(y), P(x + w), P(y + h)], radius=P(radius),
                        fill=fill, outline=line, width=lw)
    if sub:
        d.text((P(x + w / 2), P(y + h / 2 - 10)), title,
               font=F(tsize, True), fill=tcolor, anchor="mm")
        d.text((P(x + w / 2), P(y + h / 2 + 14)), sub,
               font=F(ssize), fill=SUB, anchor="mm")
    else:
        d.text((P(x + w / 2), P(y + h / 2)), title,
               font=F(tsize, True), fill=tcolor, anchor="mm")


def _head(d, x1, y1, x2, y2, color, lw, head):
    ang = math.atan2(y2 - y1, x2 - x1)
    for s in (+1, -1):
        a = ang + s * 0.42
        d.line([P(x2), P(y2), P(x2 - head * math.cos(a)), P(y2 - head * math.sin(a))],
               fill=color, width=lw)


def arrow(d, x1, y1, x2, y2, color=BLUE, lw=3, head=9, label=None,
          fsize=12, lcolor=SUB, lx=None, ly=None, anchor="mm"):
    d.line([P(x1), P(y1), P(x2), P(y2)], fill=color, width=lw)
    _head(d, x1, y1, x2, y2, color, lw, head)
    if label:
        d.text((P(lx if lx is not None else (x1 + x2) / 2),
                P(ly if ly is not None else (y1 + y2) / 2)),
               label, font=F(fsize), fill=lcolor, anchor=anchor)


def poly_arrow(d, pts, color=BLUE, lw=3, head=9):
    for i in range(len(pts) - 1):
        d.line([P(pts[i][0]), P(pts[i][1]), P(pts[i + 1][0]), P(pts[i + 1][1])],
               fill=color, width=lw)
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    _head(d, x1, y1, x2, y2, color, lw, head)


def dashed(d, x1, y1, x2, y2, color=GREY_L, lw=2, on=8, off=6):
    dist = math.hypot(x2 - x1, y2 - y1)
    if dist < 1:
        return
    ux, uy = (x2 - x1) / dist, (y2 - y1) / dist
    pos, draw_on = 0.0, True
    while pos < dist:
        seg = min(on if draw_on else off, dist - pos)
        if draw_on:
            d.line([P(x1 + ux * pos), P(y1 + uy * pos),
                    P(x1 + ux * (pos + seg)), P(y1 + uy * (pos + seg))],
                   fill=color, width=lw)
        pos += seg
        draw_on = not draw_on


# ================================================================ 图 1：系统框图

def fig_system():
    W, H = 1500, 860
    img = Image.new("RGB", (W * SS, H * SS), "white")
    d = ImageDraw.Draw(img)

    d.text((P(60), P(34)), "图 1  改造方案系统框图", font=F(28, True), fill=NAVY)
    d.text((P(60), P(80)), "旧充电宝电池健康度（SOH）监测  ·  ESP32-C3 + INA219",
           font=F(14), fill=MUTE)

    # ---------- 功率与信号主链
    y1, bh = 160, 84
    d.text((P(50), P(124)), "功 率 与 信 号 链", font=F(13, True), fill=BLUE)

    box(d, 50, y1, 186, bh, "电芯", "BAT+  3.0–4.2 V",
        fill=GREEN_F, line=GREEN_L, tcolor="#375623", ssize=11)
    box(d, 282, y1, 176, bh, "采样电阻", "0.05 Ω  1%  2512",
        fill=AMBER_F, line=AMBER_L, tcolor="#7F6000", ssize=11)
    box(d, 504, y1, 196, bh, "原板主控", "升压 / 充电 / 保护")
    box(d, 746, y1, 176, bh, "USB 输出", "5 V / 9 V")

    arrow(d, 236, y1 + bh / 2, 282, y1 + bh / 2, label="串入", lx=259, ly=150)
    arrow(d, 458, y1 + bh / 2, 504, y1 + bh / 2)
    arrow(d, 700, y1 + bh / 2, 746, y1 + bh / 2)

    # ---------- INA219
    y2 = 312
    box(d, 282, y2, 176, 92, "INA219", "V_bus + V_shunt", ssize=11,
        fill=AMBER_F, line=AMBER_L, tcolor="#7F6000")
    arrow(d, 330, y1 + bh, 330, y2, color=AMBER_L, lw=2, head=7)
    arrow(d, 412, y1 + bh, 412, y2, color=AMBER_L, lw=2, head=7)
    d.text((P(371), P(300)), "VIN+ / VIN−", font=F(11), fill="#7F6000", anchor="mm")

    # ---------- ESP32-C3
    box(d, 556, 296, 216, 124, "ESP32-C3", "10 Hz 采样 · 库仑计\n内阻阶跃 · SOH 计算",
        ssize=11)
    arrow(d, 458, y2 + 46, 556, 358, color=AMBER_L, lw=3,
          label="I²C", fsize=13, lcolor="#7F6000", lx=507, ly=336)

    # ---------- PC
    box(d, 872, y2, 200, 92, "PC 上位机", "串口落盘 → process_logs/",
        ssize=10, fill=GREY_F, line=GREY_L, tcolor="#3F3F3F")
    arrow(d, 772, 358, 872, 358, label="UART 115200", fsize=11, lx=822, ly=344)

    # ---------- 供电支路
    y3 = 540
    d.text((P(50), P(504)), "供 电 链", font=F(13, True), fill=GREY_L)
    box(d, 50, y3, 196, 84, "原板 VOUT", "5 V 输出轨", ssize=11)
    box(d, 306, y3, 172, 84, "LDO 3.3 V", "AMS1117 / ME6211", ssize=10,
        fill=GREY_F, line=GREY_L, tcolor="#3F3F3F")
    box(d, 556, y3, 216, 84, "ESP32 + INA219", "3.3 V 供电轨", ssize=11,
        fill=GREY_F, line=GREY_L, tcolor="#3F3F3F")

    arrow(d, 246, y3 + 42, 306, y3 + 42)
    arrow(d, 478, y3 + 42, 556, y3 + 42)
    dashed(d, 664, y3, 664, 420, color=GREY_L, lw=2)
    d.text((P(676), P(478)), "3.3 V", font=F(11), fill=GREY_L, anchor="lm")

    # ---------- 底部注释
    notes = [
        "注 1  采样电阻串在「电芯正极」与「原板 BAT+ 焊盘」之间，位于原板保护电路内侧，",
        "　　　因此继承了 IP3005B 类保护 IC 的过放 / 过流保护，不绕过原保护。",
        "注 2  ESP32 从原板 5 V 轨经 LDO 取电，不从电芯直接取（4.2 V 会超压）。",
    ]
    yy = 668
    for n in notes:
        d.text((P(60), P(yy)), n, font=F(12), fill=MUTE)
        yy += 24
    d.text((P(60), P(yy + 16)), "生成脚本：tools/make_diagrams.py（可重跑复现）",
           font=F(11), fill="#9CA3AF")

    out = os.path.join(OUTDIR, "fig_系统框图.png")
    img.resize((W, H), Image.LANCZOS).save(out, "PNG", optimize=True)
    return out


# ================================================================ 图 2：控制状态图

def fig_state():
    W, H = 1500, 880
    img = Image.new("RGB", (W * SS, H * SS), "white")
    d = ImageDraw.Draw(img)

    d.text((P(60), P(34)), "图 2  控制状态图", font=F(28, True), fill=NAVY)
    d.text((P(60), P(80)), "固件主循环的六个状态与迁移条件  ·  对应 firmware/src/main.cpp",
           font=F(14), fill=MUTE)

    bw, bh = 208, 96
    pos = {
        "S0": (70, 176),
        "S1": (400, 200),
        "S2": (790, 170),
        "S3": (790, 350),
        "S4": (400, 430),
        "S5": (1080, 176),
    }
    spec = {
        "S0": ("S0  BOOT", "初始化 I²C\n回读配置校验", BLUE_F, BLUE, NAVY, 16, 11),
        "S1": ("S1  IDLE", "10 Hz 采样 · 电流≈0", GREY_F, GREY_L, "#3F3F3F", 16, 11),
        "S2": ("S2  DISCHARGE", "累加 Ah/Wh · 内阻阶跃", GREEN_F, GREEN_L, "#375623", 15, 10),
        "S3": ("S3  CHARGE", "累加 Ah_in/Wh_in", BLUE_F, BLUE, NAVY, 16, 11),
        "S4": ("S4  DEGRADED", "flag 打 AGED", AMBER_F, AMBER_L, "#7F6000", 16, 11),
        "S5": ("S5  FAULT", "I²C 无应答\n配置不一致", RED_F, RED_L, "#7F0000", 16, 11),
    }
    for k, (x, y) in pos.items():
        t, s, f, l, c, ts, ss_ = spec[k]
        box(d, x, y, bw, bh, t, s, fill=f, line=l, tcolor=c, tsize=ts, ssize=ss_)

    x = {k: v[0] for k, v in pos.items()}
    y = {k: v[1] for k, v in pos.items()}

    # S0 -> S1
    arrow(d, x["S0"] + bw, y["S0"] + bh / 2, x["S1"], y["S0"] + bh / 2,
          label="配置一致", lx=(x["S0"] + bw + x["S1"]) / 2,
          ly=y["S0"] + bh / 2 - 16)

    # S0 -> S5：顶部走 y=130 泳道，避开标题区
    LANE = 130
    poly_arrow(d, [(x["S0"] + bw / 2, y["S0"]),
                   (x["S0"] + bw / 2, LANE),
                   (x["S5"] + bw / 2, LANE),
                   (x["S5"] + bw / 2, y["S5"])], color=RED_L, lw=3, head=9)
    d.text((P((x["S0"] + bw / 2 + x["S5"] + bw / 2) / 2), P(LANE - 14)),
           "无应答 / 校验失败", font=F(12), fill=RED_L, anchor="mm")

    # S1 <-> S2：两条平行水平泳道，不交叉
    yA, yB = y["S2"] + 40, y["S2"] + 66
    poly_arrow(d, [(x["S1"] + bw, yA), (x["S2"], yA)], color=GREEN_L, lw=3, head=9)
    d.text((P(x["S1"] + bw + 14), P(yA - 15)), "I > 0.05 A",
           font=F(12), fill=GREEN_L, anchor="lm")
    poly_arrow(d, [(x["S2"], yB), (x["S1"] + bw, yB)], color=GREEN_L, lw=3, head=9)
    d.text((P(x["S1"] + bw + 14), P(yB + 15)), "I < 0.05 A",
           font=F(12), fill=GREEN_L, anchor="lm")

    # S1 <-> S3：两条平行斜线，标签放在线外侧
    poly_arrow(d, [(x["S1"] + bw, 276), (x["S3"], 372)],
               color=BLUE, lw=3, head=9)
    d.text((P((x["S1"] + bw + x["S3"]) / 2), P(306)),
           "I < −0.05 A", font=F(12), fill=BLUE, anchor="mm")
    poly_arrow(d, [(x["S3"], 404), (x["S1"] + bw, 292)],
               color=BLUE, lw=3, head=9)
    d.text((P((x["S1"] + bw + x["S3"]) / 2), P(366)),
           "I < 0.05 A", font=F(12), fill=BLUE, anchor="mm")

    # S1 <-> S4：竖直双向
    arrow(d, x["S1"] + bw / 2 - 34, y["S1"] + bh, x["S4"] + bw / 2 - 34, y["S4"],
          color=AMBER_L, lw=3)
    d.text((P(x["S1"] + bw / 2 - 44), P(363)), "SOH < 60%", font=F(12),
           fill="#7F6000", anchor="rm")
    arrow(d, x["S4"] + bw / 2 + 34, y["S4"], x["S1"] + bw / 2 + 34, y["S1"] + bh,
          color=AMBER_L, lw=3)
    d.text((P(x["S1"] + bw / 2 + 44), P(363)), "恢复 / 更新", font=F(12),
           fill="#7F6000", anchor="lm")

    # 说明
    d.text((P(60), P(560)),
           "S5 FAULT 不自动恢复：硬件故障必须人工排查，自动重试会掩盖问题。",
           font=F(14, True), fill=RED_L)
    d.text((P(60), P(592)),
           "S2 / S3 用电流符号区分方向，不用电压趋势——负载撤掉时电压会回弹，靠电压判断会误判。",
           font=F(13), fill=MUTE)

    # 图例
    ly = 650
    d.text((P(60), P(ly)), "状态图例", font=F(13, True), fill=NAVY)
    items = [("正常", GREY_F, GREY_L), ("放电", GREEN_F, GREEN_L),
             ("充电", BLUE_F, BLUE), ("降级告警", AMBER_F, AMBER_L),
             ("故障", RED_F, RED_L)]
    lx = 150
    for name, f, l in items:
        d.rounded_rectangle([P(lx), P(ly - 4), P(lx + 26), P(ly + 16)], radius=P(4),
                            fill=f, outline=l, width=2)
        d.text((P(lx + 34), P(ly + 6)), name, font=F(12), fill=SUB, anchor="lm")
        lx += 128

    d.text((P(60), P(ly + 66)),
           "生成脚本：tools/make_diagrams.py（可重跑复现）", font=F(11), fill="#9CA3AF")

    out = os.path.join(OUTDIR, "fig_控制状态图.png")
    img.resize((W, H), Image.LANCZOS).save(out, "PNG", optimize=True)
    return out


if __name__ == "__main__":
    os.makedirs(OUTDIR, exist_ok=True)
    for f in (fig_system, fig_state):
        print("已生成:", f())
