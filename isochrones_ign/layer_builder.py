"""
Creation of the QGIS layer (a module that imports QGIS, using dialog.py and main.py)
"""

# Liiust

from __future__ import annotations

from typing import Any, Dict, Optional

from qgis.core import QgsCoordinateReferenceSystem, QgsFillSymbol, QgsProject, QgsVectorLayer

from .geo import write_geojson


def add_isochrone_layer(
    feature_collection: Dict[str, Any],
    name: str,
    crs: str = "EPSG:4326",
    project: Optional[QgsProject] = None,
) -> QgsVectorLayer:
    """Writes the FeatureCollection to a temporary .geojson file, loads it, and adds it to the project."""
    path = write_geojson(feature_collection, name)
    layer = QgsVectorLayer(path, name, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"QGIS could not read the GeoJSON result ({path}).")
    layer.setCrs(QgsCoordinateReferenceSystem(crs))
    layer.renderer().setSymbol(
        QgsFillSymbol.createSimple(
            {"color": "255,140,0,90", "outline_color": "200,90,0,255", "outline_width": "0.6"}
        )
    )
    (project or QgsProject.instance()).addMapLayer(layer)
    return layer
