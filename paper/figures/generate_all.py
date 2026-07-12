#!/usr/bin/env python3
"""
Generate 10 publication-quality figures for Mars landing SOCP paper.
All sizing fits A4 single-column (text width ~16cm / 6.3in).
"""
import json, os, numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import rcParams

# ============================================================
# Paths & data
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(SCRIPT_DIR)), 'paper', 'data')

with open(os.path.join(DATA_DIR, 'trajectory.json')) as f:
    traj = json.load(f)
with open(os.path.join(DATA_DIR, 'solver_comparison.json')) as f:
    solvers = json.load(f)

N, dt, tf = traj['N'], traj['dt'], traj['tf']
time = np.array(traj['time'])
rx, ry, rz = np.array(traj['rx']), np.array(traj['ry']), np.array(traj['rz'])
vx, vy, vz = np.array(traj['vx']), np.array(traj['vy']), np.array(traj['vz'])
mass = np.array(traj['mass'])
ux, uy, uz = np.array(traj['ux']), np.array(traj['uy']), np.array(traj['uz'])
sigma = np.array(traj['sigma'])
u_norm = np.sqrt(ux**2 + uy**2 + uz**2)

# ============================================================
# Professional academic style
# ============================================================
rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Liberation Serif', 'DejaVu Serif', 'Times New Roman'],
    'font.size': 7,
    'axes.labelsize': 7,
    'axes.titlesize': 8,
    'xtick.labelsize': 6,
    'ytick.labelsize': 6,
    'legend.fontsize': 6,
    'legend.framealpha': 0.7,
    'lines.linewidth': 1.0,
    'axes.linewidth': 0.5,
    'grid.alpha': 0.2,
    'grid.linestyle': '--',
    'grid.linewidth': 0.3,
    'pdf.fonttype': 42,
    'ps.fonttype': 42,
    'text.usetex': False,
    'figure.dpi': 150,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.02,
})
COLORS = plt.get_cmap('tab10').colors

# Compact sizes — LaTeX \includegraphics will scale these down further
W = 3.2     # figure width (inches) — LaTeX scales to ~0.6\textwidth
H = 1.8     # base height for single-panel figures
H2 = 2.6    # height for 2-subplot figures
H3 = 3.4    # height for 3-subplot figures

def grid(ax):
    ax.grid(True, alpha=0.25, linestyle='--', linewidth=0.2)
    ax.tick_params(direction='in', top=True, right=True, width=0.5, labelsize=6)

def save(fig, name):
    pdf = os.path.join(SCRIPT_DIR, f'{name}.pdf')
    png = os.path.join(SCRIPT_DIR, f'{name}.png')
    fig.savefig(pdf, bbox_inches='tight', pad_inches=0.02)
    fig.savefig(png, dpi=300, bbox_inches='tight', pad_inches=0.02)
    plt.close(fig)
    print(f'  {name}.pdf + .png')

# ============================================================
# Fig 1 — 3D trajectory
# ============================================================
def fig1():
    fig = plt.figure(figsize=(W * 1.1, W * 1.0))
    ax = fig.add_subplot(111, projection='3d')
    ax.view_init(elev=22, azim=-48)

    points = np.array([rx, ry, rz]).T
    for i in range(len(points) - 1):
        ax.plot(rx[i:i+2], ry[i:i+2], rz[i:i+2],
                color=plt.cm.viridis(i/len(points)), linewidth=0.7, alpha=0.8)

    ax.scatter(*[rx[0]],  *[ry[0]],  *[rz[0]],  color='#d62728', s=35,
               marker='o', edgecolors='k', linewidth=0.2, zorder=10, label='Start (t=0)')
    ax.scatter(*[rx[-1]], *[ry[-1]], *[rz[-1]], color='#2ca02c', s=50,
               marker='^', edgecolors='k', linewidth=0.2, zorder=10, label='Landing (t=81s)')

    xx, yy_ = np.meshgrid(np.linspace(-3, 3, 3), np.linspace(-3, 3, 3))
    ax.plot_surface(xx * 300, yy_ * 300, np.zeros_like(xx),
                    alpha=0.06, color='gray', zorder=0)

    ax.set_xlabel('$r_x$ (m)', labelpad=3)
    ax.set_ylabel('$r_y$ (m)', labelpad=3)
    ax.set_zlabel('$r_z$ (m)', labelpad=3)
    ax.legend(loc='upper left', fontsize=6, framealpha=0.6)

    ax.set_xlim(0, 1550)
    ax.set_ylim(-150, 150)
    ax.set_zlim(0, 2100)
    ax.set_box_aspect([1, 0.3, 1.3])
    ax.tick_params(labelsize=5, pad=1)

    fig.tight_layout(pad=0.05)
    save(fig, 'fig01_3d_trajectory')


# ============================================================
# Fig 2 — Position vs time (3 subplots, stacked vertically)
# ============================================================
def fig2():
    fig, axes = plt.subplots(3, 1, figsize=(W, H3), sharex=True)
    fig.subplots_adjust(hspace=0.12)
    data = [(rx, '$r_x$ (m)', COLORS[0]),
            (ry, '$r_y$ (m)', COLORS[1]),
            (rz, '$r_z$ (m)', COLORS[2])]
    for i, (ax, (d, lab, c)) in enumerate(zip(axes, data)):
        ax.plot(time, d, color=c, linewidth=0.9)
        ax.set_ylabel(lab, fontsize=7)
        ax.axhline(y=0, color='gray', linewidth=0.2, linestyle=':')
        grid(ax)
        if i < 2:
            ax.tick_params(labelbottom=False)
    axes[-1].set_xlabel('Time (s)', fontsize=7)
    save(fig, 'fig02_position_time')


# ============================================================
# Fig 3 — Velocity vs time
# ============================================================
def fig3():
    fig, axes = plt.subplots(3, 1, figsize=(W, H3), sharex=True)
    fig.subplots_adjust(hspace=0.12)
    data = [(vx, '$v_x$ (m/s)', COLORS[0]),
            (vy, '$v_y$ (m/s)', COLORS[1]),
            (vz, '$v_z$ (m/s)', COLORS[2])]
    for i, (ax, (d, label, c)) in enumerate(zip(axes, data)):
        ax.plot(time, d, color=c, linewidth=0.9)
        ax.set_ylabel(label, fontsize=7)
        ax.axhline(y=0, color='gray', linewidth=0.2, linestyle=':')
        grid(ax)
        if i < 2:
            ax.tick_params(labelbottom=False)
    axes[-1].set_xlabel('Time (s)')
    save(fig, 'fig03_velocity_time')


# ============================================================
# Fig 4 — Mass evolution
# ============================================================
def fig4():
    fig, ax = plt.subplots(figsize=(W, H))
    ax.plot(time, mass, color=COLORS[7], linewidth=0.9)
    ax.axhline(y=mass[-1], color='gray', linestyle=':', linewidth=0.8,
               label=f'Terminal: {mass[-1]:.1f} kg')
    ax.axhline(y=mass[0], color='gray', linestyle=':', linewidth=0.8,
               label=f'Initial: {mass[0]:.1f} kg')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Mass (kg)')
    ax.legend(fontsize=6, loc='lower left')
    grid(ax)
    fig.tight_layout(pad=0.1)
    save(fig, 'fig04_mass_evolution')


# ============================================================
# Fig 5 — Thrust: ‖u‖ vs σ
# ============================================================
def fig5():
    fig, ax = plt.subplots(figsize=(W, H))
    ax.plot(time, u_norm, color=COLORS[0], linewidth=0.9, label=r'$\|\mathbf{u}\|$')
    ax.plot(time, sigma, color=COLORS[3], linewidth=0.9, linestyle='--', dashes=(5, 3),
            label=r'$\sigma$')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Thrust acceleration (N/kg)')
    ax.legend(fontsize=7)
    grid(ax)
    fig.tight_layout(pad=0.1)
    save(fig, 'fig05_thrust_comparison')


# ============================================================
# Fig 6 — Glide slope constraint
# ============================================================
def fig6():
    theta_rad = np.radians(86.0)
    lhs = np.sqrt(ry**2 + rz**2)
    rhs = rx * np.tan(theta_rad)
    margin = rhs - lhs

    fig, axes = plt.subplots(2, 1, figsize=(W, H2), sharex=True)
    fig.subplots_adjust(hspace=0.12)

    ax = axes[0]
    ax.plot(time, lhs, color=COLORS[2], linewidth=0.9,
            label=r'$\|[r_y,r_z]\|$')
    ax.plot(time, rhs, color=COLORS[3], linewidth=0.9, linestyle='--', dashes=(5, 3),
            label=r'$r_x\tan\theta$')
    ax.set_ylabel('Distance (m)', fontsize=7)
    ax.legend(fontsize=6, loc='upper left')
    grid(ax)
    ax.tick_params(labelbottom=False)

    ax = axes[1]
    ax.fill_between(time, 0, margin, color=COLORS[4], alpha=0.15)
    ax.plot(time, margin, color=COLORS[4], linewidth=0.8)
    ax.axhline(y=0, color='k', linewidth=0.2)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel(r'$r_x\tan\theta - \|[r_y,r_z]\|$ (m)', fontsize=7)
    grid(ax)

    fig.tight_layout(pad=0.1)
    save(fig, 'fig06_glide_slope')


# ============================================================
# Fig 7 — Thrust cone constraint
# ============================================================
def fig7():
    margin = sigma - u_norm

    fig, axes = plt.subplots(2, 1, figsize=(W, H2), sharex=True)
    fig.subplots_adjust(hspace=0.12)

    ax = axes[0]
    ax.plot(time, u_norm, color=COLORS[0], linewidth=0.9, label=r'$\|\mathbf{u}\|$')
    ax.plot(time, sigma, color=COLORS[3], linewidth=0.9, linestyle='--', dashes=(5, 3),
            label=r'$\sigma$')
    ax.set_ylabel('Thrust (N/kg)', fontsize=7)
    ax.legend(fontsize=6)
    grid(ax)
    ax.tick_params(labelbottom=False)

    ax = axes[1]
    ax.fill_between(time, 0, margin, color=COLORS[5], alpha=0.15)
    ax.plot(time, margin, color=COLORS[5], linewidth=0.8)
    ax.axhline(y=0, color='k', linewidth=0.2)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel(r'$\sigma - \|\mathbf{u}\|$ (N/kg)', fontsize=7)
    ax.set_yscale('log')
    grid(ax)

    fig.tight_layout(pad=0.1)
    save(fig, 'fig07_thrust_cone')


# ============================================================
# Fig 8 — Fuel consumption bar chart
# ============================================================
def fig8():
    names = [s['solver'].replace('+','+\n') for s in solvers]
    fuels = [s['fuel_kg'] for s in solvers]

    fig, ax = plt.subplots(figsize=(W, H * 1.05))
    bars = ax.bar(range(len(names)), fuels, color=[COLORS[0], COLORS[1], COLORS[2]],
                  width=0.55, edgecolor='white', linewidth=0.2, zorder=3)
    ax.set_ylabel('Fuel consumption (kg)')
    ax.set_ylim(395, 410)
    ax.axhline(y=400.7, color='gray', linestyle='--', linewidth=0.6, alpha=0.5)
    for bar, val in zip(bars, fuels):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f'{val:.1f}', ha='center', va='bottom', fontsize=7)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=7)
    grid(ax)
    fig.tight_layout(pad=0.1)
    save(fig, 'fig08_fuel_comparison')


# ============================================================
# Fig 9 — Solve time bar chart
# ============================================================
def fig9():
    names = [s['solver'].replace('+','+\n') for s in solvers]
    times_ms = [s['time_ms'] for s in solvers]

    fig, ax = plt.subplots(figsize=(W, H * 1.05))
    bars = ax.bar(range(len(names)), times_ms, color=[COLORS[0], COLORS[1], COLORS[2]],
                  width=0.55, edgecolor='white', linewidth=0.2, zorder=3)
    ax.set_ylabel('Solve time (ms)')
    ax.set_yscale('log')
    for bar, val in zip(bars, times_ms):
        lbl = f'{val:.0f}' if val < 1000 else f'{val/1000:.2f}s'
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 1.15,
                lbl, ha='center', va='bottom', fontsize=6)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, fontsize=7)
    grid(ax)
    fig.tight_layout(pad=0.1)
    save(fig, 'fig09_time_comparison')


# ============================================================
# Fig 10 — Control components (ux, uy, uz)
# ============================================================
def fig10():
    fig, axes = plt.subplots(3, 1, figsize=(W, H3), sharex=True)
    fig.subplots_adjust(hspace=0.12)
    data = [(ux, '$u_x$ (N/kg)', COLORS[0]),
            (uy, '$u_y$ (N/kg)', COLORS[1]),
            (uz, '$u_z$ (N/kg)', COLORS[2])]
    for i, (ax, (d, label, c)) in enumerate(zip(axes, data)):
        ax.plot(time, d, color=c, linewidth=0.9)
        ax.set_ylabel(label, fontsize=7)
        ax.axhline(y=0, color='gray', linewidth=0.2, linestyle=':')
        grid(ax)
        if i < 2:
            ax.tick_params(labelbottom=False)
    axes[-1].set_xlabel('Time (s)')
    save(fig, 'fig10_control_time')


# ============================================================
if __name__ == '__main__':
    print(f'Trajectory: N={N}, dt={dt:.1f}s, tf={tf:.0f}s, fuel={traj["fuel"]:.1f}kg')
    print(f'Mass: {mass[0]:.1f} → {mass[-1]:.1f} kg\n')
    fig1(); fig2(); fig3(); fig4(); fig5()
    fig6(); fig7(); fig8(); fig9(); fig10()
    print('\nDone — 10 figures.')
