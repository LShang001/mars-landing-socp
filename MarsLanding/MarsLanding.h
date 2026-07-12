/**
 * ===========================================================================
 * MarsLanding.h — 火星着陆轨迹优化 参数/维度定义头文件
 * ===========================================================================
 *
 * 【项目概述】
 *   使用 ECOS (Embedded Conic Solver) 二阶锥规划求解器，
 *   求解火星动力下降段最小燃料轨迹优化问题。
 *   离散化采用直接转录法 (Direct Transcription)，固定 N 个时间步长。
 *
 * 【状态变量】 每离散点 7 维: rx, ry, rz, vx, vy, vz, z(=ln m)
 * 【控制变量】 每离散点 4 维: ux, uy, uz (推力加速度), σ (松弛变量)
 * 【优化变量总数】 (NX+NU) × (N+1) = 11 × 31 = 341
 *
 * 【坐标系】
 *   +x : 竖直向上（从火星表面指向天空，与重力方向相反）
 *   +y, +z : 水平面内正交方向
 *   重力加速度 g = 3.7114 m/s²，沿 -x 方向（即 b 向量中以正值加入
 *   动力学方程，因为 Ax = b 形式中 b 移到等号右边）
 *
 * 【参考文献】
 *   Acikmese & Ploen (2007): "Convex Programming Approach to
 *   Powered Descent Guidance for Mars Landing"
 *
 * 作者: LShang
 * 日期: 2024-03-29 / 优化: 2026-07-12
 * ===========================================================================
 */

#ifndef MARSLANDING_H
#define MARSLANDING_H

#include <stdio.h>
#include "ecos.h"

/* ========================== 数学常数 ===================================== */
#define PI  3.14159265358979323846   /* 圆周率                          */
#define D2R (PI / 180.0)             /* 角度 → 弧度 转换因子            */

/* ========================== 问题规模参数 ================================= */

#define N   30    /* 离散点数（时间网格数），N+1=31 个节点               */
#define NX  7     /* 状态变量维度: rx, ry, rz, vx, vy, vz, z(=ln m)    */
#define NU  4     /* 控制变量维度: ux, uy, uz(推力), σ(松弛变量)       */

/* ---- 矩阵非零元统计（用于预分配内存）----------------------------------- */

#define NNZ_BOUND  (NX + NX - 1)     /* 边界条件: 13 非零元             */
#define NNZ_DYN    (10 + 7 + 7)      /* 每步动力学: 24 非零元           */
                                     /*   位置更新: 4+4+4 = 12           */
                                     /*   速度更新: 3+3+3 = 9            */
                                     /*   质量更新: 3                   */

#define NNZ_TNORM  (2 * 2)           /* 质量值不等式: 每步 4            */
#define NNZ_MASS   (2 * 1)           /* 质量上下界: 每步 2              */
#define NNZ_TRELAX  4                /* 推力松弛(SOC): 每步 4           */
#define NNZ_SLOPE   3                /* 下滑角(SOC): 每步 3             */

/* ---- 优化问题维度（由上述参数推导）-------------------------------------- */

#define N_VAR  ((NX + NU) * (N + 1))             /* 341: 优化变量总数     */
#define P_EQ   ((NX + NX - 1) + NX * N)           /* 223: 等式约束数       */
                                                /*   边界条件 13         */
                                                /*   动力学约束 7×30=210 */
#define L_G    ((N + 1) * (2 + 2))                /* 124: 线性不等式约束数 */
                                                /*   质量值不等式（线性化推力边界）2×31   */
                                                /*   质量上下界（干/湿重边界）2×31         */
#define NCONES ((N + 1) * (1 + 1))                /* 62: 二阶锥总数        */
                                                /*   下滑角锥 31         */
                                                /*   推力松弛锥 31       */
#define M_G    (L_G + (N + 1) * 4 + (N + 1) * 3) /* 341: 不等式约束总行数 */
                                                /*   线性 124            */
                                                /*   SOC1(推力,q=4) 124  */
                                                /*   SOC2(下滑,q=3) 93   */

#define NNZA  (NNZ_BOUND + NNZ_DYN * N)           /*  733: A矩阵非零元    */
#define NNZG  ((NNZ_TNORM + NNZ_MASS + NNZ_TRELAX + NNZ_SLOPE) * (N + 1))
                                                 /*  403: G矩阵非零元    */

/* ---- 二阶锥维度数组 q[ncones] ------------------------------------------- */
/* 前 N+1 个锥: q=3 → 下滑角约束   ||[ry,rz]|| ≤ rx·tan(θ)                */
/* 后 N+1 个锥: q=4 → 推力松弛约束 ||[ux,uy,uz]|| ≤ σ                     */

/* ========================== 函数声明 ===================================== */

/**
 * crm_to_ccm — 稀疏矩阵 CRS → CCS 格式转换
 *
 * 将行压缩存储 (Compressed Row Storage) 转为列压缩存储 (Compressed Column
 * Storage)。ECOS 求解器要求输入矩阵为 CCS 格式。
 *
 * @param CRMjc    输入: CRS 列索引数组  (大小 nnz)
 * @param CRMir    输入: CRS 行指针数组  (大小 m+1)
 * @param CRMpr    输入: CRS 数值数组    (大小 nnz)
 * @param CCMjc    输出: CCS 列指针数组  (大小 n+1)
 * @param CCMir    输出: CCS 行索引数组  (大小 nnz)
 * @param CCMpr    输出: CCS 数值数组    (大小 nnz)
 * @param m        矩阵行数
 * @param n        矩阵列数
 * @param nnz      非零元素总数
 * @param w        临时工作数组 (大小 n)
 */
void crm_to_ccm(idxint CRMjc[], idxint CRMir[], pfloat CRMpr[],
             idxint CCMjc[], idxint CCMir[], pfloat CCMpr[],
             idxint m, idxint n, idxint nnz, idxint w[]);

#endif /* MARSLANDING_H */
