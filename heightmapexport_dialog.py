"""
Show the dialog for the Heightmap Export plugin.

Heightmap Export, a QGIS plugin by Nathaniel Klumb

This plugin was created to make it easy to take a raster layer, such as 
clipped USGS DEM data, and export it to a 16-bit PNG image to load into
CAM software to create terrain relief models using CNC.

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

"""
from os.path import splitext
from configparser import ConfigParser
from builtins import str
from math import sin, cos, atan2, sqrt, radians
from osgeo import gdal

try:
  # If this imports, we're in QGIS 2.
  # It was renamed 'Qgis' in QGIS 3.
  from qgis.core import QGis
  # QGIS 2 imports.
  from PyQt4 import QtCore, QtGui
  from PyQt4.QtGui import (QDialog, QColor, QFileDialog, QApplication,
                           QCursor, QDoubleValidator, QIntValidator)
  from PyQt4.QtCore import Qt, QLocale
  from qgis.gui import (QgsRubberBand, QgsMessageBar, QgsMapLayerComboBox,
                        QgsMapLayerProxyModel)
  from qgis.core import (QgsPoint, QgsProject,QgsRectangle,
                         QgsGeometry, QgsCoordinateTransform,
                         QgsCoordinateReferenceSystem)
  from .heightmapexport_dialog_base_2 import Ui_HeightmapExportDialog
except ImportError:
  # QGIS 3 imports.
  from qgis.PyQt import QtCore, QtGui, QtWidgets
  from qgis.PyQt.QtWidgets import QDialog, QFileDialog, QApplication
  from qgis.PyQt.QtGui import QColor, QCursor, QDoubleValidator, QIntValidator
  from qgis.PyQt.QtCore import Qt, QLocale
  from qgis.gui import (QgsRubberBand, QgsMessageBar, QgsMapLayerComboBox)
  from qgis.core import (QgsPointXY, QgsRectangle, QgsProject,
                         QgsGeometry, QgsCoordinateTransform,
                         QgsCoordinateReferenceSystem, QgsMapLayerProxyModel)
  from .heightmapexport_dialog_base_3 import Ui_HeightmapExportDialog

from .PathTracer import PathTracer,PathTracerGUI


class HeightmapExportDialog(QDialog, Ui_HeightmapExportDialog):
    """Present the export dialog for the Heightmap Export plugin."""
    try:
      QGis.QGIS_VERSION
      QGIS_VERSION = 2
    except:
      QGIS_VERSION = 3  
  
    SIZE_DECIMAL_DIGITS = 3
    SCALE_DECIMAL_DIGITS = 5
    MAXIMUM_ALLOWED_VALUE = 6371000000
    MAXIMUM_IMAGE_SIZE = 2147483647
    EARTH_RADIUS = 6371000

    # extent is where we will keep our dashed line highlighting the layer.
    extent = None    
    # And these keep the dimensions we calculate when a layer is selected.
    height = 0
    width = 0
    zmin = 0
    zmax = 0
    # Keep the filename of the heightmap once exported.
    heightmap = None
    
    def __init__(self, iface):
        """Constructor."""
        QDialog.__init__(self)
        self.ui = Ui_HeightmapExportDialog()
        self.ui.setupUi(self)
        # Add a QgsMessageBar to the dialog so we can use it to
        # tell the user when their export is finished.
        self.messageBar = QgsMessageBar()
        self.ui.MainVLayout.insertWidget(0, self.messageBar)
        # Get the canvas to use for the dashed line highlight.
        self.iface = iface
        self.canvas = iface.mapCanvas()

        # Fill a QgsMapLayerComboBox with the set of raster layers,
        # set the combobox to select the first.  If that results in a
        # layer being selected, call layer_changed to load its details.
        self.ui.LayerComboBox.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.ui.LayerComboBox.setCurrentIndex(0)
        layer = self.ui.LayerComboBox.currentLayer()
        if layer:
            self.layer_changed(layer)
        self.ui.LayerComboBox.layerChanged.connect(self.layer_changed)

        # Set up the model dimension fields to accept cromulent values.
        validDecimals = QDoubleValidator(0.1 ** self.SIZE_DECIMAL_DIGITS,
                                         self.MAXIMUM_ALLOWED_VALUE,
                                         self.SIZE_DECIMAL_DIGITS)
        self.ui.ModelHeight.setValidator(validDecimals)
        self.ui.ModelHeight.textEdited.connect(self.update_from_model_height)
        self.ui.ModelWidth.setValidator(validDecimals)
        self.ui.ModelWidth.textEdited.connect(self.update_from_model_width)
        self.ui.ModelDepth.setValidator(validDecimals)
        self.ui.ModelDepth.textEdited.connect(self.update_from_model_depth)
        self.ui.ScaleDepth.setValidator(validDecimals)
        self.ui.ScaleDepth.textEdited.connect(self.update_from_scale_depth)

        # The scale factors have a different set of cromulent values.
        validScales = QDoubleValidator(0.1 ** self.SCALE_DECIMAL_DIGITS,
                                       self.MAXIMUM_ALLOWED_VALUE,
                                       self.SCALE_DECIMAL_DIGITS)
        self.ui.ScaleFactor.setValidator(validScales)
        self.ui.ScaleFactor.textEdited.connect(self.update_from_scale_factor)
        self.ui.Resolution.setValidator(validScales)
        self.ui.Resolution.textEdited.connect(self.update_from_resolution)

        # And set up the validation for the image height and width as well.
        validIntegers = QIntValidator(1, self.MAXIMUM_IMAGE_SIZE)
        self.ui.ImageHeight.setValidator(validScales)
        self.ui.ImageHeight.textEdited.connect(self.update_from_image_height)
        self.ui.ImageWidth.setValidator(validScales)
        self.ui.ImageWidth.textEdited.connect(self.update_from_image_width)

        self.ui.CancelDialog.clicked.connect(self.reject)
        self.ui.ExportHeightmap.clicked.connect(self.export_heightmap)
        self.ui.StartPathTracer.clicked.connect(self.start_path_tracer)

    def check_ready(self):
        """Enable the export button if the parameters have been entered."""
        self.ui.CancelDialog.setText('Cancel')
        try:
            ready = (float(self.ui.ModelHeight.text()) and
                     float(self.ui.ModelWidth.text()) and
                     int(self.ui.ImageHeight.text()) and
                     int(self.ui.ImageWidth.text()))
        except ValueError:
            self.ui.ExportHeightmap.setEnabled(False)
        else:
            self.ui.ExportHeightmap.setEnabled(ready)

    def scale_factor(self):
        """Return the scale factor, defaulting to 1 if not set."""
        try:
            sfactor = float(self.ui.ScaleFactor.text())
        except ValueError:
            sfactor = 1.0
            self.ui.ScaleFactor.setText('1')
        return sfactor

    def update_scales(self, also_resolution=True):
        """Update the scale (and resolution) entries in the dialog."""
        try:
            mheight = float(self.ui.ModelHeight.text())
            sdepth = float(self.ui.ScaleDepth.text())
        except ValueError:
            mheight = False
            sdepth = False
        if mheight and sdepth:
            self.ui.HorizontalScale.setText('%s m/mm (%s:1)' % (
                str(round(self.height/mheight, self.SCALE_DECIMAL_DIGITS)),
                QLocale().toString(float(self.height/mheight*1000), 'f', 0)))
            self.ui.VerticalScale.setText('%s m/mm (%s:1)' % (
                str(round((self.zmax - self.zmin)/sdepth,
                          self.SCALE_DECIMAL_DIGITS)),
                QLocale().toString(float((self.zmax - self.zmin) /
                                         sdepth*1000), 'f', 0)))
            if also_resolution:
                try:
                    iheight = float(self.ui.ImageHeight.text())
                except ValueError:
                    iheight = False
                if iheight:
                    self.ui.Resolution.setText(
                        str(round(mheight/iheight, self.SCALE_DECIMAL_DIGITS)))
        self.check_ready()

    def update_from_model_height(self, mheight):
        """Update the scaled model parameters based on a new height."""
        try:
            mheight = float(mheight)
        except ValueError:
            return
        if not self.height:
            return
        self.ui.ModelWidth.setText(str(round(
            mheight/self.height
            * self.width, self.SIZE_DECIMAL_DIGITS)))
        self.ui.ModelDepth.setText(str(round(
            mheight/self.height
            * (self.zmax - self.zmin), self.SIZE_DECIMAL_DIGITS)))
        self.ui.ScaleDepth.setText(str(round(
            mheight/self.height * (self.zmax - self.zmin)
            * self.scale_factor(), self.SIZE_DECIMAL_DIGITS)))
        self.update_scales()

    def update_from_model_width(self, mwidth):
        """Update the scaled model parameters based on a new width."""
        try:
            mwidth = float(mwidth)
        except ValueError:
            return
        if not self.width:
            return
        self.ui.ModelHeight.setText(str(round(
            mwidth/self.width
            * self.height, self.SIZE_DECIMAL_DIGITS)))
        self.ui.ModelDepth.setText(str(round(
            mwidth/self.width
            * (self.zmax - self.zmin), self.SIZE_DECIMAL_DIGITS)))
        self.ui.ScaleDepth.setText(str(round(
            mwidth/self.width * (self.zmax - self.zmin)
            * self.scale_factor(), self.SIZE_DECIMAL_DIGITS)))
        self.update_scales()

    def update_from_model_depth(self, mdepth):
        """Update the scaled model parameters based on a new depth."""
        try:
            mdepth = float(mdepth)
        except ValueError:
            return
        if (self.zmax - self.zmin) == 0:
            return
        self.ui.ModelHeight.setText(str(round(
            mdepth / (self.zmax - self.zmin)
            * self.height, self.SIZE_DECIMAL_DIGITS)))
        self.ui.ModelWidth.setText(str(round(
            mdepth / (self.zmax - self.zmin)
            * self.width, self.SIZE_DECIMAL_DIGITS)))
        try:
            sfactor = float(self.ui.ScaleFactor.text())
        except ValueError:
            sfactor = 1.0
            self.ui.ScaleFactor.setText('1')
        self.ui.ScaleDepth.setText(str(round(
            mdepth * sfactor, self.SIZE_DECIMAL_DIGITS)))
        self.update_scales()

    def update_from_scale_depth(self, sdepth):
        """Update the scaled model parameters based on a new scaled depth."""
        try:
            mdepth = float(self.ui.ModelDepth.text())
            sdepth = float(sdepth)
        except ValueError:
            return
        if not mdepth or not sdepth:
            return
        self.ui.ScaleFactor.setText(str(round(
            sdepth / mdepth, self.SCALE_DECIMAL_DIGITS)))
        self.update_scales()

    def update_from_scale_factor(self, sfactor):
        """Update the scaled model parameters based on a new scale factor."""
        try:
            mdepth = float(self.ui.ModelDepth.text())
            sfactor = float(sfactor)
        except ValueError:
            return
        if not mdepth or not sfactor:
            return
        self.ui.ScaleDepth.setText(str(round(
            mdepth * sfactor, self.SCALE_DECIMAL_DIGITS)))
        self.update_scales()

    def update_from_resolution(self, res):
        """Update the image parameters based on a new physical resolution."""
        try:
            mheight = float(self.ui.ModelHeight.text())
            res = float(res)
        except ValueError:
            return
        if not mheight or not res:
            return
        self.ui.ImageHeight.setText('%i' % round(mheight / res))
        self.ui.ImageWidth.setText(
            '%i' % round(mheight / self.height * self.width / res))
        self.update_scales(False)

    def update_from_image_height(self, iheight):
        """Update the image parameters based on a new image height."""
        try:
            mheight = float(self.ui.ModelHeight.text())
            iheight = round(float(self.ui.ImageHeight.text()))
        except ValueError:
            return
        if not mheight or not iheight:
            return
        self.ui.ImageWidth.setText(
            '%i' % round(iheight / self.height * self.width))
        self.update_scales()

    def update_from_image_width(self, iwidth):
        """Update the image parameters based on a new image width."""
        try:
            mwidth = float(self.ui.ModelWidth.text())
            iwidth = float(self.ui.ImageWidth.text())
        except ValueError:
            return
        if not mwidth or not iwidth:
            return
        self.ui.ImageHeight.setText(
            '%i' % round(iwidth / self.width * self.height))
        self.update_scales()

    def layer_changed(self, layer):
        """Update the dialog to show data from a newly selected layer."""
        self.reset_dialog()
        self.get_dimensions(layer)
        self.draw_box(layer)

    def reset_dialog(self):
        """Clear any existing user input from the dialog."""
        self.ui.ModelHeight.clear()
        self.ui.ModelWidth.clear()
        self.ui.ModelDepth.clear()
        self.ui.ScaleDepth.clear()
        self.ui.ScaleFactor.setText('1')
        self.ui.Resolution.clear()
        self.ui.ImageHeight.clear()
        self.ui.ImageWidth.clear()
        self.ui.HorizontalScale.setText('')
        self.ui.VerticalScale.setText('')
        if self.extent:
            self.canvas.scene().removeItem(self.extent)
            self.extent = None

    def get_dimensions(self, layer):
        """Calculate and display map dimensions."""
        # In case this takes noticeable time, change the cursor for now.
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        extent = layer.extent()
        
        # The raster layer could be in any CRS, e.g. lat/lon, UTM, etc.
        # Using a coordinate transform, we convert the bounds of the
        # raster layer to latitude and longitude in the WGS-84
        # Coordinate Reference System so our math is straightforward.
        source = layer.crs()
        wgs84 = QgsCoordinateReferenceSystem("EPSG:4326")
        if self.QGIS_VERSION == 2:
          transform = QgsCoordinateTransform(source, wgs84)
        else:
          transform = QgsCoordinateTransform(source, wgs84, QgsProject.instance())
        rect = transform.transform(extent)
        latn = rect.yMaximum()
        lats = rect.yMinimum()
        lonw = rect.xMinimum()
        lone = rect.xMaximum()

        # With the latitude and longitude bounds of the raster layer,
        # we can use simplifications of the great circle distance
        # calculations to determine the height (north/south) and
        # width (east/west) of the area (measured across the middle).
        hy = sqrt((sin((radians(lats) - radians(latn))/2))**2)
        hx = sqrt(1 - (sin((radians(lats) - radians(latn))/2))**2)
        height = self.EARTH_RADIUS * 2 * atan2(hy, hx)
        wy = sqrt((cos((radians(lats) + radians(latn))/2))**2
                  * (sin((radians(lone) - radians(lonw))/2))**2)
        wx = sqrt(1 - ((cos((radians(lats) + radians(latn))/2))**2
                       * (sin((radians(lone) - radians(lonw))/2))**2))
        width = self.EARTH_RADIUS * 2 * atan2(wy, wx)

        # We also need the highest and lowest points, which we get
        # with a straightforward API call to GDAL.
        src = gdal.Open(layer.dataProvider().dataSourceUri().split('|')[0])
        (zmin, zmax) = src.GetRasterBand(1).ComputeRasterMinMax(False)

        # Now save the values for later, fill in the appropriate fields
        # in the dialog, and put the cursor back where we found it.
        self.height = height
        self.width = width
        self.zmin = zmin
        self.zmax = zmax
        self.ui.MapHeight.setText(
            QLocale().toString(float(height), 'f', self.SIZE_DECIMAL_DIGITS))
        self.ui.MapWidth.setText(
            QLocale().toString(float(width), 'f', self.SIZE_DECIMAL_DIGITS))
        self.ui.MapHighest.setText(
            QLocale().toString(float(zmax), 'f', self.SIZE_DECIMAL_DIGITS))
        self.ui.MapLowest.setText(
            QLocale().toString(float(zmin), 'f', self.SIZE_DECIMAL_DIGITS))
        QApplication.restoreOverrideCursor()

    def draw_box(self, layer):
        """Draw a box around the extent of the selected layer."""
        rec = layer.extent()
        x_max = rec.xMaximum()
        y_min = rec.yMinimum()
        x_min = rec.xMinimum()
        y_max = rec.yMaximum()

        if self.extent:
            self.canvas.scene().removeItem(self.extent)
            self.extent = None
        self.extent = QgsRubberBand(self.canvas, True)
        if self.QGIS_VERSION == 2:
            points = [QgsPoint(x_max, y_min),
                      QgsPoint(x_max, y_max),
                      QgsPoint(x_min, y_max),
                      QgsPoint(x_min, y_min),
                      QgsPoint(x_max, y_min)]
            self.extent.setToGeometry(QgsGeometry.fromPolyline(points), None)
        else:
            points = [QgsPointXY(x_max, y_min),
                      QgsPointXY(x_max, y_max),
                      QgsPointXY(x_min, y_max),
                      QgsPointXY(x_min, y_min),
                      QgsPointXY(x_max, y_min)]
            self.extent.setToGeometry(QgsGeometry.fromPolylineXY(points), None)
        self.extent.setColor(QColor(255, 25, 25, 255))
        self.extent.setWidth(4)
        self.extent.setLineStyle(Qt.PenStyle(Qt.DashLine))
        self.canvas.refresh()

    def save_metadata(self, export_file):
        """Save metadata for the heightmap."""
        metafile = '{}.ini'.format(splitext(export_file)[0])
        meta = ConfigParser()
        layer = self.ui.LayerComboBox.currentLayer()
        rec = layer.extent()
        if self.QGIS_VERSION == 2:
            meta.add_section('Source')
            meta.set('Source','name',layer.name())
            meta.add_section('Bounds')
            meta.set('Bounds','north',str(rec.yMaximum()))
            meta.set('Bounds','south',str(rec.yMinimum()))
            meta.set('Bounds','west',str(rec.xMinimum()))
            meta.set('Bounds','east',str(rec.xMaximum()))
            meta.set('Bounds','high',str(self.zmax))
            meta.set('Bounds','low',str(self.zmin))
            meta.add_section('Size')
            meta.set('Size','height',str(self.height))
            meta.set('Size','width',str(self.width))
            meta.set('Size','depth',str(self.zmax - self.zmin))
            meta.add_section('Model')
            meta.set('Model','x_width',self.ui.ModelWidth.text())
            meta.set('Model','y_height',self.ui.ModelHeight.text())
            meta.set('Model','z_depth',self.ui.ModelDepth.text())
            meta.set('Model','scale_depth',self.ui.ScaleDepth.text())
            meta.set('Model','scale_factor',self.ui.ScaleFactor.text())
            meta.add_section('Heightmap')
            meta.set('Heightmap','width',self.ui.ImageWidth.text())
            meta.set('Heightmap','height',self.ui.ImageHeight.text())
        else:
            meta['Source'] = { 'name' : layer.name() }
            meta['Bounds'] = { 'north' : str(rec.yMaximum()),
                               'south' : str(rec.yMinimum()),
                               'west' : str(rec.xMinimum()),
                               'east' : str(rec.xMaximum()),
                               'high' : str(self.zmax),
                               'low' : str(self.zmin)
                             }
            meta['Size'] = { 'height' : str(self.height),
                             'width' : str(self.width),
                             'depth' : str(self.zmax - self.zmin)
                           }
            meta['Model'] = { 'x_width' : self.ui.ModelWidth.text(),
                              'y_height' : self.ui.ModelHeight.text(),
                              'z_depth' : self.ui.ModelDepth.text(),
                              'scale_depth' : self.ui.ScaleDepth.text(),
                              'scale_factor' : self.ui.ScaleFactor.text()
                            }
            meta['Heightmap'] = { 'width' : self.ui.ImageWidth.text(),
                                  'height' : self.ui.ImageHeight.text()
                                }
        with open(metafile, 'w') as mfile:
          meta.write(mfile)

    def start_path_tracer(self):
            pt = PathTracerGUI(heightmap=self.heightmap,
                               x_width=self.ui.ModelWidth.text(),
                               z_depth=self.ui.ScaleDepth.text(),
                               zero_x=50,
                               zero_y=50,
                               safe_z=3,
                               feed_plunge=200,
                               feed_carve=2000,
                               optimize=0,
                               x_offset=0,
                               y_offset=0,
                               z_offset=0,
                               laser_mode=False
                               )
            pt.setModal(True)
            pt.show()
            pt.exec_()
          
    def export_heightmap(self):
        """Export the heightmap.
        
        Show a save dialog, then use GDAL to translate the chosen raster
        layer to a 16-bit PNG scaled to the chosen image dimensions, with
        the output levels scaled up to full range.
        
        """
        # Get the selected layer from the box.
        layer = self.ui.LayerComboBox.currentLayer()
        uri = layer.dataProvider().dataSourceUri()

        # Make up a suggestion for the save dialog, then present the dialog.
        suggestion = uri.split('|')[0].rsplit('.', 1)[0] + '_heightmap.png'
        if self.QGIS_VERSION == 2:
            export_file = QFileDialog.getSaveFileName(
                self, 'Export to PNG', suggestion,
                filter="16-bit PNG Heightmap (*.png)")
        else:
            export_file, __ = QFileDialog.getSaveFileName(
                self, 'Export to PNG', suggestion,
                filter="16-bit PNG Heightmap (*.png)")
        if export_file:
            self.heightmap = export_file
            # Change the cursor in case this takes a while.
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            # Hand it over to GDAL to do the export.
            src = gdal.Open(uri.split('|')[0])
            ds = gdal.Translate(
                export_file, src, format='PNG',
                outputType=gdal.GDT_UInt16,
                width=int(self.ui.ImageWidth.text()),
                height=int(self.ui.ImageHeight.text()),
                scaleParams=[[self.zmin, self.zmax, 0, 65535]])
            self.save_metadata(export_file)
            # With the export complete, clean up and inform the user.
            self.ui.CancelDialog.setText('Close')
            QApplication.restoreOverrideCursor()
            self.messageBar.pushInfo(
                "Heightmap Export", "%s heightmap exported." % layer.name())
