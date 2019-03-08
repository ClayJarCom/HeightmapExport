"""
Provide UI for mapping SVG paths onto PNG heightmap data.

PathTracer allows the user to load a PNG heightmap,
load an SVG with paths, and choose what settings to use
to render the paths into G-code engraving toolpaths
mapped onto the surface of the heightmap.
"""
import sys
import argparse

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Trace paths onto a heightmap.')
    parser.add_argument('-hm','--heightmap',default=None,
                        help='Heightmap PNG filename.')
    parser.add_argument('-pm','--pathmap',default=None,
                        help='Pathmap SVG filename.')
    parser.add_argument('-pv','--preview',default=None,
                        help='Preview PNG filename.')
    parser.add_argument('-gc','--gcode',default=None,help='G-code filename.')
    parser.add_argument('-xw','--x_width',default=None,type=float,
                        help='X-axis width of model.')
    parser.add_argument('-zd','--z_depth',default=None,type=float,
                        help='Z-axis maximum depth.')
    parser.add_argument('-sz','--safe_z',default=3,type=float,
                        help='Safe Z between paths, >0.')
    parser.add_argument('-0x','--zero_x',default=50,type=float,
                        help='X0 as percent from left edge.')
    parser.add_argument('-0y','--zero_y',default=50,type=float,
                        help='Y0 as percent from front edge.')
    parser.add_argument('-ox','--offset_x',default=0,type=float,
                        help='Add offset to X values.')
    parser.add_argument('-oy','--offset_y',default=0,type=float,
                        help='Add offset to Y values.')
    parser.add_argument('-oz','--offset_z',default=0,type=float,
                        help='Add offset to Z values.')
    parser.add_argument('-fp','--feed_plunge',default=200,type=float,
                        help='Feed rate entering path.')
    parser.add_argument('-fc','--feed_carve',default=2000,type=float,
                        help='Feed rate following path.')
    parser.add_argument('-ss','--spindle_speed',default=None,type=float,
                        help='Spindle speed or laser setting.')
    parser.add_argument('-lm','--laser_mode',action='store_true',
                        help='Enable laser mode output.')
    parser.add_argument('-rh','--rescale_heightmap',action='store_true',
                        help='Export rescaled heightmap.')
    parser.add_argument('-op','--optimize',default=0,type=float,
                        help='Optimization distance.')
    args = parser.parse_args()
  
    if ((args.heightmap is not None) and 
        (args.pathmap is not None) and 
        (args.x_width is not None) and 
        (args.z_depth is not None)):
        from main.path_tracer import PathTracer
        pt = PathTracer(heightmap=args.heightmap, pathmap=args.pathmap)
        pt.outputpng = args.preview
        pt.gcodefile = args.gcode
        z_offset = 0
        pt.trace_paths(args.x_width,
                       args.z_depth,
                       args.zero_x/100.0,
                       args.zero_y/100.0,
                       args.safe_z,
                       args.feed_plunge,
                       args.feed_carve,
                       args.optimize,
                       args.spindle_speed,
                       args.offset_x,
                       args.offset_y,
                       args.offset_z,
                       args.laser_mode,
                       args.rescale_heightmap)
    else:
        # GUI mode
        from PyQt5.QtWidgets import QApplication
        from gui.path_tracer_gui import PathTracerGUI
        app = QApplication(sys.argv)
        gui = PathTracerGUI(heightmap=args.heightmap,
                            pathmap=args.pathmap,
                            x_width=args.x_width,
                            z_depth=args.z_depth,
                            zero_x=args.zero_x,
                            zero_y=args.zero_y,
                            safe_z=args.safe_z,
                            feed_plunge=args.feed_plunge,
                            feed_carve=args.feed_carve,
                            optimize=args.optimize,
                            spindle_speed=args.spindle_speed,
                            offset_x=args.offset_x,
                            offset_y=args.offset_y,
                            offset_z=args.offset_z,
                            laser_mode=args.laser_mode,
                            rescale_heightmap=args.rescale_heightmap)
        gui.show()
        app.exec_()