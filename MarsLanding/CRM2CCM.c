/**
 * ===========================================================================
 * CRM2CCM.c — 稀疏矩阵格式转换: CRS (行压缩) → CCS (列压缩)
 * ===========================================================================
 *
 * 【背景】
 *   ECOS 求解器要求输入的稀疏矩阵 A 和 G 为 CCS (Compressed Column Storage)
 *   格式。但我们的问题建模代码按行（逐约束）构造矩阵更直观，因此先以 CRS
 *   (Compressed Row Storage) 格式存储，再通过本函数转换为 CCS。
 *
 * 【算法】
 *   1. 遍历 CRS 的列索引，统计每列的非零元素数目     → w[col] = nnz_count
 *   2. 前缀和累积得到 CCS 列指针                     → CCMjc[col] = start_pos
 *   3. 按行遍历 CRS，将每个非零元填入 CCS 对应位置
 *
 * 【时间复杂度】 O(nnz)，单次线性扫描
 * 【空间复杂度】 O(n) 临时工作数组 w
 *
 * 【CRS 格式说明】
 *   CRMpr[k]  = 第 k 个非零元的数值
 *   CRMjc[k]  = 第 k 个非零元的列号 (0-based)
 *   CRMir[i]  = 第 i 行第一个非零元在 CRMpr/CRMjc 中的索引
 *   CRMir[i+1] - CRMir[i] = 第 i 行的非零元个数
 *
 * 【CCS 格式说明 (输出)】
 *   CCMpr[k]  = 第 k 个非零元的数值
 *   CCMir[k]  = 第 k 个非零元的行号
 *   CCMjc[j]  = 第 j 列第一个非零元在 CCMpr/CCMir 中的索引
 *   CCMjc[j+1] - CCMjc[j] = 第 j 列的非零元个数
 *
 * 作者: LShang
 * 日期: 2024-03-29 / 注释: 2026-07-12
 * ===========================================================================
 */

#include "glblopts.h"

void CRM2CCM(
    idxint CRMjc[], idxint CRMir[], pfloat CRMpr[],
    idxint CCMjc[], idxint CCMir[], pfloat CCMpr[],
    idxint m, idxint n, idxint nnz, idxint w[])
{
    idxint i, j, k, pos;

    /* ===== 阶段1: 初始化临时工作数组 w ===== */
    /* w[j] 将依次用于: 统计每列nnz数 → 记录CCS写入位置 */
    for (j = 0; j < n; j++) {
        w[j] = 0;
    }

    /* ===== 阶段2: 统计每列的非零元个数 ===== */
    /* CRMjc[k] 是第k个非零元所在的列号 */
    for (k = 0; k < nnz; k++) {
        w[CRMjc[k]]++;
    }

    /* ===== 阶段3: 前缀和 → CCS列指针数组 CCMjc ===== */
    /* CCMjc[j] = 第j列第一个非零元在 CCMpr/CCMir 中的位置 */
    CCMjc[0] = 0;
    for (j = 0; j < n; j++) {
        CCMjc[j + 1] = CCMjc[j] + w[j];
    }

    /* ===== 阶段4: 将 w 重置为 "下次写入位置" ===== */
    /* w[j] = CCMjc[j]，即第j列当前尚未写入的第一个位置 */
    for (j = 0; j < n; j++) {
        w[j] = CCMjc[j];
    }

    /* ===== 阶段5: 按行遍历CRS，将每个非零元填入CCS ===== */
    for (i = 0; i < m; i++) {
        /* 遍历第 i 行的所有非零元 */
        for (k = CRMir[i]; k < CRMir[i + 1]; k++) {
            /* 取出当前写入位置，然后指针后移 */
            pos = w[CRMjc[k]]++;

            /* 填入 CCS: 行号 = i, 数值不变 */
            CCMir[pos] = i;
            CCMpr[pos] = CRMpr[k];
        }
    }

    /* 转换完成。CCS 结果存储在 CCMjc, CCMir, CCMpr 中 */
}
