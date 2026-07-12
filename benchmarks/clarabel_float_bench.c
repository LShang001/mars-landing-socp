/**
 * Clarabel double vs float precision benchmark — 火星着陆 SOCP
 *
 * 构建: gcc -O3 -o clarabel_float_bench clarabel_float_bench.c -lclarabel_c -lm
 * 运行: LD_LIBRARY_PATH=/usr/local/lib ./clarabel_float_bench
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include "c/DefaultSolver.h"

#define N 30
#define NX 7
#define NU 4
#define N_VAR ((NX+NU)*(N+1))
#define P_EQ (NX+NX-1+NX*N)
#define L_G ((N+1)*4)
#define M_G (L_G+(N+1)*4+(N+1)*3)
#define NNZA 733
#define NNZG 403
#define VAR_IDX(k,f) ((k)*(NX+NU)+(f))

typedef int idxint;
static const double g_m=3.7114,g_e=9.807,m0v=1905.0,I_sp=225.0,T_max=3100.0,t_f=81.0;

static void crs2ccs(idxint *crjc,idxint *crir,double *crpr,
                     idxint *ccjc,idxint *ccir,double *ccpr,int m,int n,int nnz){
    int *w=calloc(n,sizeof(int));
    for(int k=0;k<nnz;k++)w[crjc[k]]++; ccjc[0]=0;
    for(int j=0;j<n;j++)ccjc[j+1]=ccjc[j]+w[j];
    for(int j=0;j<n;j++)w[j]=ccjc[j];
    for(int i=0;i<m;i++)for(int k=crir[i];k<crir[i+1];k++){int pos=w[crjc[k]]++;ccir[pos]=i;ccpr[pos]=crpr[k];}
    free(w);
}

/* 矩阵构造 (double) */
static void build_matrices(
    double **Ap,uintptr_t **Aj,uintptr_t **Ai,
    double **bc,double **q,uintptr_t *nc_out,
    ClarabelSupportedConeT **cs_out)
{
    double phi=27*M_PI/180,th=(90-4)*M_PI/180,dt=t_f/N,tn=tan(th);
    double T_min=0.3*T_max,T2=0.8*T_max,alph=1/(I_sp*g_e*cos(phi));
    double r1=6*T_min*cos(phi),r2=6*T2*cos(phi);
    double z0[N+1],mu1[N+1],mu2[N+1];
    for(int k=0;k<=N;k++){double tk=k*dt;z0[k]=log(m0v-alph*r2*tk);mu1[k]=r1*exp(-z0[k]);mu2[k]=r2*exp(-z0[k]);}
    *q=calloc(N_VAR,sizeof(double));
    for(int k=0;k<=N;k++)(*q)[VAR_IDX(k,NX+3)]=1;
    idxint CAj[NNZA],CAi[P_EQ+1],CGj[NNZG],CGi[M_G+1];
    double CAp[NNZA],CGp[NNZG],ba[P_EQ],bg[M_G];
    int ir=0,in=0,rn=0;CAi[0]=0;
    #define P(c,v)do{CAj[in]=(c);CAp[in]=(v);in++;rn++;}while(0)
    #define R(v)do{CAi[ir+1]=CAi[ir]+rn;ba[ir]=(v);ir++;rn=0;}while(0)
    P(VAR_IDX(0,0),1);R(1500);P(VAR_IDX(0,1),1);R(0);P(VAR_IDX(0,2),1);R(2000);
    P(VAR_IDX(0,3),1);R(-75);P(VAR_IDX(0,4),1);R(0);P(VAR_IDX(0,5),1);R(100);
    P(VAR_IDX(0,6),1);R(log(m0v));
    for(int f=0;f<6;f++){P(VAR_IDX(N,f),1);R(0);}
    for(int k=0;k<N;k++){
        P(VAR_IDX(k,0),1);P(VAR_IDX(k,3),dt);P(VAR_IDX(k,NX+0),0.5*dt*dt);P(VAR_IDX(k+1,0),-1);R(g_m*0.5*dt*dt);
        P(VAR_IDX(k,1),1);P(VAR_IDX(k,4),dt);P(VAR_IDX(k,NX+1),0.5*dt*dt);P(VAR_IDX(k+1,1),-1);R(0);
        P(VAR_IDX(k,2),1);P(VAR_IDX(k,5),dt);P(VAR_IDX(k,NX+2),0.5*dt*dt);P(VAR_IDX(k+1,2),-1);R(0);
        P(VAR_IDX(k,3),1);P(VAR_IDX(k,NX+0),dt);P(VAR_IDX(k+1,3),-1);R(g_m*dt);
        P(VAR_IDX(k,4),1);P(VAR_IDX(k,NX+1),dt);P(VAR_IDX(k+1,4),-1);R(0);
        P(VAR_IDX(k,5),1);P(VAR_IDX(k,NX+2),dt);P(VAR_IDX(k+1,5),-1);R(0);
        P(VAR_IDX(k,6),1);P(VAR_IDX(k,NX+3),-alph*dt);P(VAR_IDX(k+1,6),-1);R(0);
    }
    int ig=0,ig2=0,gn=0;CGi[0]=0;
    #define G(c,v)do{CGj[ig2]=(c);CGp[ig2]=(v);ig2++;gn++;}while(0)
    #define H(v)do{CGi[ig+1]=CGi[ig]+gn;bg[ig]=(v);ig++;gn=0;}while(0)
    for(int k=0;k<=N;k++){
        G(VAR_IDX(k,6),-mu1[k]);G(VAR_IDX(k,NX+3),-1);H(-mu1[k]*(1+z0[k]));
        G(VAR_IDX(k,6),+mu2[k]);G(VAR_IDX(k,NX+3),+1);H(+mu2[k]*(1+z0[k]));
        G(VAR_IDX(k,6),-1);H(-log(m0v-alph*r2*k*dt));
        G(VAR_IDX(k,6),+1);H(+log(m0v-alph*r1*k*dt));
    }
    for(int k=0;k<=N;k++){G(VAR_IDX(k,0),-tn);H(0);G(VAR_IDX(k,1),-1);H(0);G(VAR_IDX(k,2),-1);H(0);}
    for(int k=0;k<=N;k++){G(VAR_IDX(k,NX+3),-1);H(0);G(VAR_IDX(k,NX+0),-1);H(0);G(VAR_IDX(k,NX+1),-1);H(0);G(VAR_IDX(k,NX+2),-1);H(0);}
    #undef P
    #undef R
    #undef G
    #undef H
    idxint CCAj[N_VAR+1],CCAi[NNZA],CCGj[N_VAR+1],CCGi[NNZG];
    double CCAp[NNZA],CCGp[NNZG];
    crs2ccs(CAj,CAi,CAp,CCAj,CCAi,CCAp,P_EQ,N_VAR,NNZA);
    crs2ccs(CGj,CGi,CGp,CCGj,CCGi,CCGp,M_G,N_VAR,NNZG);
    int mt=P_EQ+M_G,nzt=NNZA+NNZG;
    int *cc=calloc(N_VAR,sizeof(int));
    for(int j=0;j<N_VAR;j++)cc[j]=(CCAj[j+1]-CCAj[j])+(CCGj[j+1]-CCGj[j]);
    *Aj=malloc((N_VAR+1)*sizeof(uintptr_t));
    (*Aj)[0]=0;for(int j=0;j<N_VAR;j++)(*Aj)[j+1]=(*Aj)[j]+cc[j];
    *Ai=malloc(nzt*sizeof(uintptr_t));
    *Ap=malloc(nzt*sizeof(double));
    for(int j=0;j<N_VAR;j++){int pos=(*Aj)[j];for(int k=CCAj[j];k<CCAj[j+1];k++){(*Ai)[pos]=CCAi[k];(*Ap)[pos]=CCAp[k];pos++;}for(int k=CCGj[j];k<CCGj[j+1];k++){(*Ai)[pos]=CCGi[k]+P_EQ;(*Ap)[pos]=CCGp[k];pos++;}}
    *bc=malloc(mt*sizeof(double));
    memcpy(*bc,ba,P_EQ*sizeof(double));memcpy(*bc+P_EQ,bg,M_G*sizeof(double));
    uintptr_t nc=64;
    *cs_out=malloc(nc*sizeof(ClarabelSupportedConeT));
    (*cs_out)[0]=ClarabelZeroConeT_f64(P_EQ);
    (*cs_out)[1]=ClarabelNonnegativeConeT_f64(L_G);
    for(int i=0;i<31;i++)(*cs_out)[2+i]=ClarabelSecondOrderConeT_f64(3);
    for(int i=0;i<31;i++)(*cs_out)[33+i]=ClarabelSecondOrderConeT_f64(4);
    *nc_out=nc; free(cc);
}

int main(void){
    printf("========================================================\n");
    printf("  Clarabel double vs float — 火星着陆 SOCP\n");
    printf("========================================================\n\n");

    /* 双精度 */
    double *Ap_d,*b_d,*q_d;
    uintptr_t *Aj_d,*Ai_d,nc_d;
    ClarabelSupportedConeT *cs_d;
    build_matrices(&Ap_d,&Aj_d,&Ai_d,&b_d,&q_d,&nc_d,&cs_d);

    uintptr_t Pc_d[N_VAR+1];
    for(int j=0;j<=N_VAR;j++)Pc_d[j]=0;
    ClarabelCscMatrix_f64 Pm_d={.m=N_VAR,.n=N_VAR,.colptr=Pc_d,.rowval=NULL,.nzval=NULL};
    ClarabelCscMatrix_f64 Am_d={.m=P_EQ+M_G,.n=N_VAR,.colptr=Aj_d,.rowval=Ai_d,.nzval=Ap_d};
    ClarabelDefaultSettings_f64 st_d=clarabel_DefaultSettings_f64_default();
    st_d.verbose=0;

    /* 预热 */
    ClarabelDefaultSolver_f64 *s_d=clarabel_DefaultSolver_f64_new(&Pm_d,q_d,&Am_d,b_d,nc_d,(ClarabelSupportedConeT_f64*)cs_d,&st_d);
    clarabel_DefaultSolver_f64_solve(s_d);

    const int NRUNS=500;
    clock_t t0=clock();
    for(int i=0;i<NRUNS;i++) clarabel_DefaultSolver_f64_solve(s_d);
    double ms_d=1000.0*(clock()-t0)/CLOCKS_PER_SEC;
    ClarabelDefaultInfo_f64 info_d=clarabel_DefaultSolver_f64_info(s_d);
    int f64_ok=(info_d.status==ClarabelSolved);
    double fuel_d=0;
    if (f64_ok) {
        ClarabelDefaultSolution_f64 sol_d=clarabel_DefaultSolver_f64_solution(s_d);
        fuel_d=m0v-exp(((double*)sol_d.x)[N*(NX+NU)+6]);
        printf("  double (f64):\n");
        printf("    %d runs: %.0f ms (%.2f ms/solve)\n",NRUNS,ms_d,ms_d/NRUNS);
        printf("    燃料: %.1f kg\n\n",fuel_d);
    } else {
        printf("  ERROR: f64 求解未达最优 (status=%d), 跳过结果\n",(int)info_d.status);
    }

    /* 单精度 */
    float *Ap_f=malloc((NNZA+NNZG)*sizeof(float));
    float *b_f=malloc((P_EQ+M_G)*sizeof(float));
    float *q_f=malloc(N_VAR*sizeof(float));
    for(int i=0;i<(P_EQ+M_G);i++) b_f[i]=(float)b_d[i];
    for(int i=0;i<N_VAR;i++) q_f[i]=(float)q_d[i];
    for(int i=0;i<Aj_d[N_VAR];i++) Ap_f[i]=(float)Ap_d[i];

    ClarabelCscMatrix_f32 Pm_f={.m=N_VAR,.n=N_VAR,.colptr=Pc_d,.rowval=NULL,.nzval=NULL};
    ClarabelCscMatrix_f32 Am_f={.m=P_EQ+M_G,.n=N_VAR,.colptr=Aj_d,.rowval=Ai_d,.nzval=Ap_f};
    ClarabelDefaultSettings_f32 st_f=clarabel_DefaultSettings_f32_default();
    st_f.verbose=0;
    /* 放宽 float 精度容差 */
    st_f.tol_gap_abs=1e-6; st_f.tol_gap_rel=1e-6;
    st_f.tol_feas=1e-6; st_f.tol_infeas_abs=1e-6; st_f.tol_infeas_rel=1e-6;

    ClarabelSupportedConeT_f32 *cs_f=malloc(nc_d*sizeof(ClarabelSupportedConeT_f32));
    cs_f[0]=ClarabelZeroConeT_f32(P_EQ);
    cs_f[1]=ClarabelNonnegativeConeT_f32(L_G);
    for(int i=0;i<31;i++) cs_f[2+i]=ClarabelSecondOrderConeT_f32(3);
    for(int i=0;i<31;i++) cs_f[33+i]=ClarabelSecondOrderConeT_f32(4);

    ClarabelDefaultSolver_f32 *s_f=clarabel_DefaultSolver_f32_new(&Pm_f,q_f,&Am_f,b_f,nc_d,cs_f,&st_f);
    clarabel_DefaultSolver_f32_solve(s_f);

    clock_t t1=clock();
    for(int i=0;i<NRUNS;i++) clarabel_DefaultSolver_f32_solve(s_f);
    double ms_f=1000.0*(clock()-t1)/CLOCKS_PER_SEC;
    ClarabelDefaultInfo_f32 info_f=clarabel_DefaultSolver_f32_info(s_f);
    int f32_ok=(info_f.status==ClarabelSolved);
    double fuel_f=0;
    if (f32_ok) {
        ClarabelDefaultSolution_f32 sol_f=clarabel_DefaultSolver_f32_solution(s_f);
        fuel_f=m0v-exp(((float*)sol_f.x)[N*(NX+NU)+6]);
        printf("  float  (f32):\n");
        printf("    %d runs: %.0f ms (%.2f ms/solve)\n",NRUNS,ms_f,ms_f/NRUNS);
        if (f64_ok)
            printf("    燃料: %.1f kg  (Δ=%.1f kg)\n\n",fuel_f,fuel_f-fuel_d);
        else
            printf("    燃料: %.1f kg\n\n",fuel_f);
    } else {
        printf("  ERROR: f32 求解未达最优 (status=%d), 跳过结果\n",(int)info_f.status);
    }
    if (f64_ok && f32_ok) {
        printf("  Speedup: %.1fx\n",ms_d/ms_f);
        printf("  精度损失: %.1f kg (%.2f%%)\n",fabs(fuel_f-fuel_d),fabs(fuel_f-fuel_d)/fuel_d*100);
    }
    printf("========================================================\n");

    clarabel_DefaultSolver_f64_free(s_d);clarabel_DefaultSolver_f32_free(s_f);
    free(Aj_d);free(Ai_d);free(Ap_d);free(Ap_f);free(b_d);free(b_f);free(q_d);free(q_f);free(cs_d);free(cs_f);
    return 0;
}
