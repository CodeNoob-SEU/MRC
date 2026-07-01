# Vendor Runtime Files

This directory is committed so the project can be cloned and tested on another Windows machine without depending on the original source folders.

Expected runtime layout:

- `camera/x64/DXMediaCap.dll` and related camera SDK DLLs
- camera SDK `.ini`, `.config`, and `.lib` files from the x64 demo folder
- camera SDK x64 demo executables for runtime verification
- `camera/win32/` with the 32-bit vendor demo and SDK runtime
- `camera/include/DXMediaCap.h`
- `camera/include/datastru.h`
- `daq/x64/USB3000.dll`
- `daq/x64/USB3000.lib`
- `daq/x86/USB3000.dll`
- `daq/x86/USB3000.lib`
- `daq/include/USB3000.h`

The Python backend defaults to these paths. You can override them with:

- `MRC_DXMEDIA_DLL`
- `MRC_USB3000_DLL`
- `MRC_VENDOR_ARCH` (`x64` or `win32`)
