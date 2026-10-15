# ICEC-2026-0147-linzetao

> **2026–2027 智能·创造者创新实验班（ICEC）选拔考核 · 过程仓库**
> Process portfolio for the ICEC 2026 Selection Assessment

| 项目 | 信息 |
| --- | --- |
| 姓名 | linzetao（`TODO: 填入中文姓名`） |
| 学号后四位 | 0147 |
| 就读层次 | `TODO: 2026级高职 / 2024级技师` |
| 所在二级学院 | `TODO: 填入学院` |
| 现就读专业 | `TODO: 填入专业全称` |
| 准考证编号 | `TODO: 填入报名后获得的编号` |
| 仓库建立日期 | 2026-10-15 |

---

## 一、我是谁（About Me）

> `TODO: 写 3–5 句，不要写成简历。招生组看的是「好奇心 × 行动力 × 韧性」。`

写作建议（写完删掉本行）：
- 你从什么时候开始玩硬件？第一件弄坏或弄成的东西是什么？
- 现在手上有什么能力？（会画原理图、会打样、会焊接、会写固件……）
- 你最想解决的一个真实问题是什么？

**已有工程积累（往届作品）**

- 自研 18650 充电宝板：主控 `IP5306`，锂电保护 `IP3005B`，USB-C 输入/输出，`AO3401A` + `SS34` 电源切换通路。**已完成原理图设计并打样出实物板。**
- 自研 PNG 裁剪/放大工具 `crop.js`：纯 JavaScript 实现，手写 PNG 解析（zlib inflate）、逐行滤波器还原（None/Sub/Up/Average/Paeth）、CRC32 校验与 RGBA 重编码，**零第三方依赖**。

---

## 二、选题总览（Selected Tasks）

本次考核我选择的主线是 **「电源类电子产品的实测 → 逆向 → 改造」**，
三个阶段共用同一条技术链路：用仪器把真实数据测出来，把电路看懂，再用低成本方案改好。

| 阶段 | 选题 | 权重 | 交付目录 |
| --- | --- | --- | --- |
| Stage 1 | 课题 07：充电宝/充电器标称容量与转换效率核验 | 20 分（与课题 05 合计） | [`01-Field-Discovery/T07-PowerBank-Efficiency/`](01-Field-Discovery/T07-PowerBank-Efficiency/) |
| Stage 1 | 课题 05：校园公共设施人机工程缺陷调研 | 20 分（与课题 07 合计） | [`01-Field-Discovery/T05-Ergonomics/`](01-Field-Discovery/T05-Ergonomics/) |
| Stage 2 | 项目五：旧电器拆解逆向、BOM 成本还原与智能化升级 | 60 分 | [`02-20Days-Challenge/P05-Teardown-Retrofit/`](02-20Days-Challenge/P05-Teardown-Retrofit/) |
| Stage 3 | 12 分钟 AI 深度面试 | 20 分 | 基于本仓库全部提交动态追问 |

**为什么这样选：** 课题 07 用仪器证实「标称容量与真实可用能量之间的差距」，
课题 05 训练「发现反直觉设计 → 给出百元内改造方案」的思维，
项目五 则把这两件事合起来做完整一遍：拆开一台真实旧电器，还原它的电路与成本，
再设计并动手验证一套智能化改造方案。三者构成一条完整证据链，而不是三个孤立作业。

---

## 三、仓库结构（Repository Layout）

```
ICEC-2026-0147-linzetao/
├── README.md                      # 本文件：个人简介与选题说明
├── 01-Field-Discovery/            # 【阶段一】基础素养实地测评
│   ├── T07-PowerBank-Efficiency/  # 课题 07：容量与转换效率核验
│   │   ├── raw_data/              # 原始实测数据（CSV / 仪器照片）
│   │   ├── analysis/              # 分析脚本与图表
│   │   └── REPORT.md              # 分析报告
│   └── T05-Ergonomics/            # 课题 05：设施人机工程缺陷调研
│       ├── raw_data/              # 实测尺寸、耗时原始记录
│       ├── analysis/              # 改造草图与预算表
│       └── REPORT.md
├── 02-20Days-Challenge/           # 【阶段二】工坊开放式项目挑战
│   └── P05-Teardown-Retrofit/     # 项目五：拆解 + BOM 还原 + 智能改造
│       ├── 01-Exploded-View/      # ①《实物爆炸拆解图谱》与分步照片  (15分)
│       ├── 02-Schematic-Trace/    # ② 芯片丝印溯源与供电/控制框图   (15分)
│       ├── 03-BOM-Cost/           # ③《批量 BOM 成本核算表》        (10分)
│       ├── 04-Retrofit-Design/    # ④《智能化升级改造方案》         (20分)
│       ├── firmware/              # 改造固件（ESP32）
│       └── process_logs/          # 跨多日连续过程数据（强制要求）
└── 03-AI-Collaboration/           # 【全程】AI 协同与关键排障对话记录
    ├── prompts/                   # 关键提问记录
    └── logs/                      # 排障对话导出
```

---

## 四、过程留痕原则（Process Integrity）

本仓库遵守考核大纲的诚信要求：

1. **所有 `raw_data/` 与 `process_logs/` 中的数据均为本人现场实测**，未做任何数值修改；
   原始文件一经生成即提交，后续分析只新增文件，不改写原始记录。
2. 使用 AI 工具辅助写代码、查资料、排障是**被鼓励**的，相关对话摘要记录在
   [`03-AI-Collaboration/`](03-AI-Collaboration/)。
3. 提交历史（`git log`）按天推进，每一次提交对应一次真实的动手进展。
4. 图表与结论由 `analysis/` 中的脚本从原始数据自动生成，**可复现**。

---

## 五、复现方式（Reproduction）

```bash
git clone <本仓库地址>
cd ICEC-2026-0147-linzetao
python -m pip install -r requirements.txt   # 依赖清单见各 analysis/ 目录
python 01-Field-Discovery/T07-PowerBank-Efficiency/analysis/analyze.py
```

---

**深圳城市职业学院（深圳技师学院）信息与通信学院 · 智能·创造者创新实验班（ICEC）**
*Curiosity × Action × Resilience × Integrity*
