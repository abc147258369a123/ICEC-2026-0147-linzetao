#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
host_logger.py —— 固件串口数据落盘器

固件每 0.5 s 打一行 CSV。这个脚本把串口数据原样存成带日期时间戳的文件，
直接写进 process_logs/，满足第二阶段「跨多日连续过程数据」的准入要求。

## 用法

    python host_logger.py --port COM5
    python host_logger.py --port COM5 --hours 12      # 连续记 12 小时
    python host_logger.py --port COM5 --out ../process_logs

## 依赖

    python -m pip install pyserial

## 输出

    process_logs/YYYYMMDD_soh_串口记录.csv

文件头固定为：

    pc_time, t_ms, V_bus, I, P, Ah_out, Ah_in, Wh_out, Wh_in, R_mohm, SOH_R, SOH_C, flag

- `pc_time` 是**电脑收到该行的真实时间**（本地时区），和固件的 `t_ms` 相对时间互为校验
- 固件以 `#` 开头的注释行会被跳过
- 脚本崩溃时已写入的内容不会丢（每行 flush）

## 为什么要 `pc_time`

面试第 ① 项会把三类时间戳交叉比对：
日志时间 / 照片 EXIF / git 提交时间。
固件的 `millis()` 一掉电就归零，无法独立证明「这段数据是那天采的」；
靠电脑本地时间落盘才能和另外两类对得上。
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime

# pyserial 延迟导入：这样 `--help` 和参数校验在没装 pyserial 时也能正常用，
# 不会一上来就报 ImportError 让人以为脚本坏了。
serial = None


def _load_serial():
    global serial
    if serial is not None:
        return serial
    try:
        import serial as _s
    except ImportError:
        sys.exit("缺少 pyserial。先执行：  python -m pip install pyserial")
    serial = _s
    return serial

COLS = ["pc_time", "t_ms", "V_bus", "I", "P",
        "Ah_out", "Ah_in", "Wh_out", "Wh_in",
        "R_mohm", "SOH_R", "SOH_C", "flag"]


def main():
    ap = argparse.ArgumentParser(description="把 SOH 固件串口数据落盘为 CSV")
    ap.add_argument("--port", required=True, help="串口号，如 COM5 或 /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "..", "process_logs"))
    ap.add_argument("--hours", type=float, default=0, help="0 表示一直记到按 Ctrl+C")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    serial_mod = _load_serial()

    os.makedirs(args.out, exist_ok=True)
    day = datetime.now().strftime("%Y%m%d")
    path = os.path.join(args.out, f"{day}_soh_串口记录.csv")
    new = not os.path.exists(path)

    ser = serial_mod.Serial(args.port, args.baud, timeout=1)
    time.sleep(1.0)
    ser.reset_input_buffer()

    deadline = time.time() + args.hours * 3600 if args.hours > 0 else None
    n = 0
    unknown = 0

    print(f"串口 {args.port} @ {args.baud}  →  {path}")
    print("按 Ctrl+C 停止。每行都会立即落盘，不会丢。")

    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
            f.flush()

        try:
            while True:
                if deadline and time.time() > deadline:
                    print("\n达到设定时长，停止。")
                    break
                raw = ser.readline().decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                if raw.startswith("#"):
                    print(f"  [设备] {raw}")
                    continue

                parts = [p.strip() for p in raw.split(",")]
                if len(parts) != 12:
                    unknown += 1
                    continue

                # 固件首字段是 t_ms，补上电脑本地时间
                w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]] + parts)
                if n % 20 == 0:
                    f.flush()
                n += 1
                if not args.quiet and n % 20 == 0:
                    print(f"  已记录 {n} 行  |  V={parts[1]}  I={parts[2]}  R={parts[8]}")
        except KeyboardInterrupt:
            print("\n用户中断。")
        finally:
            f.flush()
            ser.close()

    print(f"完成：{n} 行有效记录，{unknown} 行格式不符被跳过。")
    print(f"文件：{path}")
    print("别忘了提交：git add . && git commit -m \"logs: SOH 串口记录\" && git push")


if __name__ == "__main__":
    main()
