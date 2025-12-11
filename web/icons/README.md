# GLaDOS PWA Icons

This directory should contain the following icon files for PWA installation:

- `icon-192.png` - 192x192 pixel icon
- `icon-512.png` - 512x512 pixel icon

## Generating Icons

### Option 1: Using the provided script (requires Pillow)

```bash
pip install Pillow
python3 ../scripts/generate_icons.py
```

### Option 2: Manual creation

Create two PNG files with:
- Black background (#000000)
- Orange circle (#ff6600)
- White "G" text in center
- Sizes: 192x192 and 512x512 pixels

### Option 3: Using ImageMagick

```bash
# 192x192 icon
convert -size 192x192 xc:black \
    -fill '#ff6600' -draw 'circle 96,96 96,30' \
    -fill white -pointsize 120 -gravity center -annotate +0+0 'G' \
    icon-192.png

# 512x512 icon
convert -size 512x512 xc:black \
    -fill '#ff6600' -draw 'circle 256,256 256,80' \
    -fill white -pointsize 320 -gravity center -annotate +0+0 'G' \
    icon-512.png
```

### Option 4: Using any graphic editor

Use tools like GIMP, Photoshop, Inkscape, or online tools like:
- https://www.figma.com/
- https://www.canva.com/
- https://realfavicongenerator.net/

## Temporary Placeholder

For testing purposes, you can use any PNG images of the correct sizes.
The PWA will still install, but will use default icons if these are missing.
