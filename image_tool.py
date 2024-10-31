import argparse
from PIL import Image

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='image-tool')
    parser.add_argument('infile')
    parser.add_argument('outfile')
    args = parser.parse_args()

    image = Image.open(args.infile)
    
    image.save(args.outfile, "jpeg", progressive=False, quality=95, keep_rgb=False, dpi=(96, 96), optimize=False)