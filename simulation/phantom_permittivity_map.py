"""
2D dielectric phantom with known relative permittivity map.

Models a 2D cross-section (cross-range x, down-range z) with:
- Homogeneous background medium (epsilon_r_bg, typically 1.0 for air)
- Circular dielectric inclusions with higher or different epsilon_r

Converts dielectric contrast to equivalent point-target reflectivities
using the Fresnel normal-incidence reflection coefficient:
  Gamma = (sqrt(eps_bg) - sqrt(eps_incl)) / (sqrt(eps_bg) + sqrt(eps_incl))

Scientific limitations
----------------------
- Free-space, non-dispersive scalar model only.
- Does NOT account for: frequency-dependent permittivity (Cole-Cole for tissue),
  multiple scattering, wave propagation inside inclusions, lossy media
  (imaginary epsilon), or near-field effects.
- Point-target approximation: each inclusion is a single scatterer at its center
  with Fresnel amplitude. Extended-body effects are not modeled.
- Result: qualitative demonstration of dielectric-contrast localization via SAR.
  NOT a validated dielectric measurement method.
  NOT suitable for medical/biological claims.

Hardware-independent. No bladeRF import. No motors. Safe to run offline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


__all__ = [
    "DielectricInclusion",
    "DielectricPhantom",
    "make_two_inclusion_phantom",
]


@dataclass
class DielectricInclusion:
    """
    Circular dielectric inclusion in a 2D phantom cross-section.

    Attributes
    ----------
    x_m       : Center cross-range position [m].
    z_m       : Center down-range (depth) position [m]. Must be > 0.
    radius_m  : Circle radius [m]. Must be > 0.
    epsilon_r : Relative permittivity. Must be >= 1.0.
    label     : Human-readable label for figures and reports.
    """
    x_m: float
    z_m: float
    radius_m: float
    epsilon_r: float
    label: str = ""

    def __post_init__(self) -> None:
        if self.epsilon_r < 1.0:
            raise ValueError(
                f"epsilon_r must be >= 1.0 (non-magnetic, passive medium), got {self.epsilon_r}"
            )
        if self.radius_m <= 0.0:
            raise ValueError(f"radius_m must be > 0, got {self.radius_m}")
        if self.z_m <= 0.0:
            raise ValueError(f"z_m must be > 0 (below aperture), got {self.z_m}")


@dataclass
class DielectricPhantom:
    """
    2D dielectric phantom: homogeneous background + circular inclusions.

    Cross-range x is horizontal (aperture axis).
    Down-range z is vertical (depth). Aperture is at z = 0.

    Attributes
    ----------
    x_min_m       : Left cross-range boundary [m].
    x_max_m       : Right cross-range boundary [m].
    z_min_m       : Near (minimum depth) boundary [m]. Should be > 0.
    z_max_m       : Far (maximum depth) boundary [m].
    n_x           : Grid resolution in cross-range.
    n_z           : Grid resolution in down-range.
    epsilon_r_bg  : Background relative permittivity (default 1.0, air).
    inclusions    : List of DielectricInclusion objects.
    """
    x_min_m: float
    x_max_m: float
    z_min_m: float
    z_max_m: float
    n_x: int = 200
    n_z: int = 200
    epsilon_r_bg: float = 1.0
    inclusions: list[DielectricInclusion] = field(default_factory=list)

    @property
    def x_grid(self) -> np.ndarray:
        """Cross-range axis [m], shape (n_x,)."""
        return np.linspace(self.x_min_m, self.x_max_m, self.n_x)

    @property
    def z_grid(self) -> np.ndarray:
        """Down-range axis [m], shape (n_z,)."""
        return np.linspace(self.z_min_m, self.z_max_m, self.n_z)

    def permittivity_grid(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Build the 2D relative permittivity map.

        Inclusions are painted onto the background grid using circular masks.
        Overlapping inclusions: last inclusion wins.

        Returns
        -------
        x_grid  : float array (n_x,). Cross-range axis [m].
        z_grid  : float array (n_z,). Down-range axis [m].
        eps_map : float array (n_x, n_z). Relative permittivity at each pixel.
        """
        x = self.x_grid
        z = self.z_grid
        XX, ZZ = np.meshgrid(x, z, indexing="ij")  # (n_x, n_z)
        eps_map = np.full((self.n_x, self.n_z), self.epsilon_r_bg, dtype=float)
        for incl in self.inclusions:
            r2 = (XX - incl.x_m) ** 2 + (ZZ - incl.z_m) ** 2
            eps_map[r2 <= incl.radius_m ** 2] = incl.epsilon_r
        return x, z, eps_map

    @staticmethod
    def fresnel_reflectivity(eps_r1: float, eps_r2: float) -> complex:
        """
        Fresnel normal-incidence reflection coefficient from medium 1 to medium 2.

        Assumes real-valued, non-magnetic (mu_r = 1) media.

        Gamma = (sqrt(eps_r1) - sqrt(eps_r2)) / (sqrt(eps_r1) + sqrt(eps_r2))

        Parameters
        ----------
        eps_r1 : float. Relative permittivity of incident medium.
        eps_r2 : float. Relative permittivity of transmitted medium.

        Returns
        -------
        gamma : complex. Reflection coefficient. |gamma| in [0, 1).
        """
        n1 = np.sqrt(complex(eps_r1))
        n2 = np.sqrt(complex(eps_r2))
        denom = n1 + n2
        if abs(denom) < 1e-15:
            return 0.0 + 0j
        return complex((n1 - n2) / denom)

    def to_point_targets(self) -> list:
        """
        Convert phantom inclusions to SAR simulator PointTarget instances.

        Each inclusion becomes one point target at its center with complex
        reflectivity = Fresnel coefficient at the bg/inclusion interface.

        This is a point-scatterer approximation. Extended-body diffraction
        and internal resonances are not modeled.

        Returns
        -------
        targets : list of PointTarget (from simulation.ofdm_uwb_sar_simulator).
        """
        from simulation.ofdm_uwb_sar_simulator import PointTarget
        targets = []
        for incl in self.inclusions:
            gamma = self.fresnel_reflectivity(self.epsilon_r_bg, incl.epsilon_r)
            targets.append(
                PointTarget(x_m=incl.x_m, z_m=incl.z_m, reflectivity=gamma)
            )
        return targets

    def reflectivity_map(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Build the 2D Fresnel reflectivity magnitude map.

        Used as ground-truth reference for comparison with the SAR image.
        The map is normalized to [0, 1] by its maximum value.

        Returns
        -------
        x_grid  : float array (n_x,).
        z_grid  : float array (n_z,).
        refl    : float array (n_x, n_z). Normalized |Gamma| in [0, 1].
        """
        x, z, eps_map = self.permittivity_grid()
        # Vectorized Fresnel |gamma| over every pixel
        n1 = np.sqrt(self.epsilon_r_bg)
        n2 = np.sqrt(np.maximum(eps_map, 1e-9))
        gamma_mag = np.abs((n1 - n2) / (n1 + n2))
        peak = float(np.max(gamma_mag))
        if peak < 1e-15:
            return x, z, gamma_mag
        return x, z, gamma_mag / peak

    def contrast_map(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Build a 2D relative contrast map: (eps(x,z) - eps_bg) / max_contrast.

        Returns
        -------
        x_grid   : float array (n_x,).
        z_grid   : float array (n_z,).
        contrast : float array (n_x, n_z). Normalized contrast in [0, 1].
        """
        x, z, eps_map = self.permittivity_grid()
        delta = np.abs(eps_map - self.epsilon_r_bg)
        peak = float(np.max(delta))
        if peak < 1e-15:
            return x, z, np.zeros_like(delta)
        return x, z, delta / peak


def make_two_inclusion_phantom(
    eps_r_bg: float = 1.0,
    eps_r_a: float = 3.5,
    eps_r_b: float = 9.0,
) -> "DielectricPhantom":
    """
    Build the standard Phase-5 two-inclusion phantom.

    Phantom layout (aperture at z=0):
      - Background: air (eps_r = 1.0)
      - Inclusion A (plastic-like): center (-0.15 m, 0.50 m), r=0.08 m
      - Inclusion B (high-contrast):  center (+0.25 m, 0.85 m), r=0.06 m

    Parameters
    ----------
    eps_r_bg : float. Background permittivity (default 1.0).
    eps_r_a  : float. Inclusion A permittivity (default 3.5, plastic-like).
    eps_r_b  : float. Inclusion B permittivity (default 9.0, high-contrast).

    Returns
    -------
    phantom : DielectricPhantom.
    """
    return DielectricPhantom(
        x_min_m=-0.75,
        x_max_m=0.75,
        z_min_m=0.05,
        z_max_m=1.55,
        n_x=200,
        n_z=200,
        epsilon_r_bg=eps_r_bg,
        inclusions=[
            DielectricInclusion(
                x_m=-0.15, z_m=0.50, radius_m=0.08,
                epsilon_r=eps_r_a, label="A_plastic_proxy",
            ),
            DielectricInclusion(
                x_m=0.25, z_m=0.85, radius_m=0.06,
                epsilon_r=eps_r_b, label="B_high_contrast",
            ),
        ],
    )
