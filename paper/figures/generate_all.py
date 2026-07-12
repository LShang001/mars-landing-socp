#!/usr/bin/env python3
"""
Generate publication-quality figures for the Mars landing SOCP paper.
The PDF output is authoritative; PNG files are only convenient previews.
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
    'font.size': 9,
    'axes.labelsize': 9,
    'axes.titlesize': 10,
    'xtick.labelsize': 8,
    'ytick.labelsize': 8,
    'legend.fontsize': 8,
    'legend.framealpha': 0.95,
    'legend.edgecolor': '#C9CED6',
    'lines.linewidth': 1.6,
    'axes.linewidth': 0.8,
    'axes.edgecolor': '#3D4654',
    'axes.labelcolor': '#202833',
    'xtick.color': '#3D4654',
    'ytick.color': '#3D4654',
    'grid.alpha': 0.55,
    'grid.linestyle': '-',
    'grid.linewidth': 0.45,
    'pdf.fonttype': 42,
    'ps.fonttype': 42,
    'text.usetex': False,
    'figure.dpi': 180,
    'savefig.dpi': 360,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.02,
})
COLORS = ['#1D4E89', '#2C7DA0', '#168277', '#D97706', '#A23E48', '#6D597A']
TEXT = '#202833'
MUTED = '#6B7280'

# Sized for a readable 0.84\textwidth placement in a single-column A4 paper.
W = 6.1
H = 2.85
H2 = 4.15
H3 = 5.05

def grid(ax):
    ax.grid(axis='y', color='#D8DEE8')
    ax.set_axisbelow(True)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.tick_params(direction='out', width=0.7, length=3, labelsize=8)

def finish(fig):
    fig.tight_layout(pad=0.45)

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
    fig = plt.figure(figsize=(5.25, 4.45))
    ax = fig.add_subplot(111, projection='3d')
    ax.view_init(elev=20, azim=-62)
    ax.plot(rx, ry, rz, color=COLORS[0], linewidth=2.2, solid_capstyle='round')
    ax.scatter(rx[0], ry[0], rz[0], color='#C2414B', s=48, marker='o',
               edgecolors='white', linewidth=0.8, zorder=10, label='Initial state')
    ax.scatter(rx[-1], ry[-1], rz[-1], color='#168277', s=55, marker='^',
               edgecolors='white', linewidth=0.8, zorder=10, label='Landing')
    yy_, zz_ = np.meshgrid(np.linspace(-220, 220, 4), np.linspace(0, 350, 4))
    ax.plot_surface(np.zeros_like(yy_), yy_, zz_, alpha=0.06, color=MUTED)

    ax.set_xlabel('$r_x$ (m)', labelpad=4)
    ax.set_ylabel('$r_y$ (m)', labelpad=4)
    ax.set_zlabel('$r_z$ (m)', labelpad=5)
    ax.legend(loc='upper left', fontsize=7, borderpad=0.5)

    ax.set_xlim(0, 1550)
    ax.set_ylim(-150, 150)
    ax.set_zlim(0, 3400)
    ax.set_box_aspect([1.0, 0.34, 1.34])
    ax.tick_params(labelsize=7, pad=1)
    ax.xaxis.pane.fill = False
    ax.yaxis.pane.fill = False
    ax.zaxis.pane.fill = False
    finish(fig)
    save(fig, 'fig01_3d_trajectory')


# ============================================================
# Fig 2 — Position vs time (3 subplots, stacked vertically)
# ============================================================
def fig2():
    fig, axes = plt.subplots(2, 1, figsize=(W, H2), sharex=True)
    fig.subplots_adjust(hspace=0.14)
    data = [(rx, '$r_x$ (m)', COLORS[0]), (rz, '$r_z$ (m)', COLORS[2])]
    for i, (ax, (d, lab, c)) in enumerate(zip(axes, data)):
        ax.plot(time, d, color=c, linewidth=1.7)
        ax.set_ylabel(lab)
        ax.axhline(y=0, color=MUTED, linewidth=0.65, linestyle=':')
        grid(ax)
        if i < 1:
            ax.tick_params(labelbottom=False)
    axes[-1].set_xlabel('Time (s)')
    axes[0].text(0.98, 0.10, r'$r_y(t)=0$ (symmetric boundary)', transform=axes[0].transAxes,
                 ha='right', va='bottom', color=MUTED, fontsize=8)
    finish(fig)
    save(fig, 'fig02_position_time')


# ============================================================
# Fig 3 — Velocity vs time
# ============================================================
def fig3():
    fig, axes = plt.subplots(2, 1, figsize=(W, H2), sharex=True)
    fig.subplots_adjust(hspace=0.14)
    data = [(vx, '$v_x$ (m/s)', COLORS[0]), (vz, '$v_z$ (m/s)', COLORS[2])]
    for i, (ax, (d, label, c)) in enumerate(zip(axes, data)):
        ax.plot(time, d, color=c, linewidth=1.7)
        ax.set_ylabel(label)
        ax.axhline(y=0, color=MUTED, linewidth=0.65, linestyle=':')
        grid(ax)
        if i < 1:
            ax.tick_params(labelbottom=False)
    axes[-1].set_xlabel('Time (s)')
    axes[0].text(0.98, 0.10, r'$v_y(t)=0$ (symmetric boundary)', transform=axes[0].transAxes,
                 ha='right', va='bottom', color=MUTED, fontsize=8)
    finish(fig)
    save(fig, 'fig03_velocity_time')


# ============================================================
# Fig 4 — Mass evolution
# ============================================================
def fig4():
    fig, ax = plt.subplots(figsize=(W, H))
    ax.plot(time, mass, color=COLORS[5], linewidth=1.8)
    ax.fill_between(time, mass, mass[-1], color=COLORS[5], alpha=0.08)
    ax.axhline(y=mass[-1], color=MUTED, linestyle=':', linewidth=1.0,
               label=f'Terminal: {mass[-1]:.1f} kg')
    ax.axhline(y=mass[0], color=MUTED, linestyle=':', linewidth=1.0,
               label=f'Initial: {mass[0]:.1f} kg')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Mass (kg)')
    ax.legend(loc='lower left')
    grid(ax)
    finish(fig)
    save(fig, 'fig04_mass_evolution')


# ============================================================
# Fig 5 — Thrust: ‖u‖ vs σ
# ============================================================
def fig5():
    fig, ax = plt.subplots(figsize=(W, H))
    control_time = time[:-1]
    ax.plot(control_time, u_norm[:-1], color=COLORS[0], linewidth=1.8, label=r'$\|\mathbf{u}\|$')
    ax.plot(control_time, sigma[:-1], color=COLORS[3], linewidth=1.5, linestyle='--', dashes=(5, 3),
            label=r'$\sigma$')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Thrust acceleration (N/kg)')
    ax.legend()
    grid(ax)
    finish(fig)
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
    ax.plot(time, lhs, color=COLORS[2], linewidth=1.7,
            label=r'$\|[r_y,r_z]\|$')
    ax.plot(time, rhs, color=COLORS[3], linewidth=1.5, linestyle='--', dashes=(5, 3),
            label=r'$r_x\tan\theta$')
    ax.set_ylabel('Distance (m)')
    ax.legend(loc='upper left')
    grid(ax)
    ax.tick_params(labelbottom=False)

    ax = axes[1]
    ax.fill_between(time, 0, margin, color=COLORS[4], alpha=0.13)
    ax.plot(time, margin, color=COLORS[4], linewidth=1.45)
    ax.axhline(y=0, color=MUTED, linewidth=0.65)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Margin (m)')
    grid(ax)

    finish(fig)
    save(fig, 'fig06_glide_slope')


# ============================================================
# Fig 7 — Thrust cone constraint
# ============================================================
def fig7():
    # The N control intervals are k=0,...,N-1.  The terminal node stores
    # decision variables for uniform layout but does not apply a control.
    control_time = time[:-1]
    control_norm = u_norm[:-1]
    control_sigma = sigma[:-1]
    residual = control_sigma - control_norm

    fig, axes = plt.subplots(2, 1, figsize=(W, H2), sharex=True)
    fig.subplots_adjust(hspace=0.12)

    ax = axes[0]
    ax.plot(control_time, control_norm, color=COLORS[0], linewidth=1.7, label=r'$\|\mathbf{u}\|$')
    ax.plot(control_time, control_sigma, color=COLORS[3], linewidth=1.5, linestyle='--', dashes=(5, 3),
            label=r'$\sigma$')
    ax.set_ylabel('Thrust (N/kg)')
    ax.legend()
    grid(ax)
    ax.tick_params(labelbottom=False)

    ax = axes[1]
    ax.fill_between(control_time, 0, residual, color=COLORS[5], alpha=0.13)
    ax.plot(control_time, residual, color=COLORS[5], linewidth=1.35)
    ax.axhline(y=0, color=MUTED, linewidth=0.65)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Numerical residual (N/kg)')
    ax.ticklabel_format(axis='y', style='sci', scilimits=(-2, 2))
    grid(ax)

    finish(fig)
    save(fig, 'fig07_thrust_cone')


# ============================================================
# Fig 8 — Fuel consumption bar chart
# ============================================================
def fig8():
    names = [s['solver'].replace('+','+\n') for s in solvers]
    fuels = [s['fuel_kg'] for s in solvers]

    fig, ax = plt.subplots(figsize=(W, H))
    x = np.arange(len(names))
    ax.hlines(400.7, -0.45, len(names) - 0.55, color=MUTED, linestyle='--', linewidth=1.0,
              label='Reference 400.7 kg')
    ax.scatter(x, fuels, s=58, color=[COLORS[0], COLORS[1], COLORS[2]],
               edgecolor='white', linewidth=1.0, zorder=3)
    ax.set_ylabel('Fuel consumption (kg)')
    ax.set_ylim(400.25, 401.15)
    for xi, val in zip(x, fuels):
        ax.text(xi, val + 0.08, f'{val:.1f}', ha='center', va='bottom', fontsize=9,
                color=TEXT, weight='semibold')
    ax.set_xticks(x)
    ax.set_xticklabels(names)
    grid(ax)
    ax.legend(loc='upper right')
    finish(fig)
    save(fig, 'fig08_fuel_comparison')


# ============================================================
# Fig 9 — Solve time bar chart
# ============================================================
def fig9():
    names = [s['solver'].replace('+','+\n') for s in solvers]
    times_ms = [s['time_ms'] for s in solvers]

    fig, ax = plt.subplots(figsize=(W, H))
    bars = ax.bar(range(len(names)), times_ms, color=[COLORS[0], COLORS[1], COLORS[2]],
                  width=0.55, edgecolor='white', linewidth=0.6, zorder=3)
    ax.set_ylabel('Solve time (ms)')
    ax.set_yscale('log')
    for bar, val in zip(bars, times_ms):
        lbl = f'{val:.0f}' if val < 1000 else f'{val/1000:.2f}s'
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 1.15,
                lbl, ha='center', va='bottom', fontsize=8, weight='semibold')
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names)
    grid(ax)
    finish(fig)
    save(fig, 'fig09_time_comparison')


# ============================================================
# Fig 10 — Control components (ux, uy, uz)
# ============================================================
def fig10():
    fig, axes = plt.subplots(2, 1, figsize=(W, H2), sharex=True)
    fig.subplots_adjust(hspace=0.14)
    data = [(ux, '$u_x$ (N/kg)', COLORS[0]), (uz, '$u_z$ (N/kg)', COLORS[2])]
    for i, (ax, (d, label, c)) in enumerate(zip(axes, data)):
        ax.plot(time, d, color=c, linewidth=1.7)
        ax.set_ylabel(label)
        ax.axhline(y=0, color=MUTED, linewidth=0.65, linestyle=':')
        grid(ax)
        if i < 1:
            ax.tick_params(labelbottom=False)
    axes[-1].set_xlabel('Time (s)')
    axes[0].text(0.98, 0.10, r'$u_y(t)=0$ (symmetric boundary)', transform=axes[0].transAxes,
                 ha='right', va='bottom', color=MUTED, fontsize=8)
    finish(fig)
    save(fig, 'fig10_control_time')


# ============================================================
if __name__ == '__main__':
    print(f'Trajectory: N={N}, dt={dt:.1f}s, tf={tf:.0f}s, fuel={traj["fuel"]:.1f}kg')
    print(f'Mass: {mass[0]:.1f} → {mass[-1]:.1f} kg\n')
    fig1(); fig2(); fig3(); fig4(); fig5()
    fig6(); fig7(); fig8(); fig9(); fig10()
    print('\nDone — 10 figures.')
