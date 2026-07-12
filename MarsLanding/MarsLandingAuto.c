/**
 * ===========================================================================
 * MarsLandingAuto.c — 火星着陆自动建模版 (CasADi 生成CCS矩阵)
 * ===========================================================================
 *
 * 使用 CasADi (mars_codegen.py) 生成的 CCS 格式矩阵数据,
 * 直接喂给 ECOS, 跳过手写 CRS 构造和格式转换。
 *
 * 编译: cmake 自动生成 ecos_auto 目标
 * 运行: ./build/bin/ecos_auto
 * 预期: ~400.7 kg (与 C 手写版、CVXPY+ECOS Python 版完全一致)
 *
 * 作者: LShang + Hermes Agent
 * 日期: 2026-07-12
 * ===========================================================================
 */

#include "MarsLandingAutoData.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <math.h>
#include <time.h>

#include "MarsLanding.h"

int main(void)
{
    printf("==================================================\n"
           "  火星着陆 SOCP — 自动建模版 (CasADi)\n"
           "==================================================\n"
           "  维度: n=%d m=%d p=%d l=%d\n"
           "  A nnz=%d  G nnz=%d\n"
           "--------------------------------------------------\n",
           (int)N_VAR_AUTO, (int)M_G_AUTO, (int)P_EQ_AUTO, (int)L_G_AUTO,
           (int)NNZA_AUTO, (int)NNZG_AUTO);

    assert(NNZA_AUTO == 733 && NNZG_AUTO == 403);

    /* 可变副本 (ECOS预处理会修改矩阵) */
    pfloat  ap[733], gp[403], c[341], b[223], h[341];
    idxint  aj[342], ai[733], gj[342], gi[403], q[62];
    memcpy(ap,CCA_pr_auto,sizeof(ap)); memcpy(aj,CCA_jc_auto,sizeof(aj));
    memcpy(ai,CCA_ir_auto,sizeof(ai)); memcpy(gp,CCG_pr_auto,sizeof(gp));
    memcpy(gj,CCG_jc_auto,sizeof(gj)); memcpy(gi,CCG_ir_auto,sizeof(gi));
    memcpy(c,c_auto,sizeof(c)); memcpy(b,b_auto,sizeof(b));
    memcpy(h,h_auto,sizeof(h)); memcpy(q,q_auto,sizeof(q));

    pwork* w = ECOS_setup(N_VAR_AUTO,M_G_AUTO,P_EQ_AUTO,L_G_AUTO,NCONES_AUTO,
                          q,0, gp,gj,gi, ap,aj,ai, c,h,b);
    if(!w){ printf("ERROR: ECOS_setup failed\n"); return 1; }

    clock_t t0=clock();
    idxint exitflag;
    for(int r=0;r<1000;r++) {
        exitflag = ECOS_solve(w);
        if (exitflag != ECOS_OPTIMAL) {
            printf("WARNING: 第 %d 次求解未达最优 (exitflag=%d)\n",
                   r + 1, (int)exitflag);
        }
    }
    double ms=(double)(clock()-t0)/CLOCKS_PER_SEC*1000;

    double zf=w->x[N*(NX+NU)+6], fuel=1905.0-exp(zf);
    printf("  求解 1000 次: %.1f ms (%.2f ms/次)\n"
           "  燃料消耗: %.1f kg\n"
           "==================================================\n",
           ms,ms/1000,fuel);

    ECOS_cleanup(w,0);
    return 0;
}
