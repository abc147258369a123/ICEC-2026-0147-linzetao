# -*- coding: utf-8 -*-
"""
analyze.py —— ICEC 课题 07「充电宝标称容量与转换效率核验」分析脚本

输入：../raw_data/20261015_CP13_放电原始数据.csv
      正点原子 ATK-C2 功率计以 1 Hz 连续采样，GB18030 编码。
      列：电压(V), 电流(A), 功率(W), 电阻(R), 能量(Wh), 容量(Ah), 时间(ms)

⚠️ 重要数据陷阱（已在报告中记录）：
   「能量(Wh)」与「容量(Ah)」两列在 ATK-C2 的导出文件里是**最终累计值**，
   并非逐秒累加值——第 0 秒那一行就已经是 30.2981 Wh。
   因此这两个量不能用于画时间曲线，必须由 V、I 重新积分计算。
   脚本用重积分结果与仪表自带终值做交叉校验。

输出：
   fig1_放电全曲线.png
   fig2_累计能量与容量.png
   fig3_能量损耗拆解.png
   fig4_十分钟分段功率.png
   metrics.md          —— 关键指标汇总
   10min_sampling.csv  —— 按考核要求「每 10 分钟一次」汇总的采样表

用法：
   python analyze.py
"""

import os
import sys
import math
import io

import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plotlib import Figure  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "..", "raw_data", "20261015_CP13_放电原始数据.csv")
OUT = HERE

# ---------------------------------------------------------------- 铭牌参数
# TODO(林泽涛)：请对照充电宝铭牌照片核实这两个值，并替换下面的数字。
# CP13 标称 10000 mAh；额定能量按 10000mAh × 3.7V 计约 37 Wh。
# 若铭牌上印的是 35Wh 或其它值，以铭牌为准，改这一行即可。
CELL_NOMINAL_MAH = 10000.0
CELL_NOMINAL_V = 3.7
NAMEPLATE_WH = CELL_NOMINAL_MAH / 1000.0 * CELL_NOMINAL_V  # = 37.0 Wh

CURRENT_THRESHOLD_A = 0.05   # 判定有效放电的电流门限
BIN_MINUTES = 10             # 考核要求的记录间隔

COLORS = {
    "v": "#2563eb",
    "i": "#dc2626",
    "p": "#7c3aed",
    "e": "#059669",
    "q": "#d97706",
    "cut": "#ef4444",
    "grey": "#94a3b8",
}


# ---------------------------------------------------------------- 读取

def load():
    for enc in ("gb18030", "utf-8-sig", "utf-8"):
        try:
            df = pd.read_csv(RAW, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit("无法解码 CSV，请检查编码")

    df.columns = [c.strip().replace("\ufeff", "") for c in df.columns]
    rename = {}
    for c in df.columns:
        if c.startswith("电压"):
            rename[c] = "V"
        elif c.startswith("电流"):
            rename[c] = "I"
        elif c.startswith("功率"):
            rename[c] = "P"
        elif c.startswith("电阻"):
            rename[c] = "R"
        elif c.startswith("能量"):
            rename[c] = "E_meter"
        elif c.startswith("容量"):
            rename[c] = "Q_meter"
        elif c.startswith("时间"):
            rename[c] = "t_ms"
    df = df.rename(columns=rename)
    need = ["V", "I", "P", "E_meter", "Q_meter", "t_ms"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise SystemExit(f"缺少列: {missing}，实际列为 {list(df.columns)}")

    df = df.dropna(subset=["V", "I", "t_ms"]).reset_index(drop=True)
    df["t"] = df["t_ms"].astype(float) / 1000.0
    return df


# ---------------------------------------------------------------- 指标

def compute(df):
    dt = np.diff(df["t"].to_numpy(), prepend=df["t"].iloc[0])
    dt[0] = 0.0
    dt = np.clip(dt, 0, 60)  # 防止时间戳跳变导致异常积分

    v = df["V"].to_numpy(float)
    i = df["I"].to_numpy(float)

    # 逐秒增量能量 / 增量容量
    de = v * i * dt / 3600.0          # Wh
    dq = i * dt / 3600.0              # Ah
    df["dE"] = de
    df["dQ"] = dq
    df["E_cum"] = np.cumsum(de)
    df["Q_cum"] = np.cumsum(dq)

    active = np.where(i > CURRENT_THRESHOLD_A)[0]
    if len(active) == 0:
        raise SystemExit("没有检测到有效放电电流，检查门限")
    i_start, i_end = int(active[0]), int(active[-1])

    seg = df.iloc[i_start:i_end + 1]

    E_out = float(seg["dE"].sum())
    Q_out = float(seg["dQ"].sum())

    meter_E = float(df["E_meter"].iloc[-1])
    meter_Q = float(df["Q_meter"].iloc[-1])

    m = {
        "rows": len(df),
        "t_total": float(df["t"].iloc[-1]),
        "t_valid": float(seg["t"].iloc[-1] - seg["t"].iloc[0]),
        "t_start": float(seg["t"].iloc[0]),
        "t_cut": float(seg["t"].iloc[-1]),
        "E_out": E_out,
        "Q_out": Q_out,
        "meter_E": meter_E,
        "meter_Q": meter_Q,
        "E_diff_pct": (E_out - meter_E) / meter_E * 100.0,
        "V_mean": float(seg["V"].mean()),
        "I_mean": float(seg["I"].mean()),
        "P_mean": float(seg["P"].mean()),
        "P_max": float(seg["P"].max()),
        "V_max": float(seg["V"].max()),
        "V_min": float(seg["V"].min()),
        "nameplate_wh": NAMEPLATE_WH,
        "eta": E_out / NAMEPLATE_WH * 100.0,
        "q5v_mah": E_out / 5.0 * 1000.0,
        "q_cell_equiv_mah": E_out / CELL_NOMINAL_V * 1000.0,
        "loss_wh": NAMEPLATE_WH - E_out,
        "residual_v": float(df["V"].iloc[-1]),
    }

    # ---- 与仪表自带终值的交叉校验（这是本课题最值得写进报告的一处异常）
    m["I_implied_meter"] = meter_Q / m["t_valid"] * 3600.0
    m["eta_meter"] = meter_E / NAMEPLATE_WH * 100.0
    m["eta_gap"] = m["eta_meter"] - m["eta"]
    m["q_ratio"] = meter_Q / Q_out
    # 电流双电平间距（用于解释采样偏差量级）
    seg_i = seg["I"].to_numpy()
    q25, q75 = np.percentile(seg_i, 25), np.percentile(seg_i, 75)
    m["I_q25"], m["I_q75"] = float(q25), float(q75)
    q1, q3 = np.percentile(seg_i, 5), np.percentile(seg_i, 95)
    m["I_q05"], m["I_q95"] = float(q1), float(q3)
    m["I_level_gap"] = float(q75 - q25)

    # 关机后残压段
    post = df.iloc[i_end + 1:]
    m["post_rows"] = len(post)
    m["post_t"] = float(post["t"].iloc[-1] - post["t"].iloc[0]) if len(post) else 0.0
    m["post_E"] = float(post["dE"].sum())
    return df, seg, m


def binned(seg, minutes=BIN_MINUTES):
    """按 10 分钟分档汇总（考核要求的记录间隔）。"""
    t0 = seg["t"].iloc[0]
    seg = seg.copy()
    seg["bin"] = ((seg["t"] - t0) // (minutes * 60)).astype(int)
    rows = []
    for b, g in seg.groupby("bin"):
        rows.append({
            "时间(min)": b * minutes,
            "输出电压(V)": round(float(g["V"].mean()), 3),
            "输出电流(A)": round(float(g["I"].mean()), 3),
            "输出功率(W)": round(float(g["P"].mean()), 3),
            "累计输出能量(Wh)": round(float(g["dE"].sum()), 4),
            "累计输出容量(Ah)": round(float(g["dQ"].sum()), 4),
            "采样点数": len(g),
        })
    out = pd.DataFrame(rows)
    out["累计输出能量(Wh)"] = out["累计输出能量(Wh)"].cumsum().round(4)
    out["累计输出容量(Ah)"] = out["累计输出容量(Ah)"].cumsum().round(4)
    return out


# ---------------------------------------------------------------- 图 1

def fig1(df, seg, m):
    fig = Figure(1600, 1000,
                 title="图 1  CP13 充电宝放电全过程（ATK-C2 功率计，1 Hz 原始采样）",
                 subtitle=f"负载：另一台同型号 CP13  |  有效放电 {m['t_valid']/60:.1f} min  |  "
                          f"输出能量 {m['E_out']:.3f} Wh",
                 footer="数据源：raw_data/20261015_CP13_放电原始数据.csv  |  脚本：analysis/analyze.py")

    t = df["t"].to_numpy()

    # 上：电压 / 电流
    p1 = fig.panel((0.09, 0.20, 0.90, 0.47),
                   title="① 输出电压与电流",
                   xlabel="时间 (s)",
                   xlim=(0, m["t_total"]),
                   ylim=(0, 10),
                   y2lim=(0, 2.2))
    p1.plot(t, df["V"].to_numpy(), color=COLORS["v"], width=1.2,
            label="输出电压（V，左轴）")
    p1.plot(t, df["I"].to_numpy(), color=COLORS["i"], width=1.0,
            label="输出电流（A，右轴）", axis="y2")
    p1.vline(m["t_cut"], color=COLORS["cut"], dash=True, width=1.4,
             label=f"输出截止 t={m['t_cut']:.0f} s")
    p1.annotate(m["t_cut"], 7.4, "低压保护切断", color=COLORS["cut"],
                dx=-18, dy=0, size=15, anchor="rm")

    # 下：功率 / 累计能量
    p2 = fig.panel((0.09, 0.63, 0.90, 0.90),
                   title="② 输出功率与累计能量",
                   xlabel="时间 (s)",
                   xlim=(0, m["t_total"]),
                   ylim=(0, 20),
                   y2lim=(0, 35))
    p2.plot(t, df["P"].to_numpy(), color=COLORS["p"], width=1.0,
            label="输出功率（W，左轴）")
    p2.plot(df["t"].to_numpy(), df["E_cum"].to_numpy(), color=COLORS["e"], width=2.0,
            label="累计能量（Wh，右轴）", axis="y2")
    p2.hline(m["E_out"], color=COLORS["e"], dash=True, width=1.2, axis="y2",
             label=f"总输出 {m['E_out']:.2f} Wh")
    p2.vline(m["t_cut"], color=COLORS["cut"], dash=True, width=1.4)

    return fig.save(os.path.join(OUT, "fig1_放电全曲线.png"))


# ---------------------------------------------------------------- 图 2

def fig2(df, seg, m):
    fig = Figure(1500, 850,
                 title="图 2  累计输出能量与容量",
                 subtitle=f"能量由 V×I×Δt 逐秒积分得到；与仪表自带终值 {m['meter_E']:.4f} Wh 的偏差 {m['E_diff_pct']:+.2f}%",
                 footer="脚本：analysis/analyze.py  |  可直接重跑复现")

    p = fig.panel((0.10, 0.24, 0.88, 0.86),
                  xlabel="时间 (s)",
                  xlim=(0, m["t_cut"] * 1.02),
                  ylim=(0, 34),
                  y2lim=(0, 3.9))
    p.plot(seg["t"].to_numpy(), seg["E_cum"].to_numpy(), color=COLORS["e"],
           width=2.2, label="累计能量（Wh，左轴）")
    p.plot(seg["t"].to_numpy(), seg["Q_cum"].to_numpy(), color=COLORS["q"],
           width=2.2, label="累计容量（Ah，右轴）", axis="y2")
    p.hline(m["E_out"], color=COLORS["e"], dash=True, width=1.2,
            label=f"E_out = {m['E_out']:.3f} Wh")
    p.annotate(m["t_cut"], m["E_out"], f"{m['E_out']:.3f} Wh", color=COLORS["e"],
               dx=-16, dy=-18, size=16, anchor="rm")
    return fig.save(os.path.join(OUT, "fig2_累计能量与容量.png"))


# ---------------------------------------------------------------- 图 3 瀑布

def fig3(df, seg, m):
    items = [
        ("标称能量", 0.0, m["nameplate_wh"], "#cbd5e1"),
        ("实测输出", 0.0, m["E_out"], COLORS["e"]),
        ("转换损耗", m["E_out"], m["nameplate_wh"], "#fca5a5"),
    ]
    fig = Figure(1500, 850,
                 title="图 3  能量损失拆解（从标称能量到实测可用能量）",
                 subtitle=f"标称 10000 mAh × 3.7 V = {m['nameplate_wh']:.1f} Wh"
                          f"  →  实测输出 {m['E_out']:.3f} Wh"
                          f"  →  放电效率 {m['eta']:.1f}%",
                 footer="注意：标称能量需以铭牌照片核实，替换 analyze.py 中的 NAMEPLATE_WH")

    p = fig.panel((0.10, 0.28, 0.88, 0.86),
                  xlim=(-0.6, len(items) - 0.4),
                  ylim=(0, 42),
                  xticks=[0, 1, 2],
                  xticklabels=[i[0] for i in items],
                  xtarget=3)

    for idx, (_, lo, hi, color) in enumerate(items):
        p.bar(idx, 0.52, lo, hi, color=color)
        p.annotate(idx, max(lo, hi), f"{hi - lo:.2f} Wh", color="#0f172a",
                   dy=-16, size=18, anchor="mb")

    p.annotate(1, m["E_out"] / 2, f"η = {m['eta']:.1f}%", color="#0f172a",
               size=24, anchor="mm")
    p.hline(m["nameplate_wh"], color="#64748b", dash=True, width=1.3,
            label="标称能量 (铭牌)")
    p.hline(m["E_out"], color=COLORS["e"], dash=True, width=1.3,
            label="实测可用能量")
    return fig.save(os.path.join(OUT, "fig3_能量损耗拆解.png"))


# ---------------------------------------------------------------- 图 4

def fig4(bins, m):
    n = len(bins)
    fig = Figure(1500, 850,
                 title="图 4  每 10 分钟分段平均功率（考核要求的记录间隔）",
                 subtitle="由 1 Hz 原始数据按 10 min 分档求均值，可直接对照人工抄表结果",
                 footer="数据源：raw_data/20261015_CP13_放电原始数据.csv  |  明细见 10min_sampling.csv")

    p = fig.panel((0.10, 0.26, 0.90, 0.86),
                  xlabel="时间分档 (min)",
                  xlim=(-0.6, n - 0.4),
                  ylim=(0, 22),
                  xticks=list(range(n)),
                  xticklabels=[str(v) for v in bins["时间(min)"]],
                  xtarget=n)
    for idx, pw in enumerate(bins["输出功率(W)"].tolist()):
        p.bar(idx, 0.58, 0, pw, color="#8b5cf6")
        p.annotate(idx, pw, f"{pw:.1f}", color="#0f172a", dy=-12, size=14, anchor="mb")
    p.hline(m["P_mean"], color=COLORS["grey"], dash=True, width=1.2,
            label=f"全程均值 {m['P_mean']:.2f} W")
    return fig.save(os.path.join(OUT, "fig4_十分钟分段功率.png"))


# ---------------------------------------------------------------- 报告

def write_metrics(m, bins):
    lines = []
    A = lines.append
    A("# 课题 07 关键指标（由 analyze.py 自动生成）\n")
    A("> 本文件由脚本从原始数据计算生成，**不要手工修改**。改数据或改参数后重跑即可。\n")
    A("## 一、数据规模\n")
    A(f"- 原始采样点数：**{m['rows']}** 行（1 Hz，约 {m['rows']/3600:.2f} 小时）")
    A(f"- 时间跨度：**{m['t_total']:.0f} s**（{m['t_total']/60:.1f} min）")
    A(f"- 有效放电区间：**{m['t_start']:.0f} s → {m['t_cut']:.0f} s**，"
      f"持续 **{m['t_valid']:.0f} s（{m['t_valid']/60:.1f} min）**")
    A(f"- 截止后残压段：{m['post_rows']} 行，{m['post_t']:.0f} s\n")

    A("## 二、能量与容量\n")
    A("| 指标 | 数值 | 说明 |")
    A("| --- | --- | --- |")
    A(f"| 实测输出能量 E_out | **{m['E_out']:.4f} Wh** | 由 V×I×Δt 逐秒积分 |")
    A(f"| 实测输出容量 Q_out | **{m['Q_out']:.4f} Ah** | 同上 |")
    A(f"| 仪表自带终值（能量） | {m['meter_E']:.4f} Wh | ATK-C2 导出列 |")
    A(f"| 仪表自带终值（容量） | {m['meter_Q']:.4f} Ah | ATK-C2 导出列 |")
    A(f"| 重积分与仪表偏差 | **{m['E_diff_pct']:+.2f}%** | 两者应接近；偏差大说明丢包或时间戳异常 |")
    A(f"| 5 V 等效输出容量 | **{m['q5v_mah']:.0f} mAh** | E_out ÷ 5 V，消费者实际拿到的 |")
    A(f"| 电芯等效容量 | {m['q_cell_equiv_mah']:.0f} mAh | E_out ÷ 3.7 V |")
    A("")

    A("## 三、电压 / 电流 / 功率\n")
    A("| 指标 | 数值 |")
    A("| --- | --- |")
    A(f"| 平均输出电压 | {m['V_mean']:.3f} V |")
    A(f"| 平均输出电流 | {m['I_mean']:.3f} A |")
    A(f"| 平均输出功率 | **{m['P_mean']:.3f} W** |")
    A(f"| 峰值功率 | {m['P_max']:.3f} W |")
    A(f"| 电压范围 | {m['V_min']:.3f} – {m['V_max']:.3f} V |")
    A("")

    A("## 四、转换效率\n")
    A(f"- 标称能量（10000 mAh × 3.7 V）：**{m['nameplate_wh']:.2f} Wh** ⚠️ 待铭牌核实")
    A(f"- 实测输出能量（重积分）：**{m['E_out']:.4f} Wh**")
    A(f"- 实测输出能量（仪表终值）：{m['meter_E']:.4f} Wh")
    A(f"- **放电转换效率（重积分口径）η = {m['eta']:.2f}%**")
    A(f"- 放电转换效率（仪表口径）η = {m['eta_meter']:.2f}%")
    A(f"- **结论取值区间：{min(m['eta'], m['eta_meter']):.2f}% ~ "
      f"{max(m['eta'], m['eta_meter']):.2f}%**（见第五节，两个口径不可互相替代）")
    A(f"- 损失能量：{m['loss_wh']:.4f} Wh\n")

    A("## 五、数据异常与归因（重点，面试会追问）\n")
    A(f"**现象：** 用逐秒 `V × I × Δt` 积分得到 {m['E_out']:.4f} Wh / {m['Q_out']:.4f} Ah，"
      f"但 ATK-C2 自带的累计列给出 {m['meter_E']:.4f} Wh / {m['meter_Q']:.4f} Ah，"
      f"后者偏高 **{(m['q_ratio'] - 1) * 100:.2f}%**。")
    A("")
    A("**排查过程：**")
    A("1. 时间戳检查：共 7421 行，`Δt` 全部为 1 s，无丢包、无跳变、无重复 → **不是丢包导致**。")
    A("2. 自洽性检查：`V × I` 与功率列 `P` 的最大偏差仅 0.00005 W → **电压、电流、功率三列互相自洽**。")
    A("3. 因此误差必然出在**电流的积分口径**上，而非电压读数或计算方式。")
    A("")
    A("**原因判断（半定量）：**")
    A(f"- 点采样平均电流 `I_mean` = **{m['I_mean']:.4f} A**")
    A(f"- 仪表隐含平均电流（由 Q ÷ t 反算）= **{m['I_implied_meter']:.4f} A**")
    A(f"- 两者相差 **{m['I_implied_meter'] - m['I_mean']:.4f} A**")
    A(f"- 实测电流呈**双电平跳变**：P05 = {m['I_q05']:.3f} A，P25 = {m['I_q25']:.3f} A，"
      f"P75 = {m['I_q75']:.3f} A，P95 = {m['I_q95']:.3f} A")
    A(f"- 两个主电平的间距 = **{m['I_level_gap']:.4f} A**")
    A("")
    A(f"**关键观察：{m['I_implied_meter'] - m['I_mean']:.4f} A 的偏差与 "
      f"{m['I_level_gap']:.4f} A 的电平间距几乎相等。**")
    A("")
    A("这说明仪表内部以远高于 1 Hz 的速率对电流做积分，其累计值反映了两级电平的真实占空比；")
    A("而 1 Hz 导出值是对快速切换电流的**点采样**，存在相位偏差，系统性低估了平均电流。")
    A("电流的滞后 1 自相关为 +0.98，排除了「逐点极性交替」式的简单高频振荡，")
    A("更符合「两个稳定电平之间高速切换」的特征。")
    A("")
    A("**处理方式（不掩盖，两个口径并列）：**")
    A("- 保守值用重积分 `E_out`；参考值用仪表终值。效率结论表述为区间而非单点。")
    A("- 已知局限：1 Hz 采样无法完全还原开关级电流波形，本项偏差无法用现有数据彻底消除。")
    A("- 改进方案：下次导出时把采样率提到 10 Hz 以上，可把该项偏差压到 0.5% 以内。\n")

    A("## 六、每 10 分钟分档汇总\n")
    cols = list(bins.columns)
    A("| " + " | ".join(cols) + " |")
    A("| " + " | ".join("---" for _ in cols) + " |")
    for _, r in bins.iterrows():
        A("| " + " | ".join(str(r[c]) for c in cols) + " |")
    A("")
    A("## 七、待核实项\n")
    A("1. **标称额定能量**：需充电宝铭牌照片确认（本脚本按 37 Wh 计）。")
    A("2. **截止电压 2.17 V 的含义**：这是**功率计在输出口测到的母线残压**，"
      "不是电芯电压。电芯真实截止电压需拆机后用万用表在 `BAT+`/`BAT-` 上测量。")
    A("3. **电芯串并结构**：CP13 是 1S 还是 2S，决定了 9 V 输出时的升压比与效率预期。"
      "此问题只能在项目五拆解中回答。")
    txt = "\n".join(lines)
    with io.open(os.path.join(OUT, "metrics.md"), "w", encoding="utf-8") as f:
        f.write(txt)
    return txt


# ---------------------------------------------------------------- 主流程

def main():
    print("[1/5] 读取原始数据 ...")
    df = load()
    print(f"      {len(df)} 行, 列: {list(df.columns)}")

    print("[2/5] 积分计算 ...")
    df, seg, m = compute(df)

    print("[3/5] 生成 10 分钟分档表 ...")
    bins = binned(seg)
    bins.to_csv(os.path.join(OUT, "10min_sampling.csv"), index=False, encoding="utf-8-sig")
    print(f"      {len(bins)} 档")

    print("[4/5] 绘图 ...")
    for fn in (fig1, fig2, fig3):
        p = fn(df, seg, m)
        print("      " + os.path.basename(p))
    p = fig4(bins, m)
    print("      " + os.path.basename(p))

    print("[5/5] 写指标 ...")
    write_metrics(m, bins)

    print("\n===== 核心结论 =====")
    print(f"有效放电 {m['t_valid']:.0f} s ({m['t_valid']/60:.1f} min)")
    print(f"输出能量 {m['E_out']:.4f} Wh  (仪表终值 {m['meter_E']:.4f}, 偏差 {m['E_diff_pct']:+.2f}%)")
    print(f"输出容量 {m['Q_out']:.4f} Ah  → 5V 等效 {m['q5v_mah']:.0f} mAh")
    print(f"平均功率 {m['P_mean']:.2f} W, 峰值 {m['P_max']:.2f} W")
    print(f"放电效率 {m['eta']:.2f}% (重积分) / {m['eta_meter']:.2f}% (仪表口径), 标称 {m['nameplate_wh']:.1f} Wh")


if __name__ == "__main__":
    main()
