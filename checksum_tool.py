
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='checksum_tool')
    parser.add_argument('input_file')
    parser.add_argument('output_file')
    args = parser.parse_args()

    with open(args.input_file, "rb") as f:
        checksum = 0
        while True:
            bytes = f.read(4)
            if not bytes:
                break
            val = int.from_bytes(bytes, byteorder='little', signed=False)
            checksum = checksum + val
            checksum = checksum & 0xFFFFFFFF

    with open(args.output_file, "rb") as f:
        checksum_contents = bytearray(f.read())
    checksum_contents[0:4] = checksum.to_bytes(4, byteorder='little', signed=False)
    
    with open(args.output_file, "wb") as f:
        f.write(checksum_contents)