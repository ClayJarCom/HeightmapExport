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
    
