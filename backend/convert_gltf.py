"""
convert_gltf.py
================
Converts a GrabCAD .gltf (+ .bin + textures) export into a single, portable
.glb binary that `layer4_dashboard.py` can base64-embed into <model-viewer>.

Usage:
    python convert_gltf.py --src "assets/Rotax 914.gltf" --dst "assets/engine_block.glb"

If --src is omitted, the script looks for the first *.gltf file inside ./assets/.
"""
import argparse
import glob
import os

from pygltflib import GLTF2

HERE = os.path.dirname(os.path.abspath(__file__))


def find_default_source() -> str | None:
    candidates = glob.glob(os.path.join(HERE, "assets", "*.gltf"))
    return candidates[0] if candidates else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default=None, help="Path to source .gltf file")
    parser.add_argument("--dst", default=os.path.join(HERE, "assets", "engine_block.glb"),
                         help="Output .glb path")
    args = parser.parse_args()

    src = args.src or find_default_source()
    if not src or not os.path.exists(src):
        raise SystemExit(
            "No .gltf source found. Place your GrabCAD export (e.g. "
            "'assets/Rotax 914.gltf' + its .bin + textures) in ./assets/ first, "
            "or pass --src explicitly."
        )

    print(f"Loading {src} ...")
    gltf = GLTF2().load(src)
    
    from pygltflib.utils import BufferFormat, ImageFormat
    gltf.convert_buffers(BufferFormat.BINARYBLOB)
    gltf.convert_images(ImageFormat.BUFFERVIEW)
    
    gltf.save_binary(args.dst)
    print(f"Conversion complete: {args.dst} generated successfully.")


if __name__ == "__main__":
    main()
