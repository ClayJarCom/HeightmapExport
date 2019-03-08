"""
Export a heightmap from a raster layer to a PNG.

Heightmap Export, a QGIS plugin by Nathaniel Klumb

This plugin was created to make it easy to take a raster layer, such as
clipped USGS DEM data, and export it to a 16-bit PNG image to load into
CAM software to create terrain relief models using CNC.

This script initializes the plugin, making it known to QGIS.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

"""


def classFactory(iface):
    """Load HeightmapExport class from file HeightmapExport.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    #
    from .heightmapexport import HeightmapExport
    return HeightmapExport(iface)
