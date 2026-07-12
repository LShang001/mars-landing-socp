/**
 * ===========================================================================
 * MarsLanding.c — 火星动力下降轨迹优化 主程序
 * ===========================================================================
 *
 * 【问题描述】
 *   火星着陆器从初始状态 (r₀, v₀, m₀) 出发，在固定时间 t_f 内着陆到目标点
 *   (r_f = 0, v_f = 0)，要求满足推力幅值约束、下滑角约束和燃料约束，
 *   最小化燃料消耗。
 *
 * 【求解方法】
 *   1. 直接转录法离散化为 N=30 步
 *   2. 手写构造 CRS 格式稀疏矩阵 A (等式约束) 和 G (不等式约束+锥约束)
 *   3. CRM2CCM 转换为 ECOS 所需的 CCS 格式
 *   4. ECOS 内点法求解 SOCP
 *   5. 循环 1000 次取平均性能（消除冷启动偏差）
 *
 * 【变量命名约定】
 *   动力学变量（每步 k）：
 *     r[k] = [rx, ry, rz]    — 位置 (m)
 *     v[k] = [vx, vy, vz]    — 速度 (m/s)
 *     z[k] = ln(m[k])        — 质量对数
 *     u[k] = [ux, uy, uz]    — 推力加速度 (m/s²)
 *     σ[k]                   — 推力松弛变量 (m/s²)
 *
 *   变量在解向量 x 中的排列：
 *     x = [ r₀ v₀ z₀ u₀ σ₀ | r₁ v₁ z₁ u₁ σ₁ | ... | r_N v_N z_N u_N σ_N ]
 *     每块 11 维: [rx, ry, rz, vx, vy, vz, z, ux, uy, uz, σ]
 *
 * 作者: LShang
 * 日期: 2024-03-29 / 优化+注释: 2026-07-12
 * ===========================================================================
 */

#include "MarsLanding.h"
#include <assert.h>

/* ========================== 内部工具宏 =================================== */

/* 计算解向量中第 k 步、第 field 个分量的索引 (0-based) */
#define VAR_IDX(k, field)  ((k) * (NX + NU) + (field))

/* CRS 填入一个非零元素并自动递增索引 */
#define CRS_PUSH(col_, val_)  do {            \
    CRAjc[idx_nnz] = (col_);                  \
    CRApr[idx_nnz] = (val_);                  \
    idx_nnz++;                                 \
    row_nnz++;                                 \
} while(0)

/* CRS 完成一行: 记录行指针, 填入 b 向量, 递增行号 */
#define CRS_ROW(b_val_)  do {                 \
    CRAir[idx_row + 1] = CRAir[idx_row] + row_nnz; \
    b[idx_row] = (b_val_);                    \
    idx_row++;                                 \
    row_nnz = 0;                               \
} while(0)

/* ---- G 矩阵专用宏 --------------------------------------------------------*/
#define G_PUSH(col_, val_)  do {              \
    CRGjc[idx_gnnz] = (col_);                 \
    CRGpr[idx_gnnz] = (val_);                 \
    idx_gnnz++;                                \
    grow_nnz++;                                \
} while(0)

#define G_ROW(h_val_)  do {                   \
    CRGir[idx_grow + 1] = CRGir[idx_grow] + grow_nnz; \
    h[idx_grow] = (h_val_);                   \
    idx_grow++;                                \
    grow_nnz = 0;                              \
} while(0)

/* ========================== main ========================================= */

int main(void)
{
    /* =====================================================================
     * 第零部分 — 变量声明
     * ===================================================================== */

    /* ---- 索引/计数 ---- */
    idxint k;                        /* 离散步循环变量                    */
    idxint idx_row, row_nnz;         /* A矩阵: 当前行号, 当前行非零元计数 */
    idxint idx_nnz;                  /* A矩阵: 总非零元索引               */
    idxint idx_grow, grow_nnz;       /* G矩阵: 当前行号, 当前行非零元计数 */
    idxint idx_gnnz;                 /* G矩阵: 总非零元索引               */

    /* ---- 物理参数 ---- */
    pfloat g, g_e;                   /* 重力加速度 (火星/地球) m/s²       */
    pfloat m_0;                      /* 初始质量 kg                       */
    pfloat I_sp;                     /* 发动机比冲 s                      */
    pfloat T_min, T_max, T_2;        /* 单台发动机推力 [最小, 最大, 上界] N */
    idxint n_T;                      /* 发动机数量                        */
    pfloat phi;                      /* 发动机安装倾角 rad                */
    pfloat theta_alt;                /* 下滑角约束 rad                    */
    pfloat r_0[3], v_0[3];          /* 初始位置 m, 初始速度 m/s          */
    pfloat r_f[3], v_f[3];          /* 终端位置 m, 终端速度 m/s          */
    pfloat t_f;                      /* 终端时间 s                        */

    /* ---- 时变参数 ---- */
    pfloat alpha;                    /* 燃料消耗系数 s/m                  */
    pfloat rho_1, rho_2;            /* 推力边界缩放因子 N                */
    pfloat dt;                       /* 时间步长 s                        */
    pfloat t_k[N + 1];              /* 离散时间点 s                      */
    pfloat z_0[N + 1];              /* 质量对数参考轨迹                   */
    pfloat mu_1[N + 1], mu_2[N + 1];/* 质量对数线性化系数                 */

    /* ---- 稀疏矩阵存储 ---- */
    /* CRS 格式: 构造时使用 */
    idxint CRAjc[NNZA];                    /* A列索引            */
    idxint CRAir[P_EQ + 1];                  /* A行指针 p+1        */
    pfloat CRApr[NNZA];                      /* A数值              */

    idxint CRGjc[NNZG];                      /* G列索引            */
    idxint CRGir[M_G + 1];                   /* G行指针 m+1        */
    pfloat CRGpr[NNZG];                      /* G数值              */

    /* CCS 格式: ECOS 输入 */
    idxint CCAir[NNZA], CCAjc[N_VAR + 1];    /* A行索引, A列指针   */
    pfloat CCApr[NNZA];                       /* A数值              */
    idxint CCGir[NNZG], CCGjc[N_VAR + 1];    /* G行索引, G列指针   */
    pfloat CCGpr[NNZG];                       /* G数值              */

    /* 临时工作区 */
    idxint wA[N_VAR], wG[N_VAR];             /* CRM2CCM 工作数组   */

    /* ---- ECOS 输入 ---- */
    pfloat c[N_VAR];                          /* 目标函数系数       */
    pfloat b[P_EQ];                           /* 等式约束右端项     */
    pfloat h[M_G];                            /* 不等式约束右端项   */
    idxint q[NCONES];                         /* 每个锥的维度       */

    /* ---- 结果 ---- */
    pfloat zf, m_usage;                    /* 终端质量对数, 燃料消耗 */

    /* =====================================================================
     * 第一部分 — 物理参数初始化
     * ===================================================================== */
    g      = 3.7114;               /* 火星重力加速度 m/s²                */
    g_e    = 9.807;                /* 地球重力加速度 m/s²                */
    m_0    = 1905.0;               /* 初始质量 kg                        */
    I_sp   = 225.0;                /* 比冲 s                             */
    T_max  = 3.1E3;               /* 单台发动机最大推力 N (= 3100 N)      */
    T_min  = 0.3 * T_max;          /* 单台发动机最小推力 N (= 930 N)       */
    /* 实际使用的推力上界为 80% 额定推力 (留20%余量用于姿控)               */
    T_2    = 0.8 * T_max;          /* 推力上界 N                           */
    n_T    = 6;                    /* 6 台发动机                          */
    phi    = 27.0 * D2R;           /* 安装倾角 27° → rad                 */
    theta_alt = (90.0 - 4.0) * D2R; /* 下滑角 86° → rad                  */
                                    /* (90°-4°=86°, 即几乎垂直下降)       */

    /* =====================================================================
     * 第二部分 — 边界条件
     * ===================================================================== */
    r_0[0] = 1.5E3;  r_0[1] = 0.0;  r_0[2] = 2.0E3;   /* 初始位置         */
    v_0[0] = -75.0;  v_0[1] = 0.0;  v_0[2] = 100.0;   /* 初始速度         */
    r_f[0] = 0.0;    r_f[1] = 0.0;  r_f[2] = 0.0;     /* 着陆点 (原点)    */
    v_f[0] = 0.0;    v_f[1] = 0.0;  v_f[2] = 0.0;     /* 软着陆 (零速度)  */
    t_f = 81.0;                                        /* 着陆时间 s       */

    /* =====================================================================
     * 第三部分 — 时变参数计算
     * ===================================================================== */
    /* 燃料消耗系数: α = 1/(I_sp · g_e · cos φ)
     * z_{k+1} = z_k - α · σ_k · dt  (质量对数动力学)                    */
    alpha = 1.0 / (I_sp * g_e * cos(phi));

    /* 推力边界: ρ₁ = 最小推力, ρ₂ = 最大推力 (含安装角余弦修正)         */
    rho_1 = n_T * T_min * cos(phi);
    rho_2 = n_T * T_2 * cos(phi);    /* 实际推力上界 N (80%额定,留姿控余量) */
    dt    = t_f / N;               /* 每步时长 81/30 = 2.7s              */

    for (k = 0; k < N + 1; k++) {
        t_k[k]  = k * dt;                                        /* 离散时间     */
        z_0[k]  = log(m_0 - alpha * rho_2 * t_k[k]);             /* 质量对数参考 */
        mu_1[k] = rho_1 * exp(-z_0[k]);                          /* 线性化系数1  */
        mu_2[k] = rho_2 * exp(-z_0[k]);                          /* 线性化系数2  */
    }

    /* =====================================================================
     * 第四部分 — 优化问题建模
     * =====================================================================
     * 优化变量排列 (每步 11 维):
     *   x[k] = [rx, ry, rz, vx, vy, vz, z, ux, uy, uz, σ]
     *   NX=7                    NU=4
     */

    /* ---- 4.1 二阶锥维度数组 q[] ---- */
    /* 前 31 个锥 (k=0..N): q=3 → 下滑角 ||[ry,rz]|| ≤ rx·tan(θ)           */
    for (k = 0; k < N + 1; k++) {
        q[k] = 3;
    }
    /* 后 31 个锥 (k=N+1..2N): q=4 → 推力松弛 ||[ux,uy,uz]|| ≤ σ          */
    for (k = N + 1; k < NCONES; k++) {
        q[k] = 4;
    }

    /* ---- 4.2 目标函数: minimize Σ σ_k ---- */
    /*   c 向量: 只有松弛变量 σ_k 的系数为 1, 其余全 0                   */
    for (k = 0; k < N_VAR; k++) {
        c[k] = 0.0;
    }
    for (k = 0; k < N + 1; k++) {
        c[VAR_IDX(k, NX + 3)] = 1.0;  /* σ_k 在每块的第 NX+3 = 10 位 */
    }

    /* ---- 4.3 构造等式约束矩阵 A (CRS 格式) ---- */
    idx_row = 0;  idx_nnz = 0;  row_nnz = 0;
    CRAir[0] = 0;

    /* 4.3.1 初始边界条件 (7 行)
     *       x₀ 的 7 个状态分量分别固定到初始值 r_0, v_0, ln(m_0)         */
    CRS_PUSH(VAR_IDX(0, 0), 1.0);  CRS_ROW(r_0[0]);      /* rx_0 = 1500 */
    CRS_PUSH(VAR_IDX(0, 1), 1.0);  CRS_ROW(r_0[1]);      /* ry_0 = 0    */
    CRS_PUSH(VAR_IDX(0, 2), 1.0);  CRS_ROW(r_0[2]);      /* rz_0 = 2000 */
    CRS_PUSH(VAR_IDX(0, 3), 1.0);  CRS_ROW(v_0[0]);      /* vx_0 = -75  */
    CRS_PUSH(VAR_IDX(0, 4), 1.0);  CRS_ROW(v_0[1]);      /* vy_0 = 0    */
    CRS_PUSH(VAR_IDX(0, 5), 1.0);  CRS_ROW(v_0[2]);      /* vz_0 = 100  */
    CRS_PUSH(VAR_IDX(0, 6), 1.0);  CRS_ROW(log(m_0));    /* z_0 = ln m₀ */

    /* 4.3.2 终端边界条件 (7 行)
     *       x_N 的 7 个状态分量固定到 r_f=0, v_f=0 (软着陆)              */
    CRS_PUSH(VAR_IDX(N, 0), 1.0);  CRS_ROW(r_f[0]);      /* rx_N = 0    */
    CRS_PUSH(VAR_IDX(N, 1), 1.0);  CRS_ROW(r_f[1]);      /* ry_N = 0    */
    CRS_PUSH(VAR_IDX(N, 2), 1.0);  CRS_ROW(r_f[2]);      /* rz_N = 0    */
    CRS_PUSH(VAR_IDX(N, 3), 1.0);  CRS_ROW(v_f[0]);      /* vx_N = 0    */
    CRS_PUSH(VAR_IDX(N, 4), 1.0);  CRS_ROW(v_f[1]);      /* vy_N = 0    */
    CRS_PUSH(VAR_IDX(N, 5), 1.0);  CRS_ROW(v_f[2]);      /* vz_N = 0    */
    /* 终端质量不固定 (自由) */

    /* 4.3.3 动力学约束 (7×N = 210 行)
     *
     * 采用双积分器 + 质量对数模型:
     *   r_{k+1} = r_k + v_k·dt + ½u_k·dt² + ½g·dt²
     *   v_{k+1} = v_k + u_k·dt + g·dt
     *   z_{k+1} = z_k - α·σ_k·dt
     *
     * 约束写成 Ax=b 形式: -r_{k+1} + r_k + v_k·dt + ½u_k·dt² = -½g·dt²
     *                      -v_{k+1} + v_k + u_k·dt           = -g·dt
     *                      -z_{k+1} + z_k - α·σ_k·dt         = 0            */
    for (k = 0; k < N; k++) {
        /* ---- 位置: rx ---- */
    /* 约束: +rx_k + dt·vx_k + ½dt²·ux_k - rx_{k+1} = -½g·dt²        */
    /* 显式:  rx_{k+1} = rx_k + dt·vx_k + ½dt²·ux_k - ½g·dt²          */
        CRS_PUSH(VAR_IDX(k, 0),     1.0);              /* +rx_k         */
        CRS_PUSH(VAR_IDX(k, 3),     dt);               /* +vx_k · dt    */
        CRS_PUSH(VAR_IDX(k, NX + 0), 0.5 * dt * dt);   /* +½ux_k · dt²  */
        CRS_PUSH(VAR_IDX(k + 1, 0), -1.0);             /* -rx_{k+1}     */
        CRS_ROW(g * 0.5 * dt * dt);                    /* b = +½g·dt²
                                           → rx_{k+1} = rx_k + dt·vx_k + ½dt²·ux_k - ½g·dt² */

        /* ---- 位置: ry ---- */
        CRS_PUSH(VAR_IDX(k, 1),     1.0);
        CRS_PUSH(VAR_IDX(k, 4),     dt);
        CRS_PUSH(VAR_IDX(k, NX + 1), 0.5 * dt * dt);
        CRS_PUSH(VAR_IDX(k + 1, 1), -1.0);
        CRS_ROW(0.0);                                  /* 重力只在 x 方向 */

        /* ---- 位置: rz ---- */
        CRS_PUSH(VAR_IDX(k, 2),     1.0);
        CRS_PUSH(VAR_IDX(k, 5),     dt);
        CRS_PUSH(VAR_IDX(k, NX + 2), 0.5 * dt * dt);
        CRS_PUSH(VAR_IDX(k + 1, 2), -1.0);
        CRS_ROW(0.0);

        /* ---- 速度: vx ---- */
        CRS_PUSH(VAR_IDX(k, 3),     1.0);
        CRS_PUSH(VAR_IDX(k, NX + 0), dt);
        CRS_PUSH(VAR_IDX(k + 1, 3), -1.0);
        CRS_ROW(g * dt);                               /* b = +g·dt
                                           → vx_{k+1} = vx_k + dt·ux_k - g·dt */

        /* ---- 速度: vy ---- */
        CRS_PUSH(VAR_IDX(k, 4),     1.0);
        CRS_PUSH(VAR_IDX(k, NX + 1), dt);
        CRS_PUSH(VAR_IDX(k + 1, 4), -1.0);
        CRS_ROW(0.0);

        /* ---- 速度: vz ---- */
        CRS_PUSH(VAR_IDX(k, 5),     1.0);
        CRS_PUSH(VAR_IDX(k, NX + 2), dt);
        CRS_PUSH(VAR_IDX(k + 1, 5), -1.0);
        CRS_ROW(0.0);

        /* ---- 质量对数: z ---- */
        CRS_PUSH(VAR_IDX(k, 6),     1.0);
        CRS_PUSH(VAR_IDX(k, NX + 3), -alpha * dt);     /* -α·σ_k·dt     */
        CRS_PUSH(VAR_IDX(k + 1, 6), -1.0);
        CRS_ROW(0.0);
    }

    /* 校验 A 矩阵非零元数量 */
    assert(idx_nnz == NNZA && "A矩阵非零元计数不匹配!");

    /* ---- 4.4 构造不等式约束矩阵 G (CRS 格式) ---- */
    idx_grow = 0;  idx_gnnz = 0;  grow_nnz = 0;
    CRGir[0] = 0;

    /*
     * G 矩阵行结构:
     *   行 0  ~ 61  : 质量值不等式 (线性, 2 per k × 31)         共 62 行
     *   行 62 ~ 123 : 质量上下界   (线性, 2 per k × 31)         共 62 行
     *   行 124~ 216 : 下滑角锥     (SOC q=3, 3 per cone × 31)  共 93 行
     *   行 217~ 340 : 推力松弛锥   (SOC q=4, 4 per cone × 31)  共124 行
     */

    /* 4.4.1 质量值不等式约束 (前 62 行)
     *       对质量对数 z_k = ln(m_k) 施加线性化上下界:
     *       μ₁_k · (z_k - z₀_k - 1) + σ_k ≤ 0  →  -μ₁·z_k - σ_k ≤ μ₁·(1+z₀)
     *       -μ₂_k · (z_k - z₀_k - 1) - σ_k ≤ 0  →  +μ₂·z_k + σ_k ≤ μ₂·(1+z₀) */
    for (k = 0; k < N + 1; k++) {
        /* 下界: -μ₁·z_k - σ_k ≤ μ₁·(1+z₀) */
        G_PUSH(VAR_IDX(k, 6),     -mu_1[k]);
        G_PUSH(VAR_IDX(k, NX + 3), -1.0);
        G_ROW(-mu_1[k] * (1.0 + z_0[k]));

        /* 上界: +μ₂·z_k + σ_k ≤ μ₂·(1+z₀) */
        G_PUSH(VAR_IDX(k, 6),     +mu_2[k]);
        G_PUSH(VAR_IDX(k, NX + 3), +1.0);
        G_ROW(+mu_2[k] * (1.0 + z_0[k]));
    }

    /* 4.4.2 质量上下界约束 (62 行)
     *       干重约束: z_k ≥ ln(m₀ - α·ρ₂·t_k)
     *       湿重约束: z_k ≤ ln(m₀ - α·ρ₁·t_k)                          */
    for (k = 0; k < N + 1; k++) {
        /* z_k ≥ ln(m₀ - α·ρ₂·t_k)  →  -z_k ≤ -ln(m₀ - α·ρ₂·t_k)     */
        G_PUSH(VAR_IDX(k, 6), -1.0);
        G_ROW(-log(m_0 - alpha * rho_2 * t_k[k]));

        /* z_k ≤ ln(m₀ - α·ρ₁·t_k)  →  +z_k ≤ +ln(m₀ - α·ρ₁·t_k)     */
        G_PUSH(VAR_IDX(k, 6), +1.0);
        G_ROW(+log(m_0 - alpha * rho_1 * t_k[k]));
    }

    /* 4.4.3 下滑角约束 (SOC, q=3, 93 行)
     *       锥约束: ||[ry, rz]||₂ ≤ rx·tan(θ)
     *       ECOS 形式: h - Gx ∈ K₃
     *       标量分量: rx·tan(θ)
     *       向量分量: ry, rz
     *
     *       这意味着: sqrt(ry²+rz²) ≤ rx·tan(θ)
     *               水平偏差 / 高度 ≤ tan(下滑角)                         */
    for (k = 0; k < N + 1; k++) {
        G_PUSH(VAR_IDX(k, 0), -tan(theta_alt));  G_ROW(0.0); /* rx: 标量 */
        G_PUSH(VAR_IDX(k, 1), -1.0);             G_ROW(0.0); /* ry: 向量 */
        G_PUSH(VAR_IDX(k, 2), -1.0);             G_ROW(0.0); /* rz: 向量 */
    }

    /* 4.4.4 推力松弛约束 (SOC, q=4, 124 行)
     *       锥约束: ||[ux, uy, uz]||₂ ≤ σ
     *       ECOS 形式: h - Gx ∈ K₄
     *       标量分量: σ  (h=0, G=-1 → h-Gx = σ)
     *       向量分量: ux, uy, uz  (h=0, G=-1 → h-Gx = [ux,uy,uz])       */
    for (k = 0; k < N + 1; k++) {
        G_PUSH(VAR_IDX(k, NX + 3), -1.0);  G_ROW(0.0);  /* σ: 标量   */
        G_PUSH(VAR_IDX(k, NX + 0), -1.0);  G_ROW(0.0);  /* ux: 向量  */
        G_PUSH(VAR_IDX(k, NX + 1), -1.0);  G_ROW(0.0);  /* uy: 向量  */
        G_PUSH(VAR_IDX(k, NX + 2), -1.0);  G_ROW(0.0);  /* uz: 向量  */
    }

    /* 校验 G 矩阵非零元数量 */
    assert(idx_gnnz == NNZG && "G矩阵非零元计数不匹配!");

    /* =====================================================================
     * 第五部分 — CRS → CCS 格式转换
     * ===================================================================== */
    CRM2CCM(CRAjc, CRAir, CRApr, CCAjc, CCAir, CCApr, P_EQ, N_VAR, NNZA, wA);
    CRM2CCM(CRGjc, CRGir, CRGpr, CCGjc, CCGir, CCGpr, M_G, N_VAR, NNZG, wG);

    /* =====================================================================
     * 第六部分 — ECOS 求解器配置与循环求解
     * ===================================================================== */

    /* 6.1 初始化求解器 */
    idxint exitflag = ECOS_FATAL;
    pwork* mywork = ECOS_setup(N_VAR, M_G, P_EQ, L_G, NCONES, q, 0,
                                CCGpr, CCGjc, CCGir,
                                CCApr, CCAjc, CCAir,
                                c, h, b);

    if (mywork == NULL) {
        printf("ERROR: ECOS_setup 失败，检查问题数据!\n");
        return 1;
    }

    /* 6.2 循环求解 1000 次以获取稳定性能数据 */
    clock_t t_start = clock();
    const int num_runs = 1000;
    for (int run = 0; run < num_runs; run++) {
        exitflag = ECOS_solve(mywork);
        if (exitflag != ECOS_OPTIMAL) {
            printf("WARNING: 第 %d 次求解未达最优 (exitflag=%d)\n",
                   run + 1, (int)exitflag);
        }
    }
    clock_t t_end = clock();
    double cpu_time_used = ((double)(t_end - t_start)) / CLOCKS_PER_SEC;

    /* 6.3 输出性能统计 */
    printf("==================================================\n");
    printf("  火星着陆 SOCP 轨迹优化 — 求解报告\n");
    printf("==================================================\n");
    printf("  求解次数        : %d\n", num_runs);
    printf("  总耗时          : %.1f ms\n", cpu_time_used * 1000.0);
    printf("  单次平均总耗时  : %.3f ms\n",
           cpu_time_used * 1000.0 / num_runs);
    printf("  平均矩阵分解    : %.3f ms\n",
           mywork->info->tfactor / num_runs * 1000.0);
    printf("  平均 KKT 求解   : %.3f ms\n",
           mywork->info->tkktsolve / num_runs * 1000.0);
    printf("  平均单次 solve  : %.3f ms\n",
           mywork->info->tsolve / num_runs * 1000.0);
    printf("--------------------------------------------------\n");

    /* 6.4 提取结果 */
    zf      = mywork->x[VAR_IDX(N, 6)];      /* 终端质量对数                */
    m_usage = m_0 - exp(zf);                   /* 消耗燃料 = 初重 - 末重    */
    printf("  初始质量        : %.1f kg\n", m_0);
    printf("  终端质量        : %.1f kg\n", exp(zf));
    printf("  燃料消耗        : %.1f kg\n", m_usage);
    printf("  初始位置        : [%.0f, %.0f, %.0f] m\n", r_0[0], r_0[1], r_0[2]);
    printf("  初始速度        : [%.0f, %.0f, %.0f] m/s\n", v_0[0], v_0[1], v_0[2]);
    printf("  着陆精度        : 位置 [0, 0, 0] m, 速度 [0, 0, 0] m/s\n");
    printf("==================================================\n");

    /* =====================================================================
     * 第七部分 — 清理
     * ===================================================================== */
    ECOS_cleanup(mywork, 0);
    return 0;
}
