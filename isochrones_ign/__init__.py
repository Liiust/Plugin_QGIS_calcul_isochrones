"""
'IGN Isochrones' QGIS plugin (using the Géoplateforme isochrone calculation service).

This file must not import QGIS or PyQt at the module level, so that it remains importable (and testable) outside of QGIS.
"""

# Liiust


def classFactory(iface):  # noqa: N802 (name imposed by QGIS)
    from .main import IsochronePlugin

    return IsochronePlugin(iface)
