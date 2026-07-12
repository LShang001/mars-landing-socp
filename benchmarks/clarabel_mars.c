/**
 * ===========================================================================
 * clarabel_mars.c — Clarabel C 求解火星着陆 SOCP
 *
 * ECOS 形式:  min c'x  s.t. Ax=b, Gx+s=h, s∈K
 * Clarabel:   min ½xᵀPx + qᵀx  s.t. Ax+s=b, s∈K
 * 转换: P=0, q=c, A=[A;G], b=[b;h], 锥 = SOC3×31 + SOC4×31
 *
 * 构建: gcc -O3 -o clarabel_mars clarabel_mars.c -lclarabel_c -lm
 * 运行: LD_LIBRARY_PATH=/usr/local/lib ./clarabel_mars
 * ===========================================================================
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include "c/DefaultSolver.h"
#include "c/DefaultSettings.h"

/* ===== 问题参数 (同 MarsLanding.h) ===== */
#define N    30
#define NX   7
#define NU   4
#define N_VAR  ((NX+NU)*(N+1))       /* 341 */
#define P_EQ   (NX+NX-1 + NX*N)       /* 223 */
#define L_G    ((N+1)*4)              /* 124 */
#define M_G    (L_G+(N+1)*4+(N+1)*3)   /* 341 */
#define NNZA   733
#define NNZG   403
#define VAR_IDX(k, field)  ((k)*(NX+NU)+(field))

typedef int idxint;

static const double g_mars=3.7114, g_earth=9.807, m0v=1905.0;
static const double I_sp=225.0, T_max=3100.0, t_final=81.0;

/* ===== CRS→CCS ===== */
static void crs2ccs(idxint *crjc, idxint *crir, double *crpr,
                     idxint *ccjc, idxint *ccir, double *ccpr,
                     int m, int n, int nnz)
{
    int *w = calloc(n, sizeof(int));
    for (int k=0;k<nnz;k++) w[crjc[k]]++;
    ccjc[0]=0;
    for (int j=0;j<n;j++) ccjc[j+1]=ccjc[j]+w[j];
    for (int j=0;j<n;j++) w[j]=ccjc[j];
    for (int i=0;i<m;i++)
        for (int k=crir[i];k<crir[i+1];k++) {
            int pos=w[crjc[k]]++;
            ccir[pos]=i; ccpr[pos]=crpr[k];
        }
    free(w);
}

/* ===== 主程序 ===== */
int main(void)
{
    printf("========================================================\n");
    printf("  Clarabel C — 火星着陆 SOCP benchmark\n");
    printf("========================================================\n");

    /* ---- 物理参数 ---- */
    double phi_rad=27.0*M_PI/180.0, theta_rad=(90.0-4.0)*M_PI/180.0;
    double T_min=0.3*T_max, T2=0.8*T_max;
    double alpha=1.0/(I_sp*g_earth*cos(phi_rad));
    double rho_1=6.0*T_min*cos(phi_rad), rho_2=6.0*T2*cos(phi_rad);
    double dt=t_final/N, tan_th=tan(theta_rad);

    /* 时变参数 */
    double z_0[N+1], mu_1[N+1], mu_2[N+1];
    for (int k=0;k<=N;k++) {
        double tk=k*dt;
        z_0[k]=log(m0v-alpha*rho_2*tk);
        mu_1[k]=rho_1*exp(-z_0[k]);
        mu_2[k]=rho_2*exp(-z_0[k]);
    }

    /* ---- 目标 q = c ---- */
    double *q_vec = calloc(N_VAR, sizeof(double));
    for (int k=0;k<=N;k++) q_vec[VAR_IDX(k,NX+3)]=1.0;

    /* ---- CRS 构造 A ---- */
    idxint CRAjc[NNZA], CRAir[P_EQ+1], CRGjc[NNZG], CRGir[M_G+1];
    double CRApr[NNZA], CRGpr[NNZG], b_a[P_EQ], b_g[M_G];

    int idx_row=0, idx_nnz=0, row_nnz=0; CRAir[0]=0;
    #define P(col,val) do{CRAjc[idx_nnz]=(col);CRApr[idx_nnz]=(val);idx_nnz++;row_nnz++;}while(0)
    #define R(val) do{CRAir[idx_row+1]=CRAir[idx_row]+row_nnz;b_a[idx_row]=(val);idx_row++;row_nnz=0;}while(0)

    P(VAR_IDX(0,0),1);R(1500);P(VAR_IDX(0,1),1);R(0);P(VAR_IDX(0,2),1);R(2000);
    P(VAR_IDX(0,3),1);R(-75);P(VAR_IDX(0,4),1);R(0);P(VAR_IDX(0,5),1);R(100);
    P(VAR_IDX(0,6),1);R(log(m0v));
    for (int fi=0;fi<6;fi++){P(VAR_IDX(N,fi),1);R(0);}
    for (int k=0;k<N;k++){
        P(VAR_IDX(k,0),1);P(VAR_IDX(k,3),dt);P(VAR_IDX(k,NX+0),0.5*dt*dt);P(VAR_IDX(k+1,0),-1);R(g_mars*0.5*dt*dt);
        P(VAR_IDX(k,1),1);P(VAR_IDX(k,4),dt);P(VAR_IDX(k,NX+1),0.5*dt*dt);P(VAR_IDX(k+1,1),-1);R(0);
        P(VAR_IDX(k,2),1);P(VAR_IDX(k,5),dt);P(VAR_IDX(k,NX+2),0.5*dt*dt);P(VAR_IDX(k+1,2),-1);R(0);
        P(VAR_IDX(k,3),1);P(VAR_IDX(k,NX+0),dt);P(VAR_IDX(k+1,3),-1);R(g_mars*dt);
        P(VAR_IDX(k,4),1);P(VAR_IDX(k,NX+1),dt);P(VAR_IDX(k+1,4),-1);R(0);
        P(VAR_IDX(k,5),1);P(VAR_IDX(k,NX+2),dt);P(VAR_IDX(k+1,5),-1);R(0);
        P(VAR_IDX(k,6),1);P(VAR_IDX(k,NX+3),-alpha*dt);P(VAR_IDX(k+1,6),-1);R(0);
    }

    int idx_gr=0,idx_gn=0,gr_nnz=0; CRGir[0]=0;
    #define G(col,val) do{CRGjc[idx_gn]=(col);CRGpr[idx_gn]=(val);idx_gn++;gr_nnz++;}while(0)
    #define H(val) do{CRGir[idx_gr+1]=CRGir[idx_gr]+gr_nnz;b_g[idx_gr]=(val);idx_gr++;gr_nnz=0;}while(0)
    for (int k=0;k<=N;k++){
        G(VAR_IDX(k,6),-mu_1[k]);G(VAR_IDX(k,NX+3),-1);H(-mu_1[k]*(1+z_0[k]));
        G(VAR_IDX(k,6),+mu_2[k]);G(VAR_IDX(k,NX+3),+1);H(+mu_2[k]*(1+z_0[k]));
        G(VAR_IDX(k,6),-1);H(-log(m0v-alpha*rho_2*k*dt));
        G(VAR_IDX(k,6),+1);H(+log(m0v-alpha*rho_1*k*dt));
    }
    for (int k=0;k<=N;k++){G(VAR_IDX(k,0),-tan_th);H(0);G(VAR_IDX(k,1),-1);H(0);G(VAR_IDX(k,2),-1);H(0);}
    for (int k=0;k<=N;k++){G(VAR_IDX(k,NX+3),-1);H(0);G(VAR_IDX(k,NX+0),-1);H(0);G(VAR_IDX(k,NX+1),-1);H(0);G(VAR_IDX(k,NX+2),-1);H(0);}
    #undef P
    #undef R
    #undef G
    #undef H

    /* ---- CCS 转换并合并 ---- */
    idxint CAj[N_VAR+1],CAi[NNZA],CGj[N_VAR+1],CGi[NNZG];
    double CAp[NNZA],CGp[NNZG];
    crs2ccs(CRAjc,CRAir,CRApr,CAj,CAi,CAp,P_EQ,N_VAR,NNZA);
    crs2ccs(CRGjc,CRGir,CRGpr,CGj,CGi,CGp,M_G,N_VAR,NNZG);

    int mt=P_EQ+M_G, nzt=NNZA+NNZG;
    int *colc=calloc(N_VAR,sizeof(int));
    for (int j=0;j<N_VAR;j++) colc[j]=(CAj[j+1]-CAj[j])+(CGj[j+1]-CGj[j]);
    uintptr_t *Aj_cl=malloc((N_VAR+1)*sizeof(uintptr_t));
    Aj_cl[0]=0; for (int j=0;j<N_VAR;j++) Aj_cl[j+1]=Aj_cl[j]+colc[j];
    uintptr_t *Ai_cl=malloc(nzt*sizeof(uintptr_t));
    double *Ap_cl=malloc(nzt*sizeof(double));
    for (int j=0;j<N_VAR;j++){
        int pos=Aj_cl[j];
        for (int k=CAj[j];k<CAj[j+1];k++){Ai_cl[pos]=CAi[k];Ap_cl[pos]=CAp[k];pos++;}
        for (int k=CGj[j];k<CGj[j+1];k++){Ai_cl[pos]=CGi[k]+P_EQ;Ap_cl[pos]=CGp[k];pos++;}
    }
    double *b_cl=malloc(mt*sizeof(double));
    memcpy(b_cl,b_a,P_EQ*sizeof(double)); memcpy(b_cl+P_EQ,b_g,M_G*sizeof(double));

    /* ---- 锥定义 (必须按行顺序匹配) ----
     *   行 0..222:   等式约束 → ZeroCone(223)
     *   行 223..346: 线性不等式 → NonnegativeCone(124)
     *   行 347..439: 下滑角 SOC → SecondOrderCone(3) ×31
     *   行 440..563: 推力 SOC → SecondOrderCone(4) ×31
     */
    uintptr_t n_cones = 2 + 62;  /* Zero + Nonneg + 62 SOC */
    ClarabelSupportedConeT cones[64];
    cones[0] = ClarabelZeroConeT_f64(P_EQ);          /* 等式 */
    cones[1] = ClarabelNonnegativeConeT_f64(L_G);     /* 线性不等式 */
    for (int i=0;i<31;i++) cones[2+i]  = ClarabelSecondOrderConeT_f64(3);
    for (int i=0;i<31;i++) cones[33+i] = ClarabelSecondOrderConeT_f64(4);

    /* ---- Clarabel 数据 ---- */
    uintptr_t *P_colptr=malloc((N_VAR+1)*sizeof(uintptr_t));
    for (int j=0;j<=N_VAR;j++) P_colptr[j]=0;
    ClarabelCscMatrix P_mat={.m=N_VAR,.n=N_VAR,.colptr=P_colptr,.rowval=NULL,.nzval=NULL};
    ClarabelCscMatrix A_mat={.m=mt,.n=N_VAR,.colptr=Aj_cl,.rowval=Ai_cl,.nzval=Ap_cl};
    ClarabelDefaultSettings settings=clarabel_DefaultSettings_default();
    /* 调低精度以加速 */
    settings.tol_gap_abs=1e-6; settings.tol_gap_rel=1e-6;
    settings.tol_feas=1e-6; settings.tol_infeas_abs=1e-6; settings.tol_infeas_rel=1e-6;

    /* ---- 求解 ---- */
    printf("  创建求解器...\n");
    ClarabelDefaultSolver *solver=clarabel_DefaultSolver_new(&P_mat,q_vec,&A_mat,b_cl,n_cones,cones,&settings);
    if (!solver){printf("  ERROR\n");return 1;}

    clarabel_DefaultSolver_solve(solver); /* 预热 */

    const int NRUNS=1000;
    printf("  求解 %d 次...\n",NRUNS);
    clock_t ts=clock();
    for (int run=0;run<NRUNS;run++) clarabel_DefaultSolver_solve(solver);
    clock_t te=clock();
    double ms=1000.0*(te-ts)/CLOCKS_PER_SEC;

    /* ---- 结果 ---- */
    ClarabelDefaultSolution sol=clarabel_DefaultSolver_solution(solver);
    ClarabelDefaultInfo info=clarabel_DefaultSolver_info(solver);

    /* 检查求解器状态 */
    if (info.status != ClarabelSolved) {
        printf("\n  ERROR: Clarabel 求解未达最优 (status=%d), 跳过结果输出\n", (int)info.status);
        clarabel_DefaultSolver_free(solver);
        free(Aj_cl); free(Ai_cl); free(Ap_cl); free(b_cl); free(q_vec); free(colc); free(P_colptr);
        return 1;
    }

    double zf=((double*)sol.x)[N*(NX+NU)+6];
    double fuel=m0v-exp(zf);

    printf("\n  Clarabel C benchmark:\n");
    printf("    %d runs: %.0f ms total, %.3f ms/solve\n",NRUNS,ms,ms/NRUNS);
    printf("    燃料: %.1f kg  (%s)\n",fuel,fabs(fuel-400.7)<1.0?"✅":"⚠");
    printf("    迭代: %u, 状态: %s\n",info.iterations,
           info.status==ClarabelSolved?"Solved":info.status==ClarabelPrimalInfeasible?"PrimalInfeas":info.status==ClarabelDualInfeasible?"DualInfeas":info.status==ClarabelAlmostSolved?"AlmostSolved":"?");
    printf("    求解时间 (内部): %.3f ms\n",info.solve_time*1000);

    printf("\n  ECOS C (MarsLanding.c) 参考:\n");
    printf("    1000 runs: ~8 ms, ~0.008 ms/solve\n");
    printf("    (ECOS 用 CCS 稀疏, Clarabel 用 CCS 稀疏 — 硬件相同)\n");

    printf("\n========================================================\n");

    clarabel_DefaultSolver_free(solver);
    free(Aj_cl); free(Ai_cl); free(Ap_cl); free(b_cl); free(q_vec); free(colc); free(P_colptr);
    return 0;
}
