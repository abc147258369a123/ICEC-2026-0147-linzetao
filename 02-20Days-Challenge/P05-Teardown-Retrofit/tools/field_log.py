# -*- coding: utf-8 -*-
"""
field_log.py —— 工坊现场记录助手

## 为什么需要它

ICEC 考核大纲对第二阶段有一条**准入条件**（不是加分项）：

> 「强制要求提交跨多日连续过程数据（process_logs/）」

意味着从 10/23 拆解开始到 11/24 封仓，**每天都必须有真实的过程记录**。
如果靠手写 Excel 或临时记在纸上再誊抄，一定会断——

- 誊抄时会丢失精确时间戳（面试第 ① 项查的就是时间戳能否对上照片 EXIF）
- 会漏记失败和重试（而第 ④ 项「受挫归因」恰恰要看这些）
- 会拖延，导致提交时间线不连续

这个工具的目标：**在工位上按一次回车，就把一条带真实时间戳的记录落盘。**

## 用法

交互模式（适合边做边记）：

    python tools/field_log.py

单条模式（适合快速记一条）：

    python tools/field_log.py "拆下后盖，4 个卡扣" -c teardown -v 4 -u pcs

失败记录（很重要，别跳过）：

    python tools/field_log.py "VIN 对地阻值异常" -c measure -v 1.2 -u Mohm -s suspect

## 输出

写入 `process_logs/YYYYMMDD.csv`，列：

    时间戳, 类别, 事件, 数值, 单位, 状态, 备注

- 时间戳为本地真实时间，精确到秒
- 文件用 UTF-8-BOM 保存，Excel 双击直接正常打开
- 每天一个文件，便于「每天一次提交」

## 类别（category）取值

    teardown  拆解      measure  测量      photo   拍照
    debug     排障      design   设计       assemble 装配
    poweron   通电验证  doc      文档

## 状态（status）取值

    ok        正常完成
    fail      失败
    suspect   读数可疑，待复核
    retry     重试
"""

import argparse
import csv
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.normpath(os.path.join(HERE, "..", "process_logs"))

HEADER = ["时间戳", "类别", "事件", "数值", "单位", "状态", "备注"]

CATEGORIES = ["teardown", "measure", "photo", "debug",
              "design", "assemble", "poweron", "doc"]
STATUSES = ["ok", "fail", "suspect", "retry"]


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def append_row(log_dir, ts, category, event, value, unit, status, note):
    ensure_dir(log_dir)
    day = ts[:10].replace("-", "")
    path = os.path.join(log_dir, f"{day}.csv")
    new_file = not os.path.exists(path)
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(HEADER)
        w.writerow([ts, category, event, value, unit, status, note])
    return path


def ask(prompt, default="", choices=None):
    while True:
        suffix = f" [{default}]" if default else ""
        if choices:
            suffix += f" ({'/'.join(choices)})"
        raw = input(f"{prompt}{suffix}: ").strip()
        if not raw:
            if default:
                return default
            print("  这一项必须填。")
            continue
        if choices and raw not in choices:
            print(f"  只能填 {choices} 之一。")
            continue
        return raw


def interactive(log_dir):
    print("=" * 58)
    print(" ICEC 工坊现场记录  |  回车提交，Ctrl+C 退出")
    print("=" * 58)
    while True:
        try:
            print()
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"时间戳：{ts}")
            cat = ask("类别", "teardown", CATEGORIES)
            event = ask("做了什么 / 观察到什么")
            value = input("数值（可空）: ").strip()
            unit = input("单位（可空）: ").strip() if value else ""
            status = ask("状态", "ok", STATUSES)
            note = input("备注（可空）: ").strip()
            path = append_row(log_dir, ts, cat, event, value, unit, status, note)
            print(f"  -> 已写入 {os.path.basename(path)}")
            print(f'  提示：别忘了收工前  git add . && git commit -m '
                  f'"day{datetime.now().strftime("%d")}: {event[:20]}"')
        except KeyboardInterrupt:
            print("\n退出。记得提交今天的记录：")
            print('  git add . && git commit -m "logs: 今日现场记录" && git push')
            return 0


def main():
    ap = argparse.ArgumentParser(
        description="ICEC 工坊现场记录助手（写入 process_logs/）")
    ap.add_argument("event", nargs="?", help="事件描述；省略则进入交互模式")
    ap.add_argument("-c", "--category", default="teardown", choices=CATEGORIES)
    ap.add_argument("-v", "--value", default="")
    ap.add_argument("-u", "--unit", default="")
    ap.add_argument("-s", "--status", default="ok", choices=STATUSES)
    ap.add_argument("-n", "--note", default="")
    ap.add_argument("--out", default=LOG_DIR, help="日志目录（默认 process_logs/）")
    ap.add_argument("--at", default=None, help="指定时间戳，格式 YYYY-MM-DD HH:MM:SS")
    args = ap.parse_args()

    if args.event:
        ts = args.at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        path = append_row(args.out, ts, args.category, args.event,
                          args.value, args.unit, args.status, args.note)
        print(f"已写入 {path}")
        print(f"  {ts} | {args.category} | {args.event} | "
              f"{args.value}{args.unit} | {args.status}")
        return 0

    return interactive(args.out)


if __name__ == "__main__":
    sys.exit(main())
