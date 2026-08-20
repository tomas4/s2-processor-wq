@echo off
setlocal enableextensions

:: ==============================================================================
:: CONFIGURATION
:: ==============================================================================
set "PYTHON_SCRIPT=C:\Users\tobr0222\ownCloud\Dropbox\scripts\dev_python\L2A_WQ\s2_l2a_processor.py"

:: 1. Check if the main Python script exists
if not exist "%PYTHON_SCRIPT%" goto err_no_script

:: 2. Detect OSGeo4W / QGIS installations
set "TARGET_OSGEO="
if defined OSGEO4W_ROOT if exist "%OSGEO4W_ROOT%\bin\o4w_env.bat" set "TARGET_OSGEO=%OSGEO4W_ROOT%"
if not defined TARGET_OSGEO if exist "%LOCALAPPDATA%\Programs\OSGeo4W\bin\o4w_env.bat" set "TARGET_OSGEO=%LOCALAPPDATA%\Programs\OSGeo4W"
if not defined TARGET_OSGEO if exist "C:\OSGeo4W\bin\o4w_env.bat" set "TARGET_OSGEO=C:\OSGeo4W"
if not defined TARGET_OSGEO if exist "C:\OSGeo4W64\bin\o4w_env.bat" set "TARGET_OSGEO=C:\OSGeo4W64"

:: 3. Load OSGeo4W environment if found
if not defined TARGET_OSGEO goto no_osgeo

echo [INFO] Detected OSGeo4W installation at: %TARGET_OSGEO%
set "OSGEO4W_ROOT=%TARGET_OSGEO%"
call "%TARGET_OSGEO%\bin\o4w_env.bat" >nul 2>&1
goto check_gdal

:no_osgeo
echo [WARN] OSGeo4W / QGIS installation not found in standard paths.

:check_gdal
:: 4. Verify that GDAL is ready in the environment
python -c "import osgeo.gdal" >nul 2>&1
if errorlevel 1 goto err_no_gdal

:: 5. Execute main Python script and pass ALL arguments directly (%*)
echo [INFO] Environment ready. Launching Python script...
python "%PYTHON_SCRIPT%" %*
goto end_script

:: ==============================================================================
:: ERROR HANDLERS & LABELS
:: ==============================================================================
:err_no_script
echo [ERROR] Python script not found at: %PYTHON_SCRIPT%
exit /b 1

:err_no_gdal
echo =========================================================================
echo [ERROR] GDAL (osgeo) module is not available in Python!
echo =========================================================================
exit /b 1

:end_script
endlocal