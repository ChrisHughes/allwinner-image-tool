# Allwinner Image Tools
Utility to modify Allwinner firmware images. This set of tools can be used to modify wallpapers, boot logos and other firmware assets in F133 / D1s based car radios such as those from SJoyBring, MELIS and PLZ.

## The tools are as follows:
**allwinner_imagewty.py** - Extract and replace disk images from ImageWTY firmware bundles.

**allwinner_minfs.py** - List, extract and replace files in a MinFS disk image.

**image_tool.py** - Re-encode jpg images into a known-compatible format.

## The following steps demonstrate how to use the tools:

### Step 1: Extract the user data disk image from your firmware bundle.
`python ./allwinner_imagewty.py update/LTTF133.img --list`

`python ./allwinner_imagewty.py update/LTTF133.img --extract data_udisk.fex --verbose`

### Step 2: Identify and optionally extract your files to replace.
`python ./allwinner_minfs.py data_udisk.fex --list`

`python ./allwinner_minfs.py data_udisk.fex --extract 0.jpg`

### Step 3: Re-encode each jpg image into a compatible format.
Optional, but recommended for logo / boot images.

`python ./image_tool.py logo0.jpg logo0.jpg`

### Step 4: Replace a file in the disk image.
`python ./allwinner_minfs.py data_udisk.fex --replace 0.jpg 0.jpg --output data_udisk.fex`

### Step 5: Repackage the disk image into the firmware bundle.
`python ./allwinner_imagewty.py update/LTTF133.img --verbose --replace data_udisk.fex data_udisk.fex`

## Additional notes

- It is recommended to replace images with images of the exact same resolution.
- When setting boot images (called logos in some cases), these are read and interpreted by the MCU, not the application. The expected format for the jpeg is very strict, otherwise the image will fail to load. Use image_tool.py to re-encode these and make them work.
- As the firmware bundle's disk image checksum is not updated, the update will loop and retry indefinitely, despite succeeding. Just wait until the first loop then power off the device, unplug the USB drive and power it on again to see the new firmware.

## Command line arguments

### allwinner_imagewty.py

`allwinner_imagewty.py <file> <actions>`

|||
|--------|-------|
|`--list`| Lists all disk images in the firmware bundle. |
|`--verbose`| Enables verbose output. |
|`--extract <name>`| Extracts disk image by name. Filename will be same as internal disk name. |
|`--replace <name> <filename>`| Replaces disk image by name with the contents of file. File length must match original.|
|`--output <filename>`| Optionally specify the output of extract function. When used with replace function, it overrides the default naming (\<original name\>.modified) of the new firmware bundle. |

### allwinner_minfs.py

`allwinner_minfs.py <file> <actions>`

|||
|--------|-------|
|`--list`| Lists all files in the disk image. |
|`--verbose`| Enables verbose output. |
|`--extract <name>`| Extracts file name. Filename will be same as internal file name. |
|`--replace <name> <filename>`| Replaces file by name with the contents of file. |
|`--output <filename>`| Optionally specify the filename of the modified disk image when using replace function. The default is (\<original name\>.modified). |



## Note

This tool is provided without warranty. You are on your own if you brick your device.