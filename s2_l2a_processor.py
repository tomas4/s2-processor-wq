#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sentinel-2 L2A Water Quality Preprocessing and Model Application Tool.
Converts SAFE format L2A data to multiband datasets, calculates masks/indices,
and applies chlorophyll-a prediction algorithms.
DEVNOTES:
* new metadata parsing needs testing (also with older data)
* create_img config switch should be implemented in the script [DONE]
* styles need verification/update for new bands, plus: add styles for 10m and 60m [DONE]
* implement relative (to script location) path to styles directory
NEW:
* 20260823 added function load_band_as_reflectance and applied in the functions working with band values
"""

import os
import sys
import re
import glob
import json
import shutil
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
from osgeo import gdal, osr

# Enable GDAL exceptions for error handling
gdal.UseExceptions()

# Band maps ordered numerically
BAND_MAP = {
    "10m": ["B02", "B03", "B04", "B08"],
    "20m": ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"],
    "60m": ["B01", "B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B09", "B11", "B12"]
}

def load_band_as_reflectance(
    band_path: str,
    band_idx: int = 1,
    offset: float = 0.0,
    quant_val: float = 10000.0,
) -> np.ndarray:
    """Load a specific band from a raster/VRT file and convert raw Digital Numbers (DN)

    to Surface Reflectance (0.0 to 1.0).

    Parameters:
        band_path (str): File path to the raster source or VRT.
        band_idx (int): Band index to read (1-based index, default is 1).
        offset (float): Radiometric BOA_ADD_OFFSET from Sentinel-2 metadata
          (e.g., -1000.0).
        quant_val (float): QUANTIFICATION_VALUE from Sentinel-2 metadata
          (default is 10000.0).

    Returns:
        np.ndarray: 2D array of float32 values representing surface reflectance.
    """
    dataset = gdal.Open(band_path)
    if not dataset:
        raise FileNotFoundError(f"Failed to open raster file: {band_path}")

    # Read the specified band array as float32 to prevent numerical overflow
    raw_dn = dataset.GetRasterBand(band_idx).ReadAsArray().astype(np.float32)

    # Convert DN to Surface Reflectance
    reflectance = (raw_dn + offset) / quant_val

    # Clip negative values to zero (e.g. shadows, deep water noise)
    reflectance = np.clip(reflectance, 0.0, None)

    return reflectance

def extract_safe_archive(input_path):
    """Unzips SAFE archive if a zip file is provided."""
    if os.path.isfile(input_path) and input_path.lower().endswith(".zip"):
        print(f"[INFO] Extracting archive: {input_path}")
        with zipfile.ZipFile(input_path, 'r') as zip_ref:
            zip_ref.extractall(os.path.dirname(input_path) or ".")
        extracted_dirs = [d for d in glob.glob("*.SAFE") if os.path.isdir(d)]
        if not extracted_dirs:
            raise FileNotFoundError("Could not find extracted .SAFE directory.")
        return extracted_dirs[0]
    elif os.path.isdir(input_path) and input_path.endswith(".SAFE"):
        return input_path
    else:
        raise ValueError(f"Invalid input path: {input_path}")

def parse_metadata(safe_dir):
    """
    Dynamically parses metadata from the MTD_MSIL2A.xml or MTD_TL.xml file
    inside the SAFE structure. Returns quantization, offset, tile and epsg.
    """
    # Look for the MTD_MSIL2A.xml file in the root of the SAFE directory
    mtd_path = None
    for root, dirs, files in os.walk(safe_dir):
        for file in files:
            if file.startswith("MTD_MSIL2A") and file.endswith(".xml"):
                mtd_path = os.path.join(root, file)
                break
        if mtd_path:
            break
            
    if not mtd_path or not os.path.exists(mtd_path):
        raise FileNotFoundError("Metadata file MTD_MSIL2A.xml not found in SAFE structure.")

    tree = ET.parse(mtd_path)
    root = tree.get_element() if hasattr(tree, 'get_element') else tree.getroot()

    # 1. Tile ID (eg. T33UWR)
    tile_elem = root.find(".//TILE_ID")
    tile_id = tile_elem.text.strip() if tile_elem is not None else None
    if tile_id and "_" in tile_id:
        # Exapmle: S2A_USER_MTD_L2AT_TL_SGS__20260814T151116_A038837_T33UWR_N05.12 -> vytáhneme T33UWR
        parts = tile_id.split('_')
        tile = [p for p in parts if p.startswith('T') and len(p) == 6][0]
    else:
        # Fallback from folder name
        tile = os.path.basename(safe_dir).split('_')[5] # podle konvence názvu S2 archivu

    # 2. EPSG code from coordinate system(např. 32633)
    epsg = extract_epsg_from_metadata(root, safe_dir)

    # 3. Quantification a offset
    quant_elem = root.find(".//QUANTIFICATION_VALUE")
    quantification = float(quant_elem.text.strip()) if quant_elem is not None else 10000.0

    # In XML, the element is listed, for example, as <BOA_ADD_OFFSET band_id="0">-1000</BOA_ADD_OFFSET>
    offset_elem = root.find(".//BOA_ADD_OFFSET")
    if offset_elem is None:
        # Fallback generic tag search without spaces
        offset_elem = root.find(".//RADIO_ADD_OFFSET")
        
    if offset_elem is not None and offset_elem.text:
        offset = float(offset_elem.text.strip())
    else:
        offset = 0.0  # For older baseline data < 04.00 the offset is 0
    print(f"[METADATA] Auto-detected Tile: {tile}, EPSG: {epsg}")
    return quantification, offset, tile, epsg

def extract_epsg_from_metadata(root, safe_dir):
    """
    Robust and universal detection of EPSG code from the SAFE structure without hard-coded constants.

    Detection cascade:
    1. Direct XML element: <HORIZONTAL_CS_CODE> (eg 'EPSG:32633')
    2. Legacy XML element: <HORIZONTAL_CS_NAME> (eg 'WGS84 / UTM zone 33N')
    3. Parsing from MGRS tile code (eg from 'T33UWR' -> zone 33 North -> EPSG 32633)
    """
    # Step 1: Newer XML structure (<HORIZONTAL_CS_CODE>)
    epsg_elem = root.find(".//HORIZONTAL_CS_CODE")
    if epsg_elem is not None and epsg_elem.text:
        text = epsg_elem.text.strip()
        if "EPSG:" in text:
            return int(text.split(":")[-1])
        elif text.isdigit():
            return int(text)

    # Step 2: Legacy XML structure (<HORIZONTAL_CS_NAME>)
    name_elem = root.find(".//HORIZONTAL_CS_NAME")
    if name_elem is not None and name_elem.text:
        # Příklad textu: "WGS84 / UTM zone 33N" nebo "WGS 84 / UTM Zone 33N"
        match = re.search(r"UTM\s+[Zz]one\s+(\d+)([NSns])", name_elem.text)
        if match:
            zone = int(match.group(1))
            hemisphere = match.group(2).upper()
            # EPSG pro WGS84 UTM North: 32600 + zone, South: 32700 + zone
            base_epsg = 32600 if hemisphere == "N" else 32700
            return base_epsg + zone

    # 3. Step: Derivation from MGRS Tile ID (eg T33UWR)
    # We look for the tile in XML or from the name of the SAFE folder
    tile_elem = root.find(".//TILE_ID")
    tile_code = tile_elem.text.strip() if tile_elem is not None and tile_elem.text else safe_dir
    
    # We find the MGRS pattern in the string (eg 33UWR)
    mgrs_match = re.search(r"T(\d{2})([C-X]{1})[A-Z]{2}", tile_code)
    if mgrs_match:
        zone = int(mgrs_match.group(1))
        band_letter = mgrs_match.group(2).upper()
        # In MGRS, bands 'N' and above are in the Northern Hemisphere (excluding special poles)
        is_north = band_letter >= "N"
        base_epsg = 32600 if is_north else 32700
        return base_epsg + zone

    raise ValueError(f"[CHYBA] Nepodařilo se automaticky určit EPSG kód z metadat v: {safe_dir}")

def get_datetime_strings(safe_dir):
    """Extracts xDATETIME and xDATE placeholders from SAFE directory name."""
    basename = os.path.basename(os.path.normpath(safe_dir))
    match = re.search(r"\d{8}T\d{6}", basename)
    if match:
        xdatetime = match.group(0)
        xdate = xdatetime.split("T")[0]
        return xdatetime, xdate
    raise ValueError(f"Could not parse timestamp from SAFE folder name: {basename}")

def locate_band_file(granule_dir, band, resolution):
    """Locates the JP2 file corresponding to a specific band and resolution."""
    # Search in target resolution folder first
    pattern = os.path.join(granule_dir, "IMG_DATA", f"R{resolution}", f"*_{band}_{resolution}.jp2")
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    
    # Fallback search across all resolution directories
    fallback_pattern = os.path.join(granule_dir, "IMG_DATA", "R*", f"*_{band}_*.jp2")
    fallback_matches = glob.glob(fallback_pattern)
    if fallback_matches:
        return fallback_matches[0]
        
    raise FileNotFoundError(f"Band file for {band} ({resolution}) not found in {granule_dir}")

def build_multiband_dataset(safe_dir, tile, epsg, resolution, bname, quantification, offset, create_img):
    """Creates VRT and IMG multiband rasters with proper band naming and sorting."""
    res_str = f"{resolution}m"
    target_bands = BAND_MAP[res_str]
    granule_dirs = glob.glob(os.path.join(safe_dir, "GRANULE", f"*{tile}*"))
    
    if not granule_dirs:
        raise FileNotFoundError(f"Granule for tile {tile} not found.")
    
    granule_dir = granule_dirs[0]
    source_files = [locate_band_file(granule_dir, b, res_str) for b in target_bands]

    vrt_name = f"{bname}_{res_str}.vrt"
    img_name = f"{bname}_{res_str}.img"

    # Build VRT
    # We select the second file as reference (index 1) to avoid 60m B01 for 20m data
    ref_index = 1 if len(source_files) > 1 else 0
    ref_file = source_files[ref_index]

    # We open the reference file and load its exact dimensions and geotransformation
    ds_ref = gdal.Open(ref_file)
    width = ds_ref.RasterXSize
    height = ds_ref.RasterYSize
    gt = ds_ref.GetGeoTransform()
    ds_ref = None # zavřít dataset

    # We create a VRT with an explicit resolution and dimension taken from a real data source
    vrt_opts = gdal.BuildVRTOptions(
        srcNodata=0,
        VRTNodata=0,
        outputSRS=f"EPSG:{epsg}",
        separate=True,
        xRes=gt[1],  # Přesné rozlišení X z referenčního souboru (např. 20.0)
        yRes=abs(gt[5]), # Přesné rozlišení Y (kladná hodnota pro rozlišení)
        resolution="user"
    )

    gdal.BuildVRT(vrt_name, source_files, options=vrt_opts)
    print(f"[SUCCESS] Created dataset: {vrt_name} ({width}x{height}px)")

    # Apply scaling and band descriptions to VRT
    ds_vrt = gdal.Open(vrt_name, gdal.GA_Update)
    scale_factor = 1.0 / quantification
    offset_factor = offset / quantification

    for idx, band_name in enumerate(target_bands, start=1):
        band = ds_vrt.GetRasterBand(idx)
        band.SetDescription(band_name)
        band.SetScale(scale_factor)
        band.SetOffset(offset_factor)
    ds_vrt = None

    # Convert VRT to IMG (HFA)
    if create_img:
        trans_opts = gdal.TranslateOptions(format="HFA", outputType=gdal.GDT_UInt16, creationOptions=["COMPRESSED=YES"])
        gdal.Translate(img_name, vrt_name, options=trans_opts)
        # Set band descriptions in target IMG file
        ds_img = gdal.Open(img_name, gdal.GA_Update)
        for idx, band_name in enumerate(target_bands, start=1):
            ds_img.GetRasterBand(idx).SetDescription(band_name)
        ds_img = None
        print(f"[SUCCESS] Created dataset: {img_name}")
    return vrt_name, img_name

def generate_masks_and_indices(
    safe_dir: str,
    tile: str,
    xdatetime: str,
    offset: float,
    quant_val: float,
    max_water_rf_b11: float,
    use_scl_filter: bool,
) -> tuple[str, str]:
    """Generates MNDWI, SCL Cloud Mask, and SCL-Filtered Water Mask rasters.

    Parameters:
        safe_dir (str): Path to the input Sentinel-2 SAFE directory.
        tile (str): Tile identifier (e.g., T33UVR).
        xdatetime (str): Full acquisition timestamp string.
        offset (float): Radiometric BOA_ADD_OFFSET from metadata.
        quant_val (float): QUANTIFICATION_VALUE from metadata.
        max_water_rf_b11 (float): Maximum SWIR1 reflectance threshold for water filtering.
        use_scl_filter (bool): Flag to enable/disable Scene Classification Layer filtering.

    Returns:
        tuple[str, str]: File paths to generated MNDWI and water mask rasters.
    """
    bname = f"{tile}_{xdatetime}"
    vrt_20m_path = f"{bname}_20m.vrt"

    # Open VRT to retrieve georeferencing info and dimensions
    ds_20m = gdal.Open(vrt_20m_path)
    if not ds_20m:
        raise FileNotFoundError(f"Failed to open 20m VRT file: {vrt_20m_path}")

    geo_transform = ds_20m.GetGeoTransform()
    projection = ds_20m.GetProjection()
    x_size = ds_20m.RasterXSize
    y_size = ds_20m.RasterYSize
    ds_20m = None  # Close handle

    # Load Green (B03) and SWIR1 (B11) as reflectance (0.0 - 1.0)
    # 20m VRT band order: B01(1), B02(2), B03(3), B04(4), B05(5), B06(6), B07(7), B08(8), B8A(9), B11(10), B12(11)
    b03_refl = load_band_as_reflectance(
        vrt_20m_path, band_idx=3, offset=offset, quant_val=quant_val
    )
    b11_refl = load_band_as_reflectance(
        vrt_20m_path, band_idx=10, offset=offset, quant_val=quant_val
    )

    # 1. MNDWI Calculation: (Green - SWIR1) / (Green + SWIR1)
    mndwi = (b03_refl - b11_refl) / (b03_refl + b11_refl + 1e-6)

    # Write MNDWI Raster
    driver_hfa = gdal.GetDriverByName("HFA")
    mndwi_file = f"{bname}_mndwi_20m.img"
    ds_mndwi = driver_hfa.Create(
        mndwi_file, x_size, y_size, 1, gdal.GDT_Float32, ["COMPRESSED=YES"]
    )
    ds_mndwi.SetGeoTransform(geo_transform)
    ds_mndwi.SetProjection(projection)
    ds_mndwi.GetRasterBand(1).WriteArray(mndwi)
    ds_mndwi = None
    print(f"[SUCCESS] Created MNDWI: {mndwi_file}")

    # 2. SCL Processing (Cloud & Water Masking)
    granule_dirs = glob.glob(os.path.join(safe_dir, "GRANULE", f"*{tile}*"))
    if not granule_dirs:
        raise FileNotFoundError(f"Granule directory for tile {tile} not found.")

    scl_matches = glob.glob(
        os.path.join(granule_dirs[0], "IMG_DATA", "R20m", "*_SCL_20m.jp2")
    )
    if not scl_matches:
        raise FileNotFoundError("SCL 20m raster not found.")

    ds_scl = gdal.Open(scl_matches[0])
    scl_arr = ds_scl.ReadAsArray()
    ds_scl = None

    # Cloud Mask: 1 for valid pixels, 0 for cloud/shadow/cirrus
    # SCL values: 3 (cloud shadow), 8 (cloud medium prob), 9 (cloud high prob), 10 (thin cirrus)
    cloud_mask = np.where(np.isin(scl_arr, [3, 8, 9, 10]), 0, 1).astype(np.uint8)

    cloud_file = f"{bname}_cloud_mask_20m.img"
    ds_cloud = driver_hfa.Create(
        cloud_file, x_size, y_size, 1, gdal.GDT_Byte, ["COMPRESSED=YES"]
    )
    ds_cloud.SetGeoTransform(geo_transform)
    ds_cloud.SetProjection(projection)
    ds_cloud.GetRasterBand(1).WriteArray(cloud_mask)
    ds_cloud = None
    print(f"[SUCCESS] Created Cloud Mask: {cloud_file}")

    # 3. Water Mask Logic (MNDWI > 0.1 AND B11 < Threshold AND cloud_mask == 1)
    water_condition = (
        (mndwi > 0.1) & (b11_refl < max_water_rf_b11) & (cloud_mask == 1)
    )
    if use_scl_filter:
        water_condition = water_condition & (scl_arr == 6)  # SCL 6 = Water

    water_mask = np.where(water_condition, 1, 0).astype(np.uint8)

    water_file = f"{bname}_water_mask_20m.img"
    ds_water = driver_hfa.Create(
        water_file, x_size, y_size, 1, gdal.GDT_Byte, ["COMPRESSED=YES"]
    )
    ds_water.SetGeoTransform(geo_transform)
    ds_water.SetProjection(projection)
    ds_water.GetRasterBand(1).WriteArray(water_mask)
    ds_water = None
    print(
        f"[SUCCESS] Created Water Mask (SCL Filtered={use_scl_filter}): {water_file}"
    )

    return mndwi_file, water_file

def run_recipe_model(
    recipe_path: str,
    tile: str,
    xdatetime: str,
    xdate: str,
    offset: float = 0.0,
    quant_val: float = 10000.0,
) -> str:
    """Executes model equation recipe using evaluated NumPy expressions on surface reflectance

    data and saves the output as an ERDAS Imagine (.img) raster.
    """
    with open(recipe_path, "r") as f:
        recipe = json.load(f)

    raw_out_name = recipe["output_filename"].format(
        xDATE=xdate, xDATETIME=xdatetime, TILE=tile
    )
    out_filename = os.path.splitext(raw_out_name)[0] + ".img"

    loaded_bands = {}
    geo_transform = None
    projection = None
    x_size, y_size = 0, 0

    for var_name, var_info in recipe["inputs"].items():
        fname = var_info["file"].format(
            xDATE=xdate, xDATETIME=xdatetime, TILE=tile
        )
        band_num = var_info.get("band", 1)

        # Retrieve georeferencing metadata from the first input file
        if geo_transform is None:
            ds_ref = gdal.Open(fname)
            if not ds_ref:
                raise FileNotFoundError(f"Failed to open input raster: {fname}")
            geo_transform = ds_ref.GetGeoTransform()
            projection = ds_ref.GetProjection()
            x_size = ds_ref.RasterXSize
            y_size = ds_ref.RasterYSize
            ds_ref = None

        # Check if the input file is a binary mask (.img) or optical band (.vrt/.jp2)
        if fname.lower().endswith(".img") or "mask" in fname.lower():
            # Load masks directly as raw numpy array (integers/floats without radiometric correction)
            ds_mask = gdal.Open(fname)
            if not ds_mask:
                raise FileNotFoundError(f"Failed to open mask raster: {fname}")
            loaded_bands[var_name] = ds_mask.GetRasterBand(band_num).ReadAsArray().astype(np.float32)
            ds_mask = None
        else:
            # Load optical bands as physical surface reflectance (0.0 - 1.0)
            loaded_bands[var_name] = load_band_as_reflectance(
                band_path=fname,
                band_idx=band_num,
                offset=offset,
                quant_val=quant_val,
            )

    # Evaluate equation formula in local environment context
    eval_env = {**loaded_bands, "np": np}
    result_array = eval(recipe["formula"], {}, eval_env)

    # Output ERDAS Imagine (.img) creation using HFA driver
    driver_hfa = gdal.GetDriverByName("HFA")
    ds_out = driver_hfa.Create(out_filename, x_size, y_size, 1, gdal.GDT_Float32)
    ds_out.SetGeoTransform(geo_transform)
    ds_out.SetProjection(projection)

    band_out = ds_out.GetRasterBand(1)
    band_out.WriteArray(result_array)
    band_out.SetNoDataValue(np.nan)

    ds_out = None

    print(f"[SUCCESS] Applied Model Algorithm. Output: {out_filename}")
    return out_filename

def apply_qml_styles(tile, xdatetime, xdate, config, output_dir="."):
    """
    Copies predefined QML files alongside output geospatial files in the target directory.
    Reads 'style_dir' and 'styles' mapping from the configuration.
    """
    style_map = config.get("styles", {})
    style_dir = config.get("style_dir", "styles")  # Defaults to "styles" subfolder if omitted

    for pattern_key, style_filename in style_map.items():
        # Replace placeholders in key name
        resolved_key = pattern_key.replace("{xDATE}", xdate).replace("{xDATETIME}", xdatetime).replace("{TILE}", tile)
        raster_name = f"{tile}_{xdatetime}_{resolved_key}" if not resolved_key.startswith("chla_") else resolved_key

        # Output QML file path (placed in current working directory alongside output rasters)
        target_qml = os.path.join(output_dir, os.path.splitext(raster_name)[0] + ".qml")

        # Determine source QML file path
        if os.path.isabs(style_filename):
            source_qml_path = style_filename
        else:
            source_qml_path = os.path.join(style_dir, style_filename)

        # Perform file copy if style exists
        if os.path.exists(source_qml_path):
            shutil.copy(source_qml_path, target_qml)
            print(f"[STYLE] Applied {source_qml_path} -> {target_qml}")
        else:
            print(f"[WARNING] Style preset not found: {source_qml_path}")

def main():
    if len(sys.argv) < 2:
        print("Usage: python s2_l2a_processor.py <path_to_SAFE_or_zip> [config.json] [recipe.json]")
        sys.exit(1)

    input_path = sys.argv[1]
    
    # We will find the absolute path to the directory where this Python script resides
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # 1. Processing the path to the configuration file
    if len(sys.argv) > 2:
        config_path = sys.argv[2]
        if not os.path.exists(config_path):
            alt_path = os.path.join(script_dir, config_path)
            if os.path.exists(alt_path):
                config_path = alt_path
    else:
        local_config = "config.json"
        script_config = os.path.join(script_dir, "config.json")
        
        if os.path.exists(local_config):
            config_path = local_config
        else:
            config_path = script_config

    print(f"[INFO] Loading configuration from: {config_path}")
    with open(config_path, 'r') as f:
        config = json.load(f)

    # 2. Recipe path processing (same robust logic)
    if len(sys.argv) > 3:
        recipe_path = sys.argv[3]
        if not os.path.exists(recipe_path):
            alt_path = os.path.join(script_dir, recipe_path)
            if os.path.exists(alt_path):
                recipe_path = alt_path
    else:
        local_recipe = "recipe.json"
        script_recipe = os.path.join(script_dir, "recipe.json")

        if os.path.exists(local_recipe):
            recipe_path = local_recipe
        else:
            recipe_path = script_recipe

    print(f"[INFO] Loading recipe from: {recipe_path}")

    # The rest of processing...
    safe_dir = extract_safe_archive(input_path)
    xdatetime, xdate = get_datetime_strings(safe_dir)
    quantification, offset, tile, epsg = parse_metadata(safe_dir)
    bname = f"{tile}_{xdatetime}"

    # 1. Build Multiband Rasters
    for res in [10, 20, 60]:
        build_multiband_dataset(safe_dir, tile, epsg, res, bname, quantification, offset, config['create_img'])

    # 2. Build Masks & Indices
    mndwi_path, water_mask_path = generate_masks_and_indices(
        safe_dir=safe_dir,
        tile=tile,
        xdatetime=xdatetime,
        offset=offset,
        quant_val=quantification,
        max_water_rf_b11=config["max_water_rf_b11"],
        use_scl_filter=config["use_scl_water_filter"],
    )

    # 3. Apply Water Quality Model
    out_img = run_recipe_model(recipe_path, tile, xdatetime, xdate, offset, quantification)

    # 4. Copy QML Presets
    apply_qml_styles(tile, xdatetime, xdate, config)
    
if __name__ == "__main__":
    main()
