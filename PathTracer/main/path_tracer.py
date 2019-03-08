"""
Map SVG paths onto PNG heightmap data.

PathTracer allows the user to load a PNG heightmap,
load an SVG with paths, and choose what settings to use
to render the paths into G-code engraving toolpaths
mapped onto the surface of the heightmap.
"""
from os.path import splitext
import re
from copy import deepcopy
from bisect import bisect
from math import pi,sin,cos,tan,sqrt
import xml.etree.ElementTree as ET
from ..png.png import Reader, Writer
from ..path import parse_path

class PathTracer():
    """ Trace SVG paths onto PNG heightmap data. """
    COLINEAR_DISTANCE = 0.0
    MAX_FILTER_CYCLES = 100
    heightmap = None
    heightmap_loaded = False
    pathmap = None
    pathmap_loaded = False

    outpng = None
    pixels = None
    rows = 0
    cols = 0
    meta = 0

    outputpng = None
    gcodefile = None

    svg_height = 0
    svg_width = 0
    svg_viewbox = (0,0,0,0)
    parsed_paths = None

    def __init__(self,heightmap=None,pathmap=None):
        """ Initialize PathTracer, loading data if so indicated. """
        if heightmap is not None:
            self.heightmap = heightmap
            self.heightmap_loaded = self.load_png(heightmap)
        if pathmap is not None:
            self.pathmap = pathmap
            self.pathmap_loaded = self.load_svg(pathmap)

    def ready(self):
        """ Return true if a heightmap and pathmap are loaded. """
        return self.heightmap_loaded and self.pathmap_loaded

    def load_heightmap(self,heightmap):
        """ Load a PNG heightmap from a file. """
        self.heightmap = heightmap
        self.heightmap_loaded = self.load_png(heightmap)
        return self.heightmap_loaded

    def load_pathmap(self,pathmap):
        """ Load an SVG pathmap from a file. """
        self.pathmap = pathmap
        self.pathmap_loaded = self.load_svg(pathmap)
        return self.pathmap_loaded

    def parse_units(self,value):
        """ Convert value with units to millimeters. """
        value = value.lower()
        if value.endswith('mm'):
            val = value[:-2].strip()
            multiplier = 1.0
        elif value.endswith('cm'):
            val = value[:-2].strip()
            multiplier = 10.0
        elif value.endswith('q'):
            val = value[:-1].strip()
            multiplier = 0.25
        elif value.endswith('in'):
            val = value[:-2].strip()
            multiplier = 25.4
        elif value.endswith('pc'):
            val = value[:-2].strip()
            multiplier = 25.4/6.0
        elif value.endswith('pt'):
            val = value[:-2].strip()
            multiplier = 25.4/72.0
        elif value.endswith('px'):
            val = value[:-2].strip()
            multiplier = 25.4/96.0
        else:
            val = value
            multiplier = 1.0
        try:
            parsed = float(val) * multiplier
        except ValueError:
            parsed = None
        return parsed

    def to_radians(self,angle):
        """ Convert angle string to radians, assuming degrees if labeled. """
        a = angle.lower().strip()
        if a.endswith('deg'):
            radians = float(a[:-3])/180.0*pi
        elif a.endswith('grad'):
            radians = float(a[:-4])/200.0*pi
        elif a.endswith('turn'):
            radians = float(a[:-4])*2*pi
        elif a.endswith('rad'):
            radians = float(a[:-4])
        else: #assume degrees
            radians = float(a)/180.0*pi
        return radians

    def multiply_matrices(self,a,b):
        """ Multiply two matrices.

        a, b: transform_matrix
        transform_matrix: (a,b,c,d,e,f)
                [a b c]
                [d e f]
                [0 0 1]

        """
        return [a[0]*b[0]+a[1]*b[3], a[0]*b[1]+a[1]*b[4],
                a[0]*b[2]+a[1]*b[5]+a[2], a[3]*b[0]+a[4]*b[3],
                a[3]*b[1]+a[4]*b[4], a[3]*b[2]+a[4]*b[5]+a[5]]

    def apply_transform(self,point,transform_matrix):
        """ Apply transform matrix to (X,Y).

        point: (x,y)
        transform_matrix: (a,b,c,d,e,f)
                [a b c]
                [d e f]
                [0 0 1]

        """
        return (transform_matrix[0]*point[0] +
                transform_matrix[1]*point[1] +
                transform_matrix[2],
                transform_matrix[3]*point[0] +
                transform_matrix[4]*point[1] +
                transform_matrix[5])

    def apply_viewbox(self,point):
        """ Compute nominal coordinates from point and viewbox.

        This takes a point (X,Y) after any transforms and scales each
        axis to the range zero to one.    The nominal coordinates can then
        be applied against the physical or image scale as appropriate.

        point: (x,y)
        viewbox: (xmin,ymin,width,height)

        """
        return ((float(point[0]) - float(self.svg_viewbox[0])) /
                 float(self.svg_viewbox[2]),
                (float(point[1]) - float(self.svg_viewbox[1])) /
                 float(self.svg_viewbox[3]))

    def apply_image_size(self,point):
        """ Compute pixel coordinates from point and image size.

        This takes a nominal point (X,Y) scales it to image coordinates.

        point: (x,y), float between 0 and 1.

        """
        return (int(round(self.cols*point[0])),
                int(round(self.rows*point[1])))

    def transforms_to_matrix(self,transform):
        """ Compute the transform matrix from a SVG transform attribute.

        Take each transform function in the string and render it as
        a transform matrix.    Multiply the transform matrices to yield
        one overall transform matrix from the transforms in the string.

        transform: string contents of an SVG transform attribute
        return: transform_matrix
            transform_matrix: (a,b,c,d,e,f)
                [a b c]
                [d e f]
                [0 0 1]

        """
        matrix_values = [1,0,0,0,1,0]
        if transform is None:
            transforms = []
        else:
            transforms = reversed(transform.lower().split(' '))
        r = re.compile('[, ]+')
        for t in transforms:
            #print(t)
            if t.startswith('matrix('):
                # Split into abcdxy, which doesn't match our abcdef,
                # which means we need to go abxcdy when we use it.
                m = r.split(t[7:-1])
                try:
                    a = float(m[0])
                    b = float(m[1])
                    c = float(m[2])
                    d = float(m[3])
                    x = float(m[4])
                    y = float(m[5])
                except ValueError:
                    pass
                else:
                    matrix_values = self.multiply_matrices([a,b,x,c,d,y],
                                                           matrix_values)
            elif t.startswith('translate('):
                #split into xy, if no y, y=0
                v = r.split(t[10:-1])
                try:
                    x = float(v[0])
                except ValueError:
                    pass
                else:
                    try:
                        y = float(v[1])
                    except ValueError:
                        pass
                    except IndexError:
                        matrix_values = self.multiply_matrices([1,0,x,0,1,0],
                                                               matrix_values)
                    else:
                        matrix_values = self.multiply_matrices([1,0,x,0,1,y],
                                                               matrix_values)
            elif t.startswith('translatex('):
                #get x
                try:
                    v = float(t[11:-1])
                except ValueError:
                    pass
                else:
                    matrix_values = self.multiply_matrices([1,0,v,0,1,0],
                                                           matrix_values)
            elif t.startswith('translatey('):
                #get y
                try:
                    v = float(t[11:-1])
                except ValueError:
                    pass
                else:
                    matrix_values = self.multiply_matrices([1,0,0,0,1,v],
                                                           matrix_values)
            elif t.startswith('scale('):
                #split into xy, if no y, y=x
                v = r.split(t[6:-1])
                try:
                    x = float(v[0])
                except ValueError:
                    pass
                else:
                    try:
                        y = float(v[1])
                    except ValueError:
                        pass
                    except IndexError:
                        matrix_values = self.multiply_matrices([x,0,0,0,x,0,0],
                                                               matrix_values)
                    else:
                        matrix_values = self.multiply_matrices([x,0,0,0,y,0,0],
                                                               matrix_values)
            elif t.startswith('scalex('):
                #get x
                try:
                    x = float(t[7:-1])
                except ValueError:
                    pass
                else:
                    matrix_values = self.multiply_matrices([x,0,0,0,1,0,0],
                                                           matrix_values)
            elif t.startswith('scaley('):
                #get y
                try:
                    y = float(t[7:-1])
                except ValueError:
                    pass
                else:
                    matrix_values = self.multiply_matrices([1,0,0,0,y,0,0],
                                                           matrix_values)
            elif t.startswith('rotate('):
                #split into a,x,y.
                #If x,y, translate() first, then rotate, then anti-translate()
                v = r.split(t[7:-1])
                #print(v)
                try:
                    a = self.to_radians(v[0])
                except ValueError:
                    pass
                else:
                    try:
                        x = float(v[1])
                        y = float(v[2])
                    except ValueError:
                        pass
                    except IndexError:
                        matrix_values = \
                            self.multiply_matrices([round(cos(a),8),
                                                    round(-sin(a),8),
                                                    0,
                                                    round(sin(a),8),
                                                    round(cos(a),8),
                                                    0], matrix_values)
                    else:
                        matrix_values = \
                            self.multiply_matrices([1,0,-x,0,1,-y],
                                                   matrix_values)
                        matrix_values = \
                            self.multiply_matrices([round(cos(a),8),
                                                    round(-sin(a),8),
                                                    0,
                                                    round(sin(a),8),
                                                    round(cos(a),8),
                                                    0], matrix_values)
                        matrix_values = \
                            self.multiply_matrices([1,0,x,0,1,y],
                                                   matrix_values)
            elif t.startswith('skew('):
                #get ax,ay
                v = r.split(t[5:-1])
                try:
                    ax = self.to_radians(v[0])
                except ValueError:
                    pass
                else:
                    try:
                        ay = self.to_radians(v[1])
                    except ValueError:
                        pass
                    except IndexError:
                        matrix_values = \
                            self.multiply_matrices([1,round(tan(ax),8),0,
                                                    0,1,0],matrix_values)
                    else:
                        matrix_values = \
                            self.multiply_matrices([1,round(tan(ax),8),0,
                                                    0,1,0], matrix_values)
                        matrix_values = \
                            self.multiply_matrices([1,0,0,
                                                    round(tan(ay),8),1,0],
                                                   matrix_values)
            elif t.startswith('skewx('):
                #get a
                try:
                    a = self.to_radians(t[5:-1])
                except ValueError:
                    pass
                else:
                    matrix_values = \
                        self.multiply_matrices([1,round(tan(a),8),0,
                                                0,1,0], matrix_values)
            elif t.startswith('skewy('):
                #get a
                try:
                    a = self.to_radians(t[5:-1])
                except ValueError:
                    pass
                else:
                    matrix_values = \
                        self.multiply_matrices([1,0,0,round(tan(a),8),1,0],
                                               matrix_values)
            else:
                pass
        return matrix_values

    def far_end(self,path_data,start_x,start_y):
        """ Walk a path segment and return the ending coordinates. """
        delimiter = re.compile(r'[ \t\r\n,]+')
        particles = delimiter.split(path_data)
        piece = 0
        implied = 'M'
        particle_defs = {
            'M':('L', 1, 2, 3),
            'L':('L', 1, 2, 3),
            'H':('H', 1, None, 2),
            'V':('V', None, 1, 2),
            'C':('C', 5, 6, 7),
            'S':('S', 3, 4, 5),
            'Q':('Q', 3, 4, 5),
            'T':('T', 1, 2, 3),
            'A':('A', 6, 7, 8),
            'Z':('L', None, None, 1),
            '':('', None, None, 1)
        }

        while piece < len(particles):
            particle = particles[piece]
            try:
             float(particle)
             particle = implied
             piece -= 1
            except ValueError:
             pass
            implied,x_piece,y_piece,next_piece = \
                particle_defs[particle.upper()]
            if particle.isupper():
             if x_piece is not None:
                 start_x = particles[piece + x_piece]
             if y_piece is not None:
                 start_y = particles[piece + y_piece]
            else:
             implied = implied.lower()
             if x_piece is not None:
                 if start_x is None:
                   start_x = particles[piece + x_piece]
                 else:
                   start_x += particles[piece + x_piece]
             if y_piece is not None:
                 if start_y is None:
                   start_y = particles[piece + y_piece]
                 else:
                   start_y += particles[piece + y_piece]
            piece += next_piece
        return (start_x,start_y)

    def get_paths(self,root,parent_map):
        """ Find, parse, and return the paths from an SVG. """
        m = re.compile('([Mm])')
        parsed_paths = []
        paths = root.findall('.//{http://www.w3.org/2000/svg}path')
        for path in paths:
            include = True
            matrix_values = self.transforms_to_matrix(path.get('transform'))
            element = path
            while(1):
                try:
                    element = parent_map[element]
                    if element.tag == '{http://www.w3.org/2000/svg}defs':
                        include = False
                        break
                except KeyError:
                    break
                transforms = \
                    self.transforms_to_matrix(element.get('transform'))
                matrix_values = self.multiply_matrices(transforms,
                                                       matrix_values)
            # Now that we have the translation matrix,
            # we can plot the curve in actual coordinates.
            if include:
                subpaths = m.split(path.get('d'))
                # Anything before the first move command is not allowed
                # and is therefore discarded, so we start at 1.
                start_x = None
                start_y = None
                for i in range(1,len(subpaths),2):
                    try:
                        if ((subpaths[i] == 'M') or
                            ((subpaths[i] == 'm') and (i == 1))):
                            path_data = \
                                '{}{}'.format(subpaths[i],subpaths[i+1])
                        else:
                            path_data = \
                                'M {},{} {}{}'.format(start_x,start_y,
                                                      subpaths[i],
                                                      subpaths[i+1])
                    except IndexError:
                        continue # Discard any trailing empty move.
                    parsed_paths += [{'transform_matrix': matrix_values,
                                      'path_data': path_data}]
                    start_x, start_y = self.far_end(path_data,start_x,start_y)
        return parsed_paths
            
    def load_svg(self,filename):
        """ Load an SVG file. """
        try:
          FileNotFoundError
        except NameError:
          FileNotFoundError = IOError
        try:
            svg = ET.parse(filename)
        except FileNotFoundError:
            return False
        parent_map = {c:p for p in svg.iter() for c in p}
        root = svg.getroot()
        r = re.compile('[, ]+')
        self.svg_viewbox = r.split(root.get('viewBox'))
        self.svg_height = self.parse_units(root.get('height'))
        self.svg_width = self.parse_units(root.get('width'))
        self.parsed_paths = self.get_paths(root,parent_map)
        return True

    def load_png(self,png_filename):
        """ Load a PNG file. """
        try:
          FileNotFoundError
        except NameError:
          FileNotFoundError = IOError
        try:
            r = Reader(filename=png_filename)
        except FileNotFoundError:
            return False
        self.cols, self.rows, data, self.meta = r.asDirect()
        # Turn the data into pixels[row][col]
        self.pixels = list(data)
        # If it's not a single-channel greyscale image, make it one.
        if self.meta['planes'] > 1:
            for i in range(len(self.pixels)):
                self.pixels[i] = self.pixels[i][0::self.meta['planes']]
            self.cols = len(self.pixels[0])
        # If necessary, rescale to 16 bits.
        if self.meta['bitdepth'] < 16:
            for i in range(len(self.pixels)):
                self.pixels[i] = [int(round(p * 65535 /
                                            (2**self.meta['bitdepth'] - 1)))
                                  for p in self.pixels[i]]
        min = None
        max = None
        for row in range(len(self.pixels)):
            for col in range(len(self.pixels[row])):
                if (min == None) or (self.pixels[row][col] < min):
                    min = self.pixels[row][col]
                if (max == None) or (self.pixels[row][col] > max):
                    max = self.pixels[row][col]
        self.min_z = min
        self.max_z = max
        self.outpng = [[0 for col in range(len(self.pixels[0]))]
                       for row in range(len(self.pixels))]
        return True

    def create_rescaled_heightmap(self):
        """ Create a rescaled heightmap to save, return scale factor. """
        self.rescaled = deepcopy(self.pixels)
        for row in range(len(self.rescaled)):
            for col in range(len(self.rescaled[row])):
                self.rescaled[row][col] = \
                    self.rescale(self.rescaled[row][col])
        scale_factor = (self.max_z - self.min_z) / 65535
        offset_factor = (65535 - self.max_z)/65535
        return (scale_factor, offset_factor)

    def rescale(self,pixel):
        """ Rescale a pixel from [min,max] to [0,65535]. """
        return int(round((pixel - self.min_z) / 
                         (self.max_z - self.min_z) * 65535))
        
    def add_fractional_lengths(self,svgpath):
        """ Add fractional lengths to svgpath to optimize point calculations.

        The version of svg.path we use has this patched in, but if you're using
        a stock version before our patch is integrated, our point() method uses
        this to precompute and add the fractional lengths.
        """
        svgpath._calc_lengths(error=1e-5)
        svgpath._fracs = []
        total = 0
        for l in svgpath._lengths:
            total += l
            svgpath._fracs.append(total)

    def point(self,svgpath,point):
        """ Find the coordinates for a point along a path.

        The version of svg.path we use has this patched in, but if you're using
        a stock version before our patch is integrated, you'll want to use this
        instead of the stock point() method.
        """
        try:
            i = bisect(svgpath._fracs,point)
        except AttributeError:
            self.add_fractional_lengths(svgpath)
            i = bisect(svgpath._fracs,point)
        newpoint = ((point - svgpath._fracs[i-1]) /
                    (svgpath._fracs[i] - svgpath._fracs[i-1]))
        return svgpath._segments[i].point(newpoint)

    def process_path(self,path):
        """ Convert a path into an ordered list of visited pixels.

        path: {'transform_matrix', 'path_data'}
        image_size: (width,height) in pixels

        """
        p = parse_path(path['path_data'])
        if not p:
            return []
        tm = path['transform_matrix']

        # It's easier to just calculate an excess of points than it is
        # to try to find an optimum number.  When pre-computing the
        # fractional lengths and using our updated point() function,
        # it is cromulently fast even with a basic brute force approach.
        path_steps = int(round(100*p.length(error=1e-5)))
        if path_steps < 10000:
            path_steps = 10000
        pixels = []
        previous = self.apply_image_size(
                       self.apply_viewbox(
                           self.apply_transform(
                               (p.point(0).real,p.point(0).imag),tm)))
        pixels.append(previous)

        for s in range(0,path_steps):
            step = 1.0*s/path_steps
            svgpoint = p.point(step)
            # If you're using the stock SVG Path package,
            # use our own point() method.
            #svgpoint = self.point(p,step)
            pixel = self.apply_image_size(
                        self.apply_viewbox(
                            self.apply_transform(
                                (svgpoint.real,svgpoint.imag),tm)))
            if (pixel[0] != previous[0]) or (pixel[1] != previous[1]):
                pixels.append(pixel)
                previous = pixel
        pixel = self.apply_image_size(
                    self.apply_viewbox(
                        self.apply_transform(
                            (p.point(1).real,p.point(1).imag),tm)))
        if (pixel[0] != previous[0]) or (pixel[1] != previous[1]):
            pixels.append(pixel)
            previous = pixel
        return pixels

    def copy_path_pixels(self,pixels,rescaled=False):
        """ Copy the pixels from our path into the output preview PNG. """
        for p in pixels:
            try:
                if (rescaled):
                  value = self.rescaled[p[1]][p[0]]
                else:
                  value = self.pixels[p[1]][p[0]]
            except IndexError:
                pass
            else:
                self.outpng[p[1]][p[0]] = value

    def write_png(self,pngdata,filename):
        """ Write the output preview PNG to a file. """
        f = open(filename, 'wb')
        w = Writer(len(pngdata[0]),
                   len(pngdata),
                   greyscale=True,
                   bitdepth=16)
        w.write(f, pngdata)
        f.close()

    def magnitude(self,v):
        ### Return the magnitude of a vector. """
        return sqrt(v[0]**2 + v[1]**2 + v[2]**2);

    def subtract_vectors(self,v1,v2):
        """ Return the difference of two vectors. """
        return (v1[0]-v2[0], v1[1]-v2[1], v1[2]-v2[2])

    def cross_product(self,v1,v2):
        #    """ Return the cross product of two vectors. """
        return (v1[1]*v2[2] - v1[2]*v2[1],
                        v1[2]*v2[0] - v1[0]*v2[2],
                        v1[0]*v2[1] - v1[1]*v2[0])

    # We don't need addition or dot product, but we're leaving the
    # code in here commented out just future reference, just in case.
    #
    #def add_vectors(v1,v2):
    #    """ Return the sum of two vectors. """
    #    return (v1[0]+v2[0], v1[1]+v2[1], v1[2]+v2[2])

    #def dot_product(v1,v2):
    #    """ Return the dot product of two vectors. """
    #    return v1[0]*v2[0] + v1[1]*v2[1] + v1[2]*v2[2]

    def shortest(self,a,b,p):
        """ Return the shortest distance between a point and a line. """
        AB = self.subtract_vectors(b,a);
        AC = self.subtract_vectors(p,a);
        area = self.magnitude(self.cross_product(AB,AC))
        try:
            CD = area/self.magnitude(AB)
        except ZeroDivisionError:
            CD = None
        return CD;

    def filter_points(self,points):
        """ Filter out points that are colinear. """
        cycles = 0
        original = 1
        filtered = 0
        while((cycles < self.MAX_FILTER_CYCLES) and (filtered < original)):
            last_point = points[0]
            for point in range(1,len(points)-2,2):
                d = self.shortest(last_point,points[point+1],points[point])
                if (d is not None) and (d < self.COLINEAR_DISTANCE):
                    points[point][3] = False
                else:
                    last_point = points[point]
            new_points = []
            for p in points:
                if p[3] == True:
                    new_points += [p]
            cycles += 1
            original = len(points)
            filtered = len(new_points)
            points = new_points
        return points

    def points_to_gcode(self,points):
        """ Generate G-code from a list of (x,y,z) coordinates. """
        points = self.filter_points(points)

        last_x = None
        last_y = None
        last_z = None
        gcode = ''
        for p in points:
            (x,y,z,include) = p
            if include:
                gc = ''
                if x != last_x:
                    gc += ' X{:.3f}'.format(x)
                if y != last_y:
                    gc += ' Y{:.3f}'.format(y)
                if z != last_z:
                    gc += ' Z{:.3f}'.format(z)
                gcode += 'G1{}\n'.format(gc)
                last_x = x
                last_y = y
                last_z = z
        return gcode

    def gcodify(self,pixels,x_width,z_depth,zero_x,zero_y,safe_z,
                feed_plunge,feed_carve,spindle_speed,
                offset_x,offset_y,offset_z,laser_mode,rescale=False):
        """ Turn a path's pixels into a G-code string.

        pixels: list of pixels walked by the path
        x_width,z_depth: dimension in mm
        zero_x,zero_y: zero point, in fraction, (0.5,0.5,1) is center

        """
        if len(pixels) == 0:
            return ('',None,None,None,None,None,None)
        mult = x_width/self.cols
        if rescale:
          zmin = self.min_z
          zmax = self.max_z
        else:
          zmin = 0
          zmax = 65535
        zmult = z_depth/(zmax - zmin)
        x0 = zero_x*x_width
        y0 = zero_x*x_width/self.cols*self.rows
        x = None
        y = None
        z = None
        last_x = None
        last_y = None
        last_z = None
        min_x = None
        max_x = None
        min_y = None
        max_y = None
        min_z = None
        max_z = safe_z + offset_z
        points = []

        gcode = '( Path Begin )\nG0 Z{:.5f}\n'.format(safe_z + offset_z)
        for p in pixels:
            try:
                value = self.pixels[p[1]][p[0]]
            except IndexError:
                #dump points[] to gcode
                gcode += self.gcodify_points(points,laser_mode,spindle_speed,
                                        feed_plunge,feed_carve,
                                        safe_z,offset_z)
                points = []
            else:
                x = p[0]*mult - x0 + offset_x
                y = (self.rows-p[1])*mult - y0 + offset_y
                z = (value-zmax)*zmult + offset_z
                points += [[x,y,z,True]]
                last_x = x
                last_y = y
                last_z = z
                min_x = x if ((min_x is None) or (x < min_x)) else min_x
                max_x = x if ((max_x is None) or (x > max_x)) else max_x
                min_y = y if ((min_y is None) or (y < min_y)) else min_y
                max_y = y if ((max_y is None) or (y > max_y)) else max_y
                min_z = z if ((min_z is None) or (z < min_z)) else min_z
                max_z = z if ((max_z is None) or (z > max_z)) else max_z
        #dump points[] to gcode
        gcode += self.gcodify_points(points,laser_mode,spindle_speed,
                                     feed_plunge,feed_carve,safe_z,offset_z)
        path_footer = ('( Bounds: X[{:.3f}:{:.3f}] Y[{:.3f}:{:.3f}] '
                       'Z[{:.3f}:{:.3f}] )\n( Path End )\n')
        gcode += path_footer.format(min_x,max_x,min_y,max_y,min_z,max_z)
        return (gcode,min_x,max_x,min_y,max_y,min_z,max_z)

    def gcodify_points(self,points,laser_mode,spindle_speed,
                       feed_plunge,feed_carve,safe_z,offset_z):
        """ Return G-code rendered from a list of points. """
        gcode = ''
        if len(points):
            segment_header = '( Path Segment )\nG0 X{:.3f} Y{:.3f}\n'
            gcode += segment_header.format(points[0][0],points[0][1])
            if laser_mode:
                segment_start = 'G0 Z{:.3f}\nM03 S{:.2f}\nG1 F{:.2f}\n'
                gcode += segment_start.format(points[0][2] + offset_z,
                                              spindle_speed,feed_carve)
            else:
                segment_start = 'G1 Z{:.3f} F{:.2f}\nG1 F{:.2f}\n'
                gcode += segment_start.format(points[0][2] + offset_z,
                                              feed_plunge,feed_carve)
            gcode += self.points_to_gcode(points)
            if laser_mode:
                gcode += 'M05\n'
            gcode += 'G0 Z{:.5f}\n'.format(safe_z + offset_z)
        return gcode

    def gcode_header(self,zero_x,zero_y,safe_z,
                     offset_x,offset_y,offset_z,laser_mode):
        """ Return the header lines for a gcode file. """
        gcode = '( Composed by PathTracer.py by Nathaniel Klumb )\n'
        gcode_header = ('( Heightmap: {} )\n( Pathmap: {} )\n'
                        '( Zeroes -- X:{} Y:{} Z:Stock Top )\n')
        gcode += gcode_header.format(self.heightmap,self.pathmap,
                                     zero_x,zero_y)
        if offset_x or offset_y or offset_z:
            offset_header = '( Offsets -- X:{} Y:{} Z:{} )\n'
            gcode += offset_header.format(offset_x,offset_y,offset_z)
        if laser_mode:
            gcode += '( Laser Mode )\n'
        gcode += 'G21 G90 G91.1\n'
        start_header = '( Start at X0,Y0,SAFE_Z )\nG0 X0 Y0 Z{:.3f}\n'
        gcode += start_header.format(safe_z+offset_z)
        return gcode

    def gcode_footer(self,min_x,max_x,min_y,max_y,min_z,max_z):
        """ Return the footer lines for a gcode file. """
        gcode_footer = ('( Job Bounds: X[{:.3f}:{:.3f}]{:.3f} '
                        'Y[{:.3f}:{:.3f}]{:.3f} Z[{:.3f}:{:.3f}]{:.3f} )\n'
                        '( Stop Spindle )\nM5\n( End )\nM30\n')
        return gcode_footer.format(min_x,max_x,max_x-min_x,
                                   min_y,max_y,max_y-min_y,
                                   min_z,max_z,max_z-min_z)

    def trace_paths(self,x_width,z_depth,zero_x,zero_y,safe_z,
                    feed_plunge,feed_carve,optimize,spindle_speed,
                    offset_x,offset_y,offset_z,laser_mode,
                    rescale_heightmap):
        """ Map the loaded paths onto the loaded heightmap. """
        if not self.ready():
            return False
        self.COLINEAR_DISTANCE = optimize
        min_x = None
        max_x = None
        min_y = None
        max_y = None
        min_z = None
        max_z = None
        gcode = self.gcode_header(zero_x,zero_y,safe_z,
                                  offset_x,offset_y,offset_z,laser_mode)
        if laser_mode:
            gcode += '( Spindle Speed: {} )\n'.format(spindle_speed)
        if rescale_heightmap:
            scale_factor, offset_factor = self.create_rescaled_heightmap()
            rescaled_file = '{}_rescaled_Z{:.3f}(-{:.3f})mm.png'
            outputpng_rescaled = \
                rescaled_file.format(splitext(self.heightmap)[0],
                                     z_depth * scale_factor,
                                     z_depth * offset_factor)
            self.write_png(self.rescaled,outputpng_rescaled)
        for p in self.parsed_paths:
            px = self.process_path(p)
            self.copy_path_pixels(px,rescale_heightmap)
            gc,minx,maxx,miny,maxy,minz,maxz = \
                self.gcodify(px,x_width,z_depth,zero_x,zero_y,safe_z,
                             feed_plunge,feed_carve,spindle_speed,
                             offset_x,offset_y,offset_z,laser_mode,
                             rescale_heightmap)
            gcode += gc
            min_x = minx if ((min_x is None) or (minx < min_x)) else min_x
            max_x = maxx if ((max_x is None) or (maxx > max_x)) else max_x
            min_y = miny if ((min_y is None) or (miny < min_y)) else min_y
            max_y = maxy if ((max_y is None) or (maxy > max_y)) else max_y
            min_z = minz if ((min_z is None) or (minz < min_z)) else min_z
            max_z = maxz if ((max_z is None) or (maxz > max_z)) else max_z
        gcode += self.gcode_footer(min_x,max_x,min_y,max_y,min_z,max_z)
        if self.outputpng is None:
            output_file = '{}_preview.png'
            self.outputpng = output_file.format(splitext(self.pathmap)[0])
        self.write_png(self.outpng,self.outputpng)
        if self.gcodefile is None:
            self.gcodefile = '{}_{}.nc'.format(splitext(self.pathmap)[0],
                                               self.COLINEAR_DISTANCE)
        with open(self.gcodefile,'w') as f:
            f.write(gcode)
        return True
