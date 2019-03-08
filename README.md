# HeightmapExport
Heightmap Export plugin for QGIS

## Purpose
Heightmap Export was created to make it simple and straightforward to take a raster layer and export it to a 16-bit PNG heightmap suitable for loading into various applications to create local terrain relief models in high resolution via CNC.

## Usage
1. Load a raster layer, e.g. USGS DEM data.
2. If desired, use the clipper tool to extract just a section of raster data into a new layer.
3. Launch the Heightmap Export plugin.
4. Choose the raster layer to export.
    * The dimensions of the selected layer, in meters, will be displayed.
    * Heightmap Export uses the ratio of the north/south and east/west distances across the center point to automatically adjust the aspect ratio of the output.  (This is a reasonable assumption for the local terrain relief models for which this plugin in intended.)
5. Set your model dimensions.
    * Entering a height, width, or depth will automatically calculate the rest, to scale.
    * If you would like to compress or exaggerate the depth, enter a scaled depth or a scale factor.
    * **Note:** If you just want a heightmap image without any intention of making a model, you can skip this section entirely.  It's just a convenient calculator for getting the model dimensions.
6. Set your image dimensions.
    * Set your image height or width, and the other will be calculated, to scale.
    * Or set your desired physical resolution (model mm/image pixel), and the height and width will be calculated.
7. Export your heightmap.
    * You will be asked where to save your 16-bit PNG.
    
## PathTracer
With version 0.5.0, Heightmap Export not only supports both QGIS 2 and QGIS 3 with the same packaged plugin, but it also adds a new PathTracer dialog.  PathTracer allows you to take a heightmap (such as one exported by Heightmap Export) and map the paths from an SVG file onto it in order to generate G-code to engrave those paths onto a physical relief model.  It's not the most sophisticated code ever, but it has already been used to make some amazing laser-engraved hiking trails on CNC carved terrain relief models.

The PathTracer dialog is mostly straightforward for anyone who is working with CAM software to carve relief models from heightmaps, but there are a few interesting bits:

* If you have a heightmap that you want to use just a section to make your model:
    1. Manipulate your heightmap with any image software (and be sure your paths overlay properly).
    2. Put the new X width and Y height in the CAM Parameters fields.
    3. Put the *original* Z depth in that field.
    4. Check "Rescale Heightmap to full range and save new PNG."
    5. When you export your G-code, a new file will be created with the values scaled to full range, and the filename will include the new Z depth (and the offset from the original top).
* When you check "Enable Laser Mode", several changes are made:
    1. Plunges will be made at rapid motion speed with the laser off.
    2. Power is set (via "spindle speed") to the scaled percentage according to the $30 (Maximum Spindle Speed) and $31 (Minimum Spindle Speed) values you enter.
* If you check "Enable Offsets", the G-code will be shifted by the offsets you enter.
    * If your spindle is at X0 Y0, and to make your laser land on that point, you need to jog the machine to X-50 Y45, you'd enter "-50" as your X offset and 45 as your Y offset.
* "Optimize" is a very rudimentary optimization algorithm that discards points in the G-code based on how far they are off a line between neighboring points.  There is room for improvement here, but if you put in something like your step size, you can shave the G-code down quite a bit.  Play around with it and see what you get, and if you're skilled in path optimization concepts... the codebase awaits.
