#!/usr/bin/env python3
"""
Generate all 10 figures for the Mars landing trajectory optimization paper.
Reads data from paper/data/trajectory.json and paper/data/solver_comparison.json.
Saves PDF (vector) + PNG (300 dpi) to paper/figures/.
"""

import json
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import rcParams

# ============================================================
# Paths
# ============================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
DATA_DIR = os.path.join(PROJECT_DIR, 'paper', 'data')
FIG_DIR = SCRIPT_DIR

# Load data
with open(os.path.join(DATA_DIR, 'trajectory.json'), 'r') as f:
    traj = json.load(f)

with open(os.path.join(DATA_DIR, 'solver_comparison.json'), 'r') as f:
    solvers = json.load(f)

N = traj['N']
dt = traj['dt']
tf = traj['tf']
g_mars = traj['g_mars']
theta = 86.0  # deg, from project docs

# Extract arrays
time = np.array(traj['time'])
rx = np.array(traj['rx'])
ry = np.array(traj['ry'])
rz = np.array(traj['rz'])
vx = np.array(traj['vx'])
vy = np.array(traj['vy'])
vz = np.array(traj['vz'])
mass = np.array(traj['mass'])
ux = np.array(traj['ux'])
uy = np.array(traj['uy'])
uz = np.array(traj['uz'])
sigma = np.array(traj['sigma'])
thrust_norm = np.array(traj['thrust_norm'])
glide_margin = np.array(traj['glide_margin'])

# Compute derived quantities
u_norm = np.sqrt(ux**2 + uy**2 + uz**2)

# ============================================================
# Matplotlib style
# ============================================================
# Use Liberation Serif (metrically identical to Times New Roman, per AGENTS.md §学术风格)
FAMILY = 'Liberation Serif'

rcParams.update({
    'font.family': 'serif',
    'font.serif': [FAMILY],
    'font.size': 10,
    'axes.labelsize': 12,
    'axes.titlesize': 14,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
    'lines.linewidth': 1.5,
    'axes.linewidth': 1.0,
    'grid.alpha': 0.3,
    'grid.linestyle': '--',
    'pdf.fonttype': 42,         # Ensure editable text in PDF
    'ps.fonttype': 42,
    'text.usetex': False,
})

# Color palette
COLORS = plt.get_cmap('tab10').colors

SINGLE_W = 3.5   # single-column width (inch)
SINGLE_H = 2.5
DOUBLE_W = 7.0   # double-column width
DOUBLE_H = 3.0


def save_fig(fig, name):
    """Save figure as PDF + PNG to FIG_DIR."""
    pdf_path = os.path.join(FIG_DIR, f'{name}.pdf')
    png_path = os.path.join(FIG_DIR, f'{name}.png')
    fig.savefig(pdf_path, bbox_inches='tight', pad_inches=0.05)
    fig.savefig(png_path, dpi=300, bbox_inches='tight', pad_inches=0.05)
    print(f'  Saved: {name}.pdf  +  {name}.png')
    plt.close(fig)


def add_grid(ax):
    """Add subdued grid."""
    ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)


# ============================================================
# Fig 1: 3D landing trajectory (rx, ry, rz) — double-column
# ============================================================
def fig1_3d_trajectory():
    print('[Fig 1] 3D landing trajectory')
    fig = plt.figure(figsize=(DOUBLE_W, DOUBLE_H))
    ax = fig.add_subplot(111, projection='3d')
    ax.plot(rx, ry, rz, color=COLORS[0], linewidth=1.5, label='Trajectory')
    ax.scatter([rx[0]], [ry[0]], [rz[0]], color=COLORS[2], s=40, marker='o',
               label='Start', zorder=5)
    ax.scatter([rx[-1]], [ry[-1]], [rz[-1]], color=COLORS[3], s=40, marker='s',
               label='Landing', zorder=5)

    ax.set_xlabel('$r_x$ (m)')
    ax.set_ylabel('$r_y$ (m)')
    ax.set_zlabel('$r_z$ (m)')
    ax.set_title('3D landing trajectory')
    ax.legend(loc='upper right', fontsize=9)
    add_grid(ax)
    # Equal aspect for 3D
    max_range = max(rx.max() - rx.min(), rz.max() - rz.min()) / 2
    mid_x = (rx.max() + rx.min()) / 2
    mid_z = (rz.max() + rz.min()) / 2
    ax.set_xlim(mid_x - max_range, mid_x + max_range)
    ax.set_ylim(-max_range, max_range)
    ax.set_zlim(mid_z - max_range, mid_z + max_range)
    save_fig(fig, 'fig01_3d_trajectory')


# ============================================================
# Fig 2: Position components vs time (3 subplots: rx, ry, rz)
# ============================================================
def fig2_position_vs_time():
    print('[Fig 2] Position components vs time')
    fig, axes = plt.subplots(3, 1, figsize=(SINGLE_W, SINGLE_H * 2.8),
                             sharex=True)
    labels = ['$r_x$ (m)', '$r_y$ (m)', '$r_z$ (m)']
    data = [rx, ry, rz]
    for i, ax in enumerate(axes):
        ax.plot(time, data[i], color=COLORS[i], linewidth=1.5)
        ax.set_ylabel(labels[i])
        add_grid(ax)
        if i < 2:
            ax.tick_params(labelbottom=False)
        else:
            ax.set_xlabel('Time (s)')
    axes[0].set_title('Position vs time')
    fig.tight_layout()
    save_fig(fig, 'fig02_position_time')


# ============================================================
# Fig 3: Velocity components vs time (3 subplots: vx, vy, vz)
# ============================================================
def fig3_velocity_vs_time():
    print('[Fig 3] Velocity components vs time')
    fig, axes = plt.subplots(3, 1, figsize=(SINGLE_W, SINGLE_H * 2.8),
                             sharex=True)
    labels = ['$v_x$ (m/s)', '$v_y$ (m/s)', '$v_z$ (m/s)']
    data = [vx, vy, vz]
    for i, ax in enumerate(axes):
        ax.plot(time, data[i], color=COLORS[i], linewidth=1.5)
        ax.set_ylabel(labels[i])
        add_grid(ax)
        if i < 2:
            ax.tick_params(labelbottom=False)
        else:
            ax.set_xlabel('Time (s)')
    axes[0].set_title('Velocity vs time')
    fig.tight_layout()
    save_fig(fig, 'fig03_velocity_time')


# ============================================================
# Fig 4: Mass evolution m(t) — 1905 → ~1504 kg
# ============================================================
def fig4_mass_evolution():
    print('[Fig 4] Mass evolution')
    fig, ax = plt.subplots(figsize=(SINGLE_W, SINGLE_H))
    ax.plot(time, mass, color=COLORS[4], linewidth=1.5)
    ax.axhline(y=mass[-1], color='gray', linestyle=':', alpha=0.7,
               label=f'Final: {mass[-1]:.1f} kg')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Mass (kg)')
    ax.set_title('Mass evolution')
    ax.legend(fontsize=9)
    add_grid(ax)
    fig.tight_layout()
    save_fig(fig, 'fig04_mass_evolution')


# ============================================================
# Fig 5: Thrust magnitude comparison — ||u|| and σ on same plot
# ============================================================
def fig5_thrust_comparison():
    print('[Fig 5] Thrust magnitude comparison')
    fig, ax = plt.subplots(figsize=(SINGLE_W, SINGLE_H))
    ax.plot(time, u_norm, color=COLORS[0], linewidth=1.5,
            label=r'$\|\mathbf{u}\|$ (thrust magnitude)')
    ax.plot(time, sigma, color=COLORS[1], linewidth=1.5, linestyle='--',
            label=r'$\sigma$ (slack variable)')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Thrust (N/kg)')
    ax.set_title('Thrust magnitude comparison')
    ax.legend(fontsize=8)
    add_grid(ax)
    fig.tight_layout()
    save_fig(fig, 'fig05_thrust_comparison')


# ============================================================
# Fig 6: Glide slope constraint verification
#   compare ||[ry, rz]|| vs rx * tan(theta)
# ============================================================
def fig6_glide_slope():
    print('[Fig 6] Glide slope constraint verification')
    theta_rad = np.radians(theta)
    lhs = np.sqrt(ry**2 + rz**2)
    rhs = rx * np.tan(theta_rad)
    # Margin: rhs - lhs (should be >= 0)
    margin = rhs - lhs

    fig, axes = plt.subplots(2, 1, figsize=(SINGLE_W, SINGLE_H * 2.2),
                             sharex=True)

    ax = axes[0]
    ax.plot(time, lhs, color=COLORS[2], linewidth=1.5,
            label=r'$\|[r_y, r_z]\|$')
    ax.plot(time, rhs, color=COLORS[3], linewidth=1.5, linestyle='--',
            label=r'$r_x \cdot \tan\theta$')
    ax.set_ylabel('Distance (m)')
    ax.set_title('Glide slope constraint')
    ax.legend(fontsize=8)
    add_grid(ax)
    ax.tick_params(labelbottom=False)

    ax = axes[1]
    ax.fill_between(time, 0, margin, color=COLORS[4], alpha=0.3)
    ax.plot(time, margin, color=COLORS[4], linewidth=1.0)
    ax.axhline(y=0, color='k', linewidth=0.5)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Margin (m)')
    add_grid(ax)

    fig.tight_layout()
    save_fig(fig, 'fig06_glide_slope')


# ============================================================
# Fig 7: Thrust cone constraint verification — ||u|| vs σ
# ============================================================
def fig7_thrust_cone():
    print('[Fig 7] Thrust cone constraint verification')
    margin = sigma - u_norm  # should be >= 0

    fig, axes = plt.subplots(2, 1, figsize=(SINGLE_W, SINGLE_H * 2.2),
                             sharex=True)

    ax = axes[0]
    ax.plot(time, u_norm, color=COLORS[0], linewidth=1.5,
            label=r'$\|\mathbf{u}\|$')
    ax.plot(time, sigma, color=COLORS[1], linewidth=1.5, linestyle='--',
            label=r'$\sigma$')
    ax.set_ylabel('Thrust (N/kg)')
    ax.set_title('Thrust cone constraint')
    ax.legend(fontsize=8)
    add_grid(ax)
    ax.tick_params(labelbottom=False)

    ax = axes[1]
    ax.fill_between(time, 0, margin, color=COLORS[5], alpha=0.3)
    ax.plot(time, margin, color=COLORS[5], linewidth=1.0)
    ax.axhline(y=0, color='k', linewidth=0.5)
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Margin (N/kg)')
    add_grid(ax)

    fig.tight_layout()
    save_fig(fig, 'fig07_thrust_cone')


# ============================================================
# Fig 8: Fuel consumption comparison (bar chart)
# ============================================================
def fig8_fuel_comparison():
    print('[Fig 8] Fuel consumption comparison')
    names = [s['solver'] for s in solvers]
    fuels = [s['fuel_kg'] for s in solvers]
    colors = [COLORS[0], COLORS[1], COLORS[2]]

    fig, ax = plt.subplots(figsize=(SINGLE_W, SINGLE_H))
    bars = ax.bar(names, fuels, color=colors, width=0.5, edgecolor='gray',
                  linewidth=0.5)
    ax.set_ylabel('Fuel consumption (kg)')
    ax.set_title('Fuel consumption comparison')
    ax.set_ylim(0, max(fuels) * 1.25)
    # Add value labels on bars
    for bar, val in zip(bars, fuels):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                f'{val:.1f}', ha='center', va='bottom', fontsize=9)
    add_grid(ax)
    # Rotate x labels if needed
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=15, ha='right', fontsize=8)
    fig.tight_layout()
    save_fig(fig, 'fig08_fuel_comparison')


# ============================================================
# Fig 9: Solve time comparison (bar chart)
# ============================================================
def fig9_time_comparison():
    print('[Fig 9] Solve time comparison')
    names = [s['solver'] for s in solvers]
    times_ms = [s['time_ms'] for s in solvers]
    colors = [COLORS[0], COLORS[1], COLORS[2]]

    fig, ax = plt.subplots(figsize=(SINGLE_W, SINGLE_H))
    bars = ax.bar(names, times_ms, color=colors, width=0.5,
                  edgecolor='gray', linewidth=0.5)
    ax.set_ylabel('Solve time (ms)')
    ax.set_title('Solve time comparison')
    # Add value labels
    for bar, val in zip(bars, times_ms):
        label = f'{val:.1f}' if val < 1000 else f'{val / 1000:.2f}s'
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(times_ms) * 0.02,
                label, ha='center', va='bottom', fontsize=9)
    add_grid(ax)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=15, ha='right', fontsize=8)
    fig.tight_layout()
    save_fig(fig, 'fig09_time_comparison')


# ============================================================
# Fig 10: Control components vs time (ux, uy, uz, 3 subplots)
# ============================================================
def fig10_control_time():
    print('[Fig 10] Control components vs time')
    fig, axes = plt.subplots(3, 1, figsize=(SINGLE_W, SINGLE_H * 2.8),
                             sharex=True)
    labels = ['$u_x$ (N/kg)', '$u_y$ (N/kg)', '$u_z$ (N/kg)']
    data = [ux, uy, uz]
    colors_c = [COLORS[0], COLORS[1], COLORS[2]]
    for i, ax in enumerate(axes):
        ax.plot(time, data[i], color=colors_c[i], linewidth=1.5)
        ax.axhline(y=0, color='gray', linewidth=0.5, linestyle=':')
        ax.set_ylabel(labels[i])
        add_grid(ax)
        if i < 2:
            ax.tick_params(labelbottom=False)
        else:
            ax.set_xlabel('Time (s)')
    axes[0].set_title('Control components vs time')
    fig.tight_layout()
    save_fig(fig, 'fig10_control_time')


# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    os.makedirs(FIG_DIR, exist_ok=True)
    print(f'Data:  {DATA_DIR}')
    print(f'Figs:  {FIG_DIR}')
    print(f'Font:  {FAMILY}')
    print(f'N={N}, dt={dt}, tf={tf}')
    print(f'Mass: {mass[0]:.1f} → {mass[-1]:.1f} kg, fuel={traj["fuel"]:.1f} kg')
    print()

    # Generate all 10 figures
    fig1_3d_trajectory()
    fig2_position_vs_time()
    fig3_velocity_vs_time()
    fig4_mass_evolution()
    fig5_thrust_comparison()
    fig6_glide_slope()
    fig7_thrust_cone()
    fig8_fuel_comparison()
    fig9_time_comparison()
    fig10_control_time()

    print()
    print('All 10 figures generated successfully.')
