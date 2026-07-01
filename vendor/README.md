# Vendor Runtime Files

This directory is committed so the project can be cloned and tested on another Windows machine without depending on the original source folders.

Expected runtime layout:

- `camera/x64/DXMediaCap.dll` and related camera SDK DLLs
- `camera/include/DXMediaCap.h`
- `camera/include/datastru.h`
- `daq/x64/USB3000.dll`
- `daq/x64/USB3000.lib`
- `daq/include/USB3000.h`

The Python backend defaults to these paths. You can override them with:

- `MRC_DXMEDIA_DLL`
- `MRC_USB3000_DLL`

