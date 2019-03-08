"""
Export a heightmap from a raster layer to a PNG.

Heightmap Export, a QGIS plugin by Nathaniel Klumb

This plugin was created to make it easy to take a raster layer, such as 
clipped USGS DEM data, and export it to a 16-bit PNG image to load into
CAM software to create terrain relief models using CNC.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

"""
from __future__ import absolute_import
from builtins import object
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from . import resources_rc
from .heightmapexport_dialog import HeightmapExportDialog

class HeightmapExport(object):
    """Implement a QGIS Plugin."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
                which provides the hook by which you can manipulate the QGIS
                application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface

        # Declare instance attributes
        self.action = None
        self.menu = '&Heightmap Export'
        self.window = True

    def initGui(self):
        """Create the menu entries and a toolbar icon in the QGIS GUI."""
        icon = QIcon(":/plugins/HeightmapExport/HeightmapExport.png")
        parent = self.iface.mainWindow()
        self.action = QAction(icon, "Heightmap Export", parent)
        self.action.setObjectName("Heightmap Export")
        self.action.setStatusTip("Export 16-bit PNG heightmaps")
        self.action.triggered.connect(self.run)

        self.iface.addPluginToRasterMenu(self.menu, self.action)
        self.iface.addRasterToolBarIcon(self.action)

    def unload(self):
        """Remove the plugin menu entry and icon from QGIS GUI."""
        self.iface.removePluginRasterMenu(self.menu, self.action)
        self.iface.removeRasterToolBarIcon(self.action)

    def run(self):
        """Run the plugin."""
        hmexport = HeightmapExportDialog(self.iface)
        hmexport.exec_()
        if hmexport.extent:
            self.iface.mapCanvas().scene().removeItem(hmexport.extent)
