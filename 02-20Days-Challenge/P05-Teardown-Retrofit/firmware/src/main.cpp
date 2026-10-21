/**
 * ICEC 项目五 · 第④项 改造固件
 * 旧充电宝 —— 电池健康度（SOH）监测模块
 *
 * 硬件：ESP32-C3 + INA219（I2C）
 * 采样：10 Hz 母线电压 + 分流电压 → 电流 / 功率 / 安时 / 瓦时
 * 估算：内阻（负载阶跃法）、容量保持率（库仑计法）→ 两个 SOH 指标
 * 输出：CSV 行（115200），供 host_logger.py 落盘到 process_logs/
 *
 * ── 为什么用分流电压自己算电流，而不用 INA219 的 CURRENT 寄存器 ──
 * CURRENT 寄存器依赖 CALIBRATION 寄存器的标定值，一旦采样电阻与标定不匹配，
 * 读数会整体偏移且不易察觉。直接用 I_shunt = V_shunt / R_SHUNT 计算，
 * 换算链条最短、可追溯，出问题时能一眼看出是哪一步错了。
 *
 * ── 量程说明（重要）──
 * INA219 的 PGA 档位最大 ±320 mV。本设计用 R_SHUNT = 0.05 Ω，
 *   量程上限 = 0.32 V / 0.05 Ω = 6.4 A
 *   分辨率   = 10 µV / 0.05 Ω = 0.2 mA
 * 若沿用常见模块自带的 0.1 Ω 采样电阻，量程只有 3.2 A，
 * 30 W 快充时电芯侧电流可能超过 3.2 A 而削顶，必须换 0.05 Ω。
 */

#include <Arduino.h>
#include <Wire.h>

// ============================================================ 引脚与器件
#define PIN_SDA        8        // ESP32-C3 默认 I2C SDA；按实际接线改
#define PIN_SCL        9        // ESP32-C3 默认 I2C SCL；按实际接线改
#define INA219_ADDR    0x40     // A0/A1 都接 GND 时为 0x40
#define PIN_LED        2        // 板载指示灯，做心跳

// ============================================================ 标定参数
// TODO(林泽涛)：把 R_SHUNT 改成你实际焊上去的那颗电阻的阻值
const float  R_SHUNT        = 0.05f;   // Ω
const float  V_BUS_LSB      = 0.004f;  // INA219 母线电压 LSB = 4 mV
const float  V_SHUNT_LSB    = 10e-6f;  // INA219 分流电压 LSB = 10 µV

// 截止判定与量程保护
const float  I_DEADBAND     = 0.005f;  // A，低于此视为 0（底噪）
const float  I_CLIP_WARN    = 3.00f;   // A，接近量程时告警
const uint32_t SAMPLE_MS    = 100;     // 10 Hz
const uint32_t PRINT_EVERY  = 5;       // 每 5 个采样点（0.5 s）打印一行

// 内阻估算
const float  STEP_MIN_A     = 0.30f;   // 判定为「负载阶跃」的最小电流变化
const uint8_t RING          = 5;       // 平滑窗口
const uint8_t R_MED_N       = 9;       // 内阻中值滤波长度
// TODO(林泽涛)：拆机后测一只健康电芯的内阻填进来，SOH_R 才有意义
const float  R_NOMINAL_MOHM = 60.0f;   // mΩ，新电池参考内阻

// 容量
const float  CAP_NOMINAL_AH = 10.0f;   // 标称 10000 mAh
// TODO：确认 CP13 是 1S 还是 2S；2S 时电芯容量要按串并联折算

// ============================================================ INA219 寄存器
static const uint8_t REG_CONFIG = 0x00;
static const uint8_t REG_SHUNT  = 0x01;
static const uint8_t REG_BUS    = 0x02;

// BRNG=0(16V) PG=11(±320mV) BADC=0011(12bit) SADC=0011(12bit) MODE=111(连续)
static const uint16_t CFG = 0x199F;

// ============================================================ I2C 底层
static bool ina_write16(uint8_t reg, uint16_t val) {
  Wire.beginTransmission(INA219_ADDR);
  Wire.write(reg);
  Wire.write((uint8_t)(val >> 8));
  Wire.write((uint8_t)(val & 0xFF));
  return Wire.endTransmission() == 0;
}

/**
 * 读 16 位寄存器。
 * 注意：不能写成 (Wire.read() << 8) | Wire.read()，
 * 因为 | 的两个操作数求值顺序在 C++ 里未定义，会偶发高低字节颠倒。
 * 这里先读入两个具名变量，顺序是确定的。
 */
static bool ina_read16(uint8_t reg, uint16_t *out) {
  Wire.beginTransmission(INA219_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission() != 0) return false;
  if (Wire.requestFrom((uint8_t)INA219_ADDR, (uint8_t)2) != 2) return false;
  uint8_t hi = Wire.read();
  uint8_t lo = Wire.read();
  *out = ((uint16_t)hi << 8) | (uint16_t)lo;
  return true;
}

// ============================================================ 数据状态
struct Reading {
  float v_bus;     // V
  float i_amp;     // A（正=放电/流出，负=充电/流入，取决于接线方向）
  float p_watt;    // W
};

static Reading g_last = {0, 0, 0};

// 库仑计 / 瓦时计
static double g_ah_out = 0.0;   // 累计放出
static double g_ah_in  = 0.0;   // 累计充入
static double g_wh_out = 0.0;
static double g_wh_in  = 0.0;

// 平滑窗口
static float g_vRing[RING];
static float g_iRing[RING];
static uint8_t g_ringIdx = 0;
static uint8_t g_ringCnt = 0;

// 内阻样本
static float g_rSamples[R_MED_N];
static uint8_t g_rCnt = 0;
static uint8_t g_rIdx = 0;

// 上一次用于阶跃判定的窗口均值
static bool  g_havePrev = false;
static float g_prevV = 0, g_prevI = 0;

// 容量法 SOH：记录本次放电起始点
static bool  g_discharging = false;
static double g_ahDip = 0.0;     // 本次放电累计
static float g_ahMeasured = 0.0f;

// ---------------------------------------------------------- 工具
static float ringMeanV() {
  if (g_ringCnt == 0) return 0;
  float s = 0;
  for (uint8_t k = 0; k < g_ringCnt; k++) s += g_vRing[k];
  return s / g_ringCnt;
}
static float ringMeanI() {
  if (g_ringCnt == 0) return 0;
  float s = 0;
  for (uint8_t k = 0; k < g_ringCnt; k++) s += g_iRing[k];
  return s / g_ringCnt;
}

static float medianR() {
  if (g_rCnt == 0) return NAN;
  float tmp[R_MED_N];
  uint8_t n = g_rCnt;
  for (uint8_t k = 0; k < n; k++) tmp[k] = g_rSamples[k];
  // 插入排序，n ≤ 9
  for (uint8_t a = 1; a < n; a++) {
    float key = tmp[a];
    int8_t b = (int8_t)a - 1;
    while (b >= 0 && tmp[b] > key) { tmp[b + 1] = tmp[b]; b--; }
    tmp[b + 1] = key;
  }
  return tmp[n / 2];
}

static void pushR(float r_mohm) {
  // 剔除明显离谱的样本（接触抖动、量程削顶会产生异常值）
  if (r_mohm < 5.0f || r_mohm > 2000.0f) return;
  g_rSamples[g_rIdx] = r_mohm;
  g_rIdx = (uint8_t)((g_rIdx + 1) % R_MED_N);
  if (g_rCnt < R_MED_N) g_rCnt++;
}

static float sohByR() {
  float r = medianR();
  if (isnan(r) || r <= 0) return NAN;
  float soh = R_NOMINAL_MOHM / r * 100.0f;
  if (soh > 120.0f) soh = 120.0f;
  if (soh < 0.0f)   soh = 0.0f;
  return soh;
}

static float sohByCapacity() {
  if (g_ahMeasured <= 0) return NAN;
  float soh = g_ahMeasured / CAP_NOMINAL_AH * 100.0f;
  if (soh > 120.0f) soh = 120.0f;
  return soh;
}

// ============================================================ setup
void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(PIN_LED, OUTPUT);

  Serial.println();
  Serial.println(F("# ICEC P05 SOH Monitor  (ESP32-C3 + INA219)"));
  Serial.printf("# R_SHUNT=%.3f ohm  I_range=+-%.2f A  I_res=%.2f mA\n",
                R_SHUNT, 0.32f / R_SHUNT, V_SHUNT_LSB / R_SHUNT * 1000.0f);

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);

  if (!ina_write16(REG_CONFIG, CFG)) {
    Serial.println(F("# ERROR: INA219 无应答，检查 VCC/GND/SDA/SCL 与 A0/A1 地址"));
    // 仍然继续跑，方便现场用串口看到状态而不是静默失败
  } else {
    uint16_t rb = 0;
    ina_read16(REG_CONFIG, &rb);
    Serial.printf("# INA219 config write=0x%04X read=0x%04X %s\n",
                  CFG, rb, (rb == CFG) ? "OK" : "(不一致!)");
  }

  Serial.println(F("t_ms,V_bus,I,P,Ah_out,Ah_in,Wh_out,Wh_in,R_mohm,SOH_R,SOH_C,flag"));
  for (uint8_t k = 0; k < RING; k++) { g_vRing[k] = 0; g_iRing[k] = 0; }
}

// ============================================================ loop
void loop() {
  static uint32_t tPrev = 0;
  static uint32_t nSample = 0;

  uint32_t tNow = millis();
  if (tNow - tPrev < SAMPLE_MS) return;

  float dt = (tPrev == 0) ? 0.0f : (float)(tNow - tPrev) / 1000.0f;
  tPrev = tNow;

  // ---- 读 INA219
  uint16_t rawBus = 0, rawShunt = 0;
  bool okBus   = ina_read16(REG_BUS, &rawBus);
  bool okShunt = ina_read16(REG_SHUNT, &rawShunt);
  if (!okBus || !okShunt) {
    Serial.println(F("# WARN: I2C 读失败"));
    return;
  }

  // 母线电压：低 3 位是标志位，必须右移
  float vBus = (float)(rawBus >> 3) * V_BUS_LSB;
  // 分流电压：有符号 16 位
  int16_t sShunt = (int16_t)rawShunt;
  float vShunt = (float)sShunt * V_SHUNT_LSB;
  float iAmp = vShunt / R_SHUNT;

  if (fabsf(iAmp) < I_DEADBAND) iAmp = 0.0f;
  float pW = vBus * iAmp;

  g_last.v_bus = vBus;
  g_last.i_amp = iAmp;
  g_last.p_watt = pW;

  // ---- 库仑计 / 瓦时计
  if (dt > 0.0f && dt < 1.0f) {
    if (iAmp > 0) {
      g_ah_out += (double)iAmp * dt / 3600.0;
      g_wh_out += (double)pW   * dt / 3600.0;
      g_discharging = true;
      g_ahDip += (double)iAmp * dt / 3600.0;
    } else if (iAmp < 0) {
      double in = -(double)iAmp;
      g_ah_in  += in * dt / 3600.0;
      g_wh_in  += in * vBus * dt / 3600.0;
      g_discharging = false;
    }
  }

  // ---- 平滑窗口
  g_vRing[g_ringIdx] = vBus;
  g_iRing[g_ringIdx] = iAmp;
  g_ringIdx = (uint8_t)((g_ringIdx + 1) % RING);
  if (g_ringCnt < RING) g_ringCnt++;

  float mV = ringMeanV();
  float mI = ringMeanI();

  // ---- 内阻：负载阶跃法 R = |ΔV| / |ΔI|
  if (g_havePrev) {
    float dI = mI - g_prevI;
    if (fabsf(dI) >= STEP_MIN_A) {
      float dV = mV - g_prevV;
      if (fabsf(dV) > 0.002f) {
        float rMohm = fabsf(dV) / fabsf(dI) * 1000.0f;
        pushR(rMohm);
      }
    }
  }
  g_prevV = mV;
  g_prevI = mI;
  g_havePrev = true;

  // ---- 放电结束判定：电流从 >0.3A 掉到接近 0，且此前有累计
  static bool wasHigh = false;
  if (mI > 0.30f) wasHigh = true;
  if (wasHigh && mI < 0.05f && g_discharging) {
    if (g_ahDip > 0.5) {               // 至少放过 0.5 Ah 才认为是有效一次放电
      g_ahMeasured = (float)g_ahDip;
    }
    g_ahDip = 0.0;
    wasHigh = false;
  }

  // ---- 输出
  if (++nSample % PRINT_EVERY == 0) {
    char flag[8] = "";
    if (fabsf(iAmp) >= I_CLIP_WARN) {
      snprintf(flag, sizeof(flag), "CLIP?");
    }

    char rBuf[12], srBuf[12], scBuf[12];
    float rm = medianR();
    float sr = sohByR();
    float sc = sohByCapacity();
    if (isnan(rm)) snprintf(rBuf, sizeof(rBuf), "nan");  else snprintf(rBuf, sizeof(rBuf), "%.1f", rm);
    if (isnan(sr)) snprintf(srBuf, sizeof(srBuf), "nan"); else snprintf(srBuf, sizeof(srBuf), "%.1f", sr);
    if (isnan(sc)) snprintf(scBuf, sizeof(scBuf), "nan"); else snprintf(scBuf, sizeof(scBuf), "%.1f", sc);

    Serial.printf("%lu,%.3f,%.4f,%.3f,%.4f,%.4f,%.4f,%.4f,%s,%s,%s,%s\n",
                  (unsigned long)tNow, vBus, iAmp, pW,
                  g_ah_out, g_ah_in, g_wh_out, g_wh_in,
                  rBuf, srBuf, scBuf, flag);
  }

  // 心跳：按电流方向亮灭，方便现场判断接线方向对不对
  digitalWrite(PIN_LED, (iAmp > 0) ? HIGH : LOW);
}
