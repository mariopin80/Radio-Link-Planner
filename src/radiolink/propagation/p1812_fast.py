"""Vectorized Py1812 6.1 routines; equations unchanged.

Derived from eeveetza/Py1812, revision a5205e6a65db27391a8ba79bd5a365e5391f9fdf.
Modified 2026-10-16: NumPy maximum reductions and basic array slices.
See vendor/Py1812-NOTICE.txt for attribution and the upstream license.
Static functions also work in a frozen application; no runtime source rewriting.
"""
from __future__ import annotations

from types import FunctionType, ModuleType

OPTIMIZATION_VERSION = "numpy-1"


def optimize_p1812(module: ModuleType) -> ModuleType:
    """Install tested replacements for the pinned upstream release, once."""
    import Py1812

    if getattr(Py1812, "__version__", None) != "6.1":
        return module
    if getattr(module, "_radiolink_optimization", None) == OPTIMIZATION_VERSION:
        return module
    for implementation in (_smooth_earth_heights, _dl_bull, _find_intervals):
        name = implementation.__name__[1:]
        replacement = FunctionType(implementation.__code__, module.__dict__, name)
        replacement.__doc__ = getattr(module, name).__doc__
        setattr(module, name, replacement)
    module._radiolink_optimization = OPTIMIZATION_VERSION
    return module


def _smooth_earth_heights(d, h, R, htg, hrg, ae, f):
    n = len(d)
    dtot = d[-1]
    hts = h[0] + htg
    hrs = h[-1] + hrg
    g = h + R
    g[0] = h[0]
    g[-1] = h[-1]
    htc = hts
    hrc = hrs
    ii = np.arange(1, n)
    v1 = ((d[ii] - d[ii - 1]) * (h[ii] + h[ii - 1])).sum()
    v2 = ((d[ii] - d[ii - 1]) * (h[ii] * (2 * d[ii] + d[ii - 1]) + h[ii - 1] * (d[ii] + 2 * d[ii - 1]))).sum()
    hst = (2 * v1 * dtot - v2) / dtot ** 2
    hsr = (v2 - v1 * dtot) / dtot ** 2
    hst_n = hst
    hsr_n = hsr
    HH = h - (htc * (dtot - d) + hrc * d) / dtot
    hobs = np.max(HH[1:-1])
    alpha_obt = np.max(HH[1:-1] / d[1:-1])
    alpha_obr = np.max(HH[1:-1] / (dtot - d[1:-1]))
    gt = alpha_obt / (alpha_obt + alpha_obr)
    gr = alpha_obr / (alpha_obt + alpha_obr)
    if hobs <= 0:
        hstp = hst
        hsrp = hsr
    else:
        hstp = hst - hobs * gt
        hsrp = hsr - hobs * gr
    if hstp >= h[0]:
        hstd = h[0]
    else:
        hstd = hstp
    if hsrp > h[-1]:
        hsrd = h[-1]
    else:
        hsrd = hsrp
    ii = slice(1, n - 1)
    theta = 1000 * np.arctan((h[ii] - hts) / (1000 * d[ii]) - d[ii] / (2 * ae))
    theta_td = 1000 * np.arctan((hrs - hts) / (1000 * dtot) - dtot / (2 * ae))
    theta_rd = 1000 * np.arctan((hts - hrs) / (1000 * dtot) - dtot / (2 * ae))
    theta_max = np.max(theta)
    if theta_max > theta_td:
        pathtype = 2
    else:
        pathtype = 1
    theta_t = max(theta_max, theta_td)
    if pathtype == 2:
        kindex, = np.where(theta == theta_max)
        lt = kindex[0] + 1
        dlt = d[lt]
        theta = 1000 * np.arctan((h[ii] - hrs) / (1000 * (dtot - d[ii])) - (dtot - d[ii]) / (2 * ae))
        theta_r = np.max(theta)
        kindex, = np.where(theta == theta_r)
        lr = kindex[-1] + 1
        dlr = dtot - d[lr]
    else:
        theta_r = theta_rd
        ii = slice(1, n - 1)
        lam = 0.2998 / f
        Ce = 1.0 / ae
        nu = (h[ii] + 500 * Ce * d[ii] * (dtot - d[ii]) - (hts * (dtot - d[ii]) + hrs * d[ii]) / dtot) * np.sqrt(0.002 * dtot / (lam * d[ii] * (dtot - d[ii])))
        numax = np.max(nu)
        kindex, = np.where(nu == numax)
        lt = kindex[-1] + 1
        dlt = d[lt]
        dlr = dtot - dlt
        lr = lt
    theta_tot = 1000.0 * dtot / ae + theta_t + theta_r
    hst = min(hst, h[0])
    hsr = min(hsr, h[-1])
    m = (hsr - hst) / dtot
    hte = htg + h[0] - hst
    hre = hrg + h[-1] - hsr
    ii = slice(lt, lr + 1)
    hm = np.max(h[ii] - (hst + m * d[ii]))
    return (hst_n, hsr_n, hst, hsr, hstd, hsrd, hte, hre, hm, dlt, dlr, theta_t, theta_r, theta_tot, pathtype)

def _find_intervals(series):
    k1 = []
    k2 = []
    series_int = 1 * series
    if np.max(series_int) == 1:
        k1, = np.where(np.diff(np.append(0, series_int)) == 1)
        k2, = np.where(np.diff(np.append(series_int, 0)) == -1)
    return (k1, k2)

def _dl_bull(d, g, hts, hrs, ap, f):
    Ce = 1.0 / ap
    lam = 0.2998 / f
    dtot = d[-1] - d[0]
    di = d[1:-1]
    gi = g[1:-1]
    Stim = np.max((gi + 500 * Ce * di * (dtot - di) - hts) / di)
    Str = (hrs - hts) / dtot
    if Stim < Str:
        numax = np.max((gi + 500 * Ce * di * (dtot - di) - (hts * (dtot - di) + hrs * di) / dtot) * np.sqrt(0.002 * dtot / (lam * di * (dtot - di))))
        Luc = 0
        if numax > -0.78:
            Luc = 6.9 + 20 * np.log10(np.sqrt((numax - 0.1) ** 2 + 1) + numax - 0.1)
    else:
        Srim = np.max((gi + 500 * Ce * di * (dtot - di) - hrs) / (dtot - di))
        dbp = (hrs - hts + Srim * dtot) / (Stim + Srim)
        nub = (hts + Stim * dbp - (hts * (dtot - dbp) + hrs * dbp) / dtot) * np.sqrt(0.002 * dtot / (lam * dbp * (dtot - dbp)))
        Luc = 0
        if nub > -0.78:
            Luc = 6.9 + 20 * np.log10(np.sqrt((nub - 0.1) ** 2 + 1) + nub - 0.1)
    Lbull = Luc + (1 - np.exp(-Luc / 6.0)) * (10 + 0.02 * dtot)
    return Lbull
