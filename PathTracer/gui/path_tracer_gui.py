"""
Show the PathTracer GUI.

This dialog allows the user to load a PNG heightmap,
load an SVG with paths, and choose what settings to use
to render the paths into G-code engraving toolpaths
mapped onto the surface of the heightmap.
"""
import sys
from os.path import basename,splitext,isfile
from configparser import ConfigParser

try:
    # If this imports, we're in QGIS 2.
    # It was renamed 'Qgis' in QGIS 3.
    from qgis.core import QGis
    # QGIS 2 imports.
    from PyQt4 import QtCore, QtGui
    from PyQt4.QtGui import (QDialog, QColor, QFileDialog, QApplication,
                             QCursor, QDoubleValidator, QIntValidator,
                             QMessageBox)
    from PyQt4.QtCore import Qt
    from .PathTracerGUI_UI_2 import Ui_PathTracerGUI_UI
except ImportError:
    #QGIS 3 imports.
    from qgis.PyQt.QtWidgets import (QDialog, QFileDialog, 
                                     QApplication, QMessageBox)
    from qgis.PyQt.QtGui import (QColor, QCursor, QDoubleValidator,
                                 QIntValidator)
    from qgis.PyQt.QtCore import Qt
    from .PathTracerGUI_UI_3 import Ui_PathTracerGUI_UI

from ..main.path_tracer import PathTracer

class PathTracerGUI(QDialog, Ui_PathTracerGUI_UI):
    """    Present a dialog for setting options and running PathTracer.
    
    PathTracer maps paths from an SVG onto a heightmap from a PNG image. """
    try:
        QGis.QGIS_VERSION
        QGIS_VERSION = 2
    except:
        QGIS_VERSION = 3    

    SIZE_DECIMAL_DIGITS = 3
    MAXIMUM_ALLOWED_VALUE = 1000000
    MAXIMUM_FEED_RATE = 1000000

    def __init__(self, parent=None, heightmap=None, pathmap=None,
                 x_width=None, z_depth=None, safe_z=None,
                 zero_x=None, zero_y=None, feed_plunge=None,
                 feed_carve=None, optimize=None,
                 x_offset=None, y_offset=None, z_offset=None,
                 laser_mode=None, rescale_heightmap=None):
        """ Load initial values and setup PathTracer dialog. """
        super(PathTracerGUI, self).__init__(parent)
        self.setupUi(self)
        self.setFixedSize(self.width(),self.height())
        self.pt = PathTracer()

        if heightmap is not None:
            self.heightmap_file.setText(heightmap)
        if pathmap is not None:
            self.pathmap_file.setText(pathmap)
        if x_width is not None:
            self.x_width.setText(str(x_width))
        if z_depth is not None:
            self.z_depth.setText(str(z_depth))
        if safe_z is not None:
            self.safe_z.setText(str(safe_z))
        if zero_x is not None:
            self.zero_x.setText(str(zero_x))
        if zero_y is not None:
            self.zero_y.setText(str(zero_y))
        if feed_plunge is not None:
            self.feed_plunge.setText(str(feed_plunge))
        if feed_carve is not None:
            self.feed_carve.setText(str(feed_carve))
        if optimize is not None:
            self.optimize.setText(str(optimize))
        if x_offset is not None:
            self.offset_x.setText(str(x_offset))
        if y_offset is not None:
            self.offset_y.setText(str(y_offset))
        if z_offset is not None:
            self.offset_z.setText(str(z_offset))
        if (laser_mode is not None) and laser_mode:
            self.laser_mode.setChecked(True)
            set_lasermode()
        if (rescale_heightmap is not None) and rescale_heightmap:
            self.rescale_heightmap.setChecked(True)
        self.power_pct.setText('100')
        self.power_min.setText('0')
        self.power_max.setText('1000')
            
        self.browse_heightmap.clicked.connect(self.select_heightmap)
        self.browse_pathmap.clicked.connect(self.select_pathmap)
        self.exportGcode.clicked.connect(self.export_gcode)
        self.laser_mode.clicked.connect(self.set_lasermode)
        self.enable_offsets.clicked.connect(self.set_offsets)
        
        self.ZeroNW.clicked.connect(self.zero_nw)
        self.ZeroN.clicked.connect(self.zero_n)
        self.ZeroNE.clicked.connect(self.zero_ne)
        self.ZeroE.clicked.connect(self.zero_e)
        self.ZeroSE.clicked.connect(self.zero_se)
        self.ZeroS.clicked.connect(self.zero_s)
        self.ZeroSW.clicked.connect(self.zero_sw)
        self.ZeroW.clicked.connect(self.zero_w)
        self.ZeroC.clicked.connect(self.zero_c)
        self.zero_x.textEdited.connect(self.check_zero)
        self.zero_y.textEdited.connect(self.check_zero)
        self.check_zero()
        
        validDecimals = QDoubleValidator(0.1 ** self.SIZE_DECIMAL_DIGITS,
                                         self.MAXIMUM_ALLOWED_VALUE,
                                         self.SIZE_DECIMAL_DIGITS)
        self.x_width.setValidator(validDecimals)
        self.x_width.textEdited.connect(self.update_from_x_width)
        self.y_height.setValidator(validDecimals)
        self.y_height.textEdited.connect(self.update_from_y_height)
        self.z_depth.setValidator(validDecimals)
        self.z_depth.textEdited.connect(self.check_ready)
        self.zero_x.setValidator(validDecimals)
        self.zero_x.textEdited.connect(self.check_ready)
        self.zero_y.setValidator(validDecimals)
        self.zero_y.textEdited.connect(self.check_ready)
        self.safe_z.setValidator(validDecimals)
        self.safe_z.textEdited.connect(self.check_ready)
        self.optimize.setValidator(validDecimals)
        self.optimize.textEdited.connect(self.check_ready)
        
        self.power_pct.setValidator(validDecimals)
        self.power_pct.textEdited.connect(self.check_ready)
        self.power_max.setValidator(validDecimals)
        self.power_max.textEdited.connect(self.check_ready)
        self.power_min.setValidator(validDecimals)
        self.power_min.textEdited.connect(self.check_ready)
        self.offset_x.setValidator(validDecimals)
        self.offset_x.textEdited.connect(self.check_ready)
        self.offset_y.setValidator(validDecimals)
        self.offset_y.textEdited.connect(self.check_ready)
        self.offset_z.setValidator(validDecimals)
        self.offset_z.textEdited.connect(self.check_ready)
        
        validIntegers = QIntValidator(1, self.MAXIMUM_FEED_RATE)
        self.feed_plunge.setValidator(validIntegers)
        self.feed_plunge.textEdited.connect(self.check_ready)
        self.feed_carve.setValidator(validIntegers)
        self.feed_carve.textEdited.connect(self.check_ready)
        
        if (heightmap is not None) and isfile(heightmap):
            self.heightmap_selected(heightmap)
            self.update_from_x_width()

    def check_ready(self):
        """ Enable the export button if we have all the necessary input. """
        try:
            1 / float(self.x_width.text())
            1 / float(self.y_height.text())
            float(self.z_depth.text())
            1 / float(self.feed_carve.text())
            float(self.zero_x.text())
            float(self.zero_y.text())
            #float(self.optimize.text()) # We can assume zero if NaN
            float(self.safe_z.text())
            if self.laser_mode.isChecked():
                1 / float(self.power_pct.text())
                1 / float(self.power_max.text())
                float(self.power_min.text())
            else:
                1 / float(self.feed_plunge.text())
            ready = True
        except (ValueError,ZeroDivisionError):
            ready = False
        self.exportGcode.setEnabled(ready and (self.pathmap_file.text() != ''))
            
    def set_lasermode(self):
        """ Enable or disable laser options in the UI. """
        if self.laser_mode.isChecked():
            self.power_pct.setEnabled(True)
            self.power_max.setEnabled(True)
            self.power_min.setEnabled(True)
            self.l_power_pct.setEnabled(True)
            self.l_power_max.setEnabled(True)
            self.l_power_min.setEnabled(True)
            self.feed_plunge.setEnabled(False)
        else:
            self.power_pct.setEnabled(False)
            self.power_max.setEnabled(False)
            self.power_min.setEnabled(False)
            self.l_power_pct.setEnabled(False)
            self.l_power_max.setEnabled(False)
            self.l_power_min.setEnabled(False)
            self.feed_plunge.setEnabled(True)
        self.check_ready()
        
    def set_offsets(self):
        """ Enable or disable offset options in the UI. """
        if self.enable_offsets.isChecked():
            self.offset_x.setEnabled(True)
            self.offset_y.setEnabled(True)
            self.offset_z.setEnabled(True)
            self.l_offset_x.setEnabled(True)
            self.l_offset_y.setEnabled(True)
            self.l_offset_z.setEnabled(True)
        else:
            self.offset_x.setEnabled(False)
            self.offset_y.setEnabled(False)
            self.offset_z.setEnabled(False)
            self.l_offset_x.setEnabled(False)
            self.l_offset_y.setEnabled(False)
            self.l_offset_z.setEnabled(False)
        self.check_ready()
        
    def update_from_x_width(self):
        """ Update the dimensions to scale based on a given X width. """
        try:
            x = float(self.x_width.text())
        except ValueError:
            return
        self.y_height.setText('{}'.format(round(x / self.pt.cols * self.pt.rows,
                                          self.SIZE_DECIMAL_DIGITS)))
        if self.z:
            self.z_depth.setText('{}'.format(round(x / self.x * self.z,
                                             self.SIZE_DECIMAL_DIGITS)))
        self.check_ready()
        
    def update_from_y_height(self):
        """ Update the dimensions to scale based on a given Y height. """
        try:
            y = float(self.y_height.text())
        except ValueError:
            return
        self.x_width.setText('{}'.format(round(y / self.pt.rows * self.pt.cols,
                                               self.SIZE_DECIMAL_DIGITS)))
        if self.z:
            self.z_depth.setText('{}'.format(round(y / self.y * self.z,
                                                   self.SIZE_DECIMAL_DIGITS)))
        self.check_ready()
        
    def load_meta(self,meta,field,section,item):
        """ Load a data item from the metadata file into a UI field. """
        try:
            if self.QGIS_VERSION == 2:
              value = float(meta.get(section,item))
            else:
              value = float(meta[section][item])
        except (IndexError,ValueError):
            value = 0
        field.setText(str(value))
        return value
    
    def heightmap_selected(self,heightmap_file):
        """ Load a heightmap PNG file and set UI values based on it. """
        QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
        if self.pt.load_heightmap(heightmap_file):
            self.x = 0
            self.y = 0
            self.z = 0
            self.heightmap_file.setText(basename(heightmap_file))
            metafile = '{}.ini'.format(splitext(heightmap_file)[0])
            if isfile(metafile):
                meta = ConfigParser()
                meta.read(metafile)
                self.x = self.load_meta(meta,self.x_width,'Model','x_width')
                self.y = self.x / self.pt.cols * self.pt.rows
                self.update_from_x_width()
                self.z = self.load_meta(meta,self.z_depth,'Model','z_depth')
            self.groupCAM.setEnabled(True)
            self.browse_pathmap.setEnabled(True)
            self.pathmap_file.setEnabled(True)
        else:
            self.heightmap_file.setText('')
            self.groupCAM.setEnabled(False)
            self.browse_pathmap.setEnabled(False)
            self.pathmap_file.setEnabled(False)
        QApplication.restoreOverrideCursor()
        self.check_ready()
    
    def select_heightmap(self):
        """ Show an open file dialog to select a heightmap PNG. """
        if self.QGIS_VERSION == 2:
            heightmap_file = \
                QFileDialog.getOpenFileName(self,
                                            'Select Heightmap PNG',
                                            None,
                                            filter=('Heightmap PNG image'
                                                    ' (*.png)'))
        else:
            heightmap_file, __ = \
                QFileDialog.getOpenFileName(self,
                                            'Select Heightmap PNG',
                                            None,
                                            filter=('Heightmap PNG image'
                                                    ' (*.png)'))
        if heightmap_file:
            self.heightmap_selected(heightmap_file)

    def select_pathmap(self):
        """ Show an open file dialog and load the selected pathmap SVG. """
        if self.QGIS_VERSION == 2:
            pathmap_file = \
                QFileDialog.getOpenFileName(self,
                                            'Select Pathmap SVG',
                                            None,
                                            filter='Pathmap SVG image (*.svg)')
        else:
            pathmap_file, __ = \
                QFileDialog.getOpenFileName(self,
                                            'Select Pathmap SVG',
                                            None,
                                            filter='Pathmap SVG image (*.svg)')
        if pathmap_file:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            if self.pt.load_pathmap(pathmap_file):
                self.pathmap_file.setText(basename(pathmap_file))
            else:
                self.pathmap_file.setText('')
            QApplication.restoreOverrideCursor()
            self.check_ready()
            
    def export_gcode(self):
        """ Generate and export G-code. """
        suggestion = '{}.nc'.format(splitext(self.pt.pathmap)[0])
        if self.QGIS_VERSION == 2:
          gcode_file = \
              QFileDialog.getSaveFileName(self,
                                          'Save G-code as...',
                                          suggestion,
                                          filter='G-code file (*.nc)')
        else:
          gcode_file, __ = \
              QFileDialog.getSaveFileName(self,
                                          'Save G-code as...',
                                          suggestion,
                                          filter='G-code file (*.nc)')
        if gcode_file:
            QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
            self.pt.gcodefile = gcode_file
            self.pt.outputpng = '{}_preview.png'.format(splitext(gcode_file)[0])
            if self.laser_mode.isChecked():
                power = float(self.power_pct.text())/100.0
                power_max = float(self.power_max.text())
                power_min = float(self.power_min.text())
                spindle_speed = power * (power_max - power_min) + power_min
                laser_mode = True
            else:
                spindle_speed = None
                laser_mode = False            
            if self.enable_offsets.isChecked():
                try:
                    offset_x = float(self.offset_x.text())
                except ValueError:
                    offset_x = 0
                try:
                    offset_y = float(self.offset_y.text())
                except ValueError:
                    offset_y = 0
                try:
                    offset_z = float(self.offset_z.text())
                except ValueError:
                    offset_z = 0
            else:
                offset_x = 0
                offset_y = 0
                offset_z = 0
            try:
                optimize = float(self.optimize.text())
            except ValueError:
                optimize = 0
            self.pt.trace_paths(float(self.x_width.text()),
                                float(self.z_depth.text()),
                                float(self.zero_x.text())/100.0,
                                float(self.zero_y.text())/100.0,
                                float(self.safe_z.text()),
                                float(self.feed_plunge.text()),
                                float(self.feed_carve.text()),
                                float(optimize),
                                spindle_speed,
                                offset_x,
                                offset_y,
                                offset_z,
                                laser_mode,
                                self.rescale_heightmap.isChecked()
                               )
            QApplication.restoreOverrideCursor()
            QMessageBox.about(self,'PathTracer','G-code exported.')
                                                    
    def check_zero(self):
        """ Mark a radio button if the text zeroes match it. """
        self.Zeroes.setExclusive(False)
        x = self.zero_x.text()
        y = self.zero_y.text()
        self.ZeroNW.setChecked((x == '0') and (y == '100'))
        self.ZeroN.setChecked((x == '50') and (y == '100'))
        self.ZeroNE.setChecked((x == '100') and (y == '100'))
        self.ZeroE.setChecked((x == '100') and (y == '50'))
        self.ZeroSE.setChecked((x == '100') and (y == '0'))
        self.ZeroS.setChecked((x == '50') and (y == '0'))
        self.ZeroSW.setChecked((x == '0') and (y == '0'))
        self.ZeroW.setChecked((x == '0') and (y == '50'))
        self.ZeroC.setChecked((x == '50') and (y == '50'))
        self.Zeroes.setExclusive(True)
    
    def set_zero(self,x,y):
        """ Set the X and Y zeroes. """
        self.zero_x.setText(str(x))
        self.zero_y.setText(str(y))
 
    def zero_nw(self):
        """ Set the zero to the NW corner. """
        self.set_zero(0,100)
    def zero_n(self):
        """ Set the zero to the center of the N edge. """
        self.set_zero(50,100)
    def zero_ne(self):
        """ Set the zero to the NE corner. """
        self.set_zero(100,100)
    def zero_e(self):
        """ Set the zero to the center of the E edge. """
        self.set_zero(100,50)
    def zero_se(self):
        """ Set the zero to the SE corner. """
        self.set_zero(100,0)
    def zero_s(self):
        """ Set the zero to the center of the S edge. """
        self.set_zero(50,0)
    def zero_sw(self):
        """ Set the zero to the SW corner. """
        self.set_zero(0,0)
    def zero_w(self):
        """ Set the zero to the center of the W edge. """
        self.set_zero(0,50)
    def zero_c(self):
        """ Set the zero to the center. """
        self.set_zero(50,50)
        
if __name__ == '__main__':
    print('GUI version.')