# Sentinel-2 L2A Processor & Water Quality Toolkit (`s2-processor-wq`)

A Python-based workflow with CLI wrapper support for processing Sentinel-2 L2A `.SAFE` image products (both `.zip` archives and extracted directories). The toolkit automates GIS pre-processing, multiband raster creation, spectral index calculation (L3 products), cloud/water masking, and empirical water quality model execution (e.g., Chlorophyll-a estimation). The outputs should be supported by most modern desktop GIS platforms, but are tested in [QGIS](https://qgis.osgeo.org) specifically.

---

## 🔑 Key Features

* **Autonomous Metadata Parsing**: Dynamically extracts Tile ID, Spatial Reference (EPSG), Quantification Value, and BOA Radiometric Offset directly from `MTD_MSIL2A.xml` inside the `.SAFE` package. No manual entry required.
* **Native Grid Preservation**: Uses native 20m band geometry as a spatial template to eliminate pixel shift, half-pixel offsets, and artificial resamplings.
* **Automated L2 & L3 Product Generation**:
  * **Multiband Rasters**: Numerically sorted spectral bands exported to ERDAS Imagine (`.img`) and Virtual Raster (`.vrt`) files for 10m, 20m, and 60m resolutions (`{TILE}_{DATETIME}_20m.img`).
  * **Modified Normalized Difference Water Index (MNDWI)**: High-resolution water surface highlighting (`{TILE}_{DATETIME}_mndwi_20m.img`).
  * **Cloud & Shadow Mask**: Binary mask isolating clouds and atmospheric noise (`{TILE}_{DATETIME}_cloud_mask_20m.img`).
  * **Refined Water Surface Mask**: Multi-criteria water extraction combining MNDWI thresholding ($>0.1$), SWIR (B11) upper boundary checks, and SCL verification (`{TILE}_{DATETIME}_water_mask_20m.img`).
  * **Water Quality Model (L3 Chlorophyll-a)**: Final concentration GeoTIFF calculated via configurable recipe templates (`chla_{xDATE}_TBDO1_2023.tif`).
* **QGIS Style Integration**: Automatically copies and matches `.qml` visual style presets to generated datasets for immediate rendering in QGIS.

---

## ⚙️ Configuration (`config.json`)

Geographic parameters (`tile`, `epsg`) are auto-detected from dataset metadata. The `config.json` file focuses purely on water classification thresholds and QGIS styling paths:

```json
{
  "max_water_rf_b11": 500,
  "use_scl_water_filter": true,
  "style_dir": "C:/Users/tobr0222/ownCloud/Dropbox/scripts/dev_python/L2A_WQ/styles/",
  "styles": {
    "20m.img": "styles/S2A-L2A_20m_REF_11-6-2.qml",
    "cloud_mask_20m.img": "styles/mask-clouds-0gray-1nothing.qml",
    "water_mask_20m.img": "styles/mask-water-1azure-0nothing.qml",
    "chla_{xDATE}_TBDO1_2023.tif": "styles/chlorofyl0-60-600_BCGYRM.qml"
  }
}
```

### Parameter Description:
* `max_water_rf_b11`: Upper reflectance threshold for Band 11 (SWIR) used during water masking (automatically offset-corrected).
* `use_scl_water_filter`: Boolean flag (`true`/`false`) toggling SCL layer verification (SCL = 6 for water).
* `style_dir`: Absolute or relative path to the directory containing `.qml` style templates.
* `styles`: Mapping dictionary linking generated raster filenames to their corresponding `.qml` style presets.

---

## 🚀 Execution & Usage

Cross-platform wrapper scripts are provided to execute the pipeline without manually activating virtual environments or navigating OSGeo4W shells.

### 1. Windows Execution (`L2A_WQ_processor_win.cmd`)
The Windows batch wrapper automatically detects local OSGeo4W / QGIS installations, sets up GDAL environment variables, and executes the Python script.

```cmd
L2A_WQ_processor_win.cmd <path_to_SAFE_or_ZIP> [config.json] [recipe.json]
```

**Example:**
```cmd
L2A_WQ_processor_win.cmd S2A_MSIL2A_20260814T100041_N0512_R122_T33UWR_20260814T151116.SAFE.zip config.json
```

### 2. Linux / macOS Execution (`L2A_WQ_processor_bash.sh`)
The shell wrapper automatically activates a local Python virtual environment (`venv`) containing GDAL bindings and launches processing.

```bash
chmod +x L2A_WQ_processor_bash.sh
./L2A_WQ_processor_bash.sh <path_to_SAFE_or_ZIP> [config.json] [recipe.json]
```

### 3. Direct Python Execution
If your environment already has `osgeo.gdal` and `numpy` installed:

```bash
python s2_l2a_processor.py /path/to/S2A_MSIL2A_...SAFE [config.json] [recipe.json]
```

---

## 📁 Generated Output Files

All output rasters and their associated `.qml` style files are saved in the current working directory from which the command is executed:

| Output Filename | Format | Description |
| :--- | :--- | :--- |
| `{TILE}_{xDATETIME}_10m.img` `{TILE}_{xDATETIME}_10m.vrt` | ERDAS Imagine & Virtual Raster (Multiband) | 10m resolution bands (B02, B03, B04, B08) |
| `{TILE}_{xDATETIME}_20m.img` `{TILE}_{xDATETIME}_20m.vrt` | ERDAS Imagine & Virtual Raster (Multiband) | 20m resolution bands (B01–B08, B8A, B11, B12, numerically sorted) |
| `{TILE}_{xDATETIME}_60m.img` `{TILE}_{xDATETIME}_60m.vrt` | ERDAS Imagine & Virtual Raster (Multiband) | 60m resolution bands (B01–B08, B8A, B09 B11, B12, numerically sorted) |
| `{TILE}_{xDATETIME}_mndwi_20m.img` | Float32 Raster | MNDWI spectral index layer |
| `{TILE}_{xDATETIME}_cloud_mask_20m.img` | Binary Mask (0/1) | Cloud and cloud shadow mask |
| `{TILE}_{xDATETIME}_water_mask_20m.img` | Binary Mask (0/1) | Water surface mask |
| `chla_{xDATE}_TBDO1_2023.tif` | GeoTIFF (Float32) | Calculated Chlorophyll-a concentration map |
| `*.qml` | QGIS Style File | Auto-copied style files matching each output raster |

The Erdas imagine format rasters are created optionally, based on *create_img* setting in *config.json*. The Virtual Raster files point to the original .SAFE format directory for bands data; to keep them working, preserve the unpacked .SAFE directory at its original location. You can decide to keep either multiband .img files only (and delete .VRT files and the .SAFE directory when the script did its work), or generate only .vrt files and keep the .SAFE directory to save disk space. The Erdas Imagine .img format files should be more effective speed-wise, when moving around in the map in a GIS, the Virtual Raster .vrt & SAFE combination has the added benefit of keeping the original data with all its metadata and bands not used by the script. If you started with a zip archive of SAFE format data, the zip file can be safely deleted, when extracted by the script.

---

## 💻 Requirements & Dependencies

- **Python**: 3.8 or higher
- **GDAL**: `osgeo.gdal` Python bindings
- **NumPy**: `numpy`

### Cross-Platform Compatibility Notes
1. **Path Handling**: Utilizes `os.path` methods to ensure seamless switching between Windows backslashes (`\`) and UNIX forward slashes (`/`).
2. **GDAL Drivers**: Uses standard HFA (`.img`) and GTiff (`.tif`) drivers supported uniformly across Linux, Windows, and macOS.

## 🎯 Future Goals & Planned Features
In the next updates I would like to:
* Change the output chl-a estimate to Erdas Imagine format as well, to keep the formats uniform.
* Add .vrt and optional .img file for SCL (Scene Classification Layer) and possibly the other two auxiliary/derived bands
* Gradually add some more optionally generated generally usable Level-3 .img files, especially common vegetation, moisture, fire or other indices (NDVI, NDMI, NBR ...).
* Perhaps adding 10m multiband files with the same the band set as in the 20m resolution, the coarser resolution bands upscaled to finer resolution.