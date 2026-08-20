# Sentinel-2 L2A Processor & Water Quality Analysis Toolkit

## Overview
This tool automates the extraction, multiband raster creation, seected L3 products creation, cloud/water masking, and empirical model execution (e.g., Chlorophyll-a estimation) from Sentinel-2 L2A `.SAFE` image products.

## Features
- **Pure Python Implementation**: Replaces legacy GDAL CLI tools with native `osgeo.gdal` and `numpy` bindings.
- **Ordered Multiband Export**: Includes Band 1 and Band 8 in 20m datasets, sorting all bands numerically (`B01, B02, ..., B08, B8A, B11, B12`).
- **Refined SCL Water Filter**: Default water mask combines MNDWI thresholding ($>0.1$), Band 11 upper boundary checking, and SCL class verification (SCL = 6).
- **Template Placeholder Substitution**: Automatically substitutes `{xDATETIME}` and `{xDATE}` across recipe workflows.
- **QML Style Distribution**: Automatically links `.qml` visual style presets to created datasets.

## Dependencies & Installation

### Requirements
- Python 3.8+
- GDAL Python bindings (`osgeo.gdal`)
- NumPy (`numpy`)

### Installation Commands

#### Linux (Ubuntu/Debian)
```
python
bash
sudo apt update
sudo apt install python3-gdal python3-numpy
```
#### macOS (via Homebrew)
```
brew install gdal
pip3 install numpy gdal
```

#### Windows (via OSGeo4W or Anaconda)
Using OSGeo4W Shell:

```
osgeo4w-setup.exe
```

Or via Conda:

```
conda install -c conda-forge gdal numpy
```

### Usage
1. Create a project directory and place `s2_l2a_processor.py`, `config.json`, `chl_a_recipe_template.json`, and `README.md` inside it.
2. Ensure you have a `styles/` subfolder containing your target QML styling files (`s2_20m.qml`, `cloud_mask.qml`, `water_mask.qml`, `chla_tbdo1.qml`)[cite: 1, 4, 5]. 
3. Edit the .json files to include styles or modify the formula 
4. Run the script against one of your `.SAFE` folders or `.zip` archives:
```
python s2_l2a_processor.py /path/to/S2B_MSIL2A_20250613T100029...SAFE [config.json] [chl_a_recipe_template.json]
```

#### Where Output Files Are Created

The Python script (s2_l2a_processor.py) creates all output files in the current working directory (the directory from which you execute the python command in your terminal/command line).

When you run the command from a folder (e.g., cd /path/to/project && python s2_l2a_processor.py ...), the script uses relative paths for saving the rasters:

**Multiband Rasters (10m, 20m, 60m):**

Saved directly in your current working directory.

Filenames: {TILE}_{xDATETIME}_10m.img, {TILE}_{xDATETIME}_20m.img, {TILE}_{xDATETIME}_60m.img (along with their corresponding .vrt files).

**Generated Masks & Indices:**

Saved in your current working directory.

Filenames: {TILE}_{xDATETIME}_mndwi_20m.img, {TILE}_{xDATETIME}_cloud_mask_20m.img, {TILE}_{xDATETIME}_water_mask_20m.img.

**Model Output Raster (Chlorophyll-a):**

Saved in your current working directory as defined by the recipe template.

Filename: chla_{xDATE}_TBDO1_2023.tif.

**Style Files (.qml):**

        Copied directly alongside each generated raster in your current working directory, using matching base filenames so QGIS auto-detects them.

#### Cross-Platform Notes
1. **Path Separators:** Standardized using os.path.join for cross-platform compatibility across Windows backslashes (\\) and UNIX forward slashes (/).
2. **GDAL Drivers:** Uses standard HFA (.img) and GTiff (.tif) drivers supported identically across all operating systems.


