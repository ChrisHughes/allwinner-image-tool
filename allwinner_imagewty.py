import argparse
import struct

class ImageWTYHeader:
    def __init__(self, bytes):
        # Check magic string
        if bytes[0:8] != b'IMAGEWTY':
            raise RuntimeError("Bad header")  
        self.header_version = struct.unpack('<L', bytes[8:12])[0]
        self.header_size = struct.unpack('<L', bytes[12:16])[0]
        self.ram_base = struct.unpack('<L', bytes[16:20])[0]
        self.version = struct.unpack('<L', bytes[20:24])[0]
        self.size = struct.unpack('<L', bytes[24:28])[0]

        if self.header_version == 0x0100:
            self.image_header_size = struct.unpack('<L', bytes[28:32])[0]
            self.pid = struct.unpack('<L', bytes[32:36])[0]
            self.vid = struct.unpack('<L', bytes[36:40])[0]
            self.hw_id = struct.unpack('<L', bytes[40:44])[0]
            self.fw_id = struct.unpack('<L', bytes[44:48])[0]
            # 2x unknown values
            self.num_files = struct.unpack('<L', bytes[56:60])[0]
        elif self.header_version == 0x0300 or self.header_version == 0x0403:
            # 1x unknown value
            self.image_header_size = struct.unpack('<L', bytes[32:36])[0]
            self.pid = struct.unpack('<L', bytes[36:40])[0]
            self.vid = struct.unpack('<L', bytes[40:44])[0]
            self.hw_id = struct.unpack('<L', bytes[44:48])[0]
            self.fw_id = struct.unpack('<L', bytes[48:52])[0]
            # 2x unknown values
            self.num_files = struct.unpack('<L', bytes[60:64])[0]
        else:
            raise RuntimeError("Unknown format version")

    def print_details(self):
        print ("Header version", hex(self.header_version))
        print ("Header size", self.header_size)
        print ("Ram base", self.ram_base)
        print ("Version", self.version)
        print ("Size", self.size)
        print ("Image header size", self.image_header_size)
        print ("Pid", hex(self.pid))
        print ("Vid", hex(self.vid))
        print ("HWID", self.hw_id)
        print ("FWID", self.fw_id)
        print ("Num files", self.num_files)

class DiskHeader:
    def __init__(self, header, bytes):
        self.filename_length = struct.unpack('<L', bytes[0:4])[0]
        self.total_header_size = struct.unpack('<L', bytes[4:8])[0]
        self.main_type = bytes[8:16].decode("utf-8")
        self.sub_type = bytes[16:32].decode("utf-8")
        if header.header_version == 0x0100:
            # 1x unknown value
            self.stored_length = struct.unpack('<L', bytes[36:40])[0]
            self.original_length = struct.unpack('<L', bytes[40:44])[0]
            self.offset = struct.unpack('<L', bytes[44:48])[0]
            # 1x unknown value
            self.name = bytes[52:52 + self.filename_length].decode("utf-8")
            self.pad1 = 0
            self.pad2 = 0
        elif header.header_version == 0x0300 or header.header_version == 0x0403:
            # 1x unknown value
            offset = 36
            self.name = bytes[offset:offset + self.filename_length].decode("utf-8")
            offset += self.filename_length
            self.stored_length = struct.unpack('<L', bytes[offset:offset+4])[0]
            offset += 4
            self.pad1 = struct.unpack('<L', bytes[offset:offset+4])[0]
            offset += 4
            self.original_length = struct.unpack('<L', bytes[offset:offset+4])[0]
            offset += 4
            self.pad2 = struct.unpack('<L', bytes[offset:offset+4])[0]
            offset += 4
            self.offset = struct.unpack('<L', bytes[offset:offset+4])[0]
            offset += 4
        self.name = self.name.replace('\x00', '')

        self.content = None

    def load_content(self, bytes):
        self.content = bytes[self.offset:self.offset + self.stored_length]

    def print_details(self):
        print("Filename length", self.filename_length)
        print("Total header size", self.total_header_size)
        print("Main type", self.main_type)
        print("Sub type", self.sub_type)
        print("Name", self.name)
        print("Stored length", self.stored_length)
        print("Original length", self.original_length)
        print("Offset", self.offset)
        print("")

def decode(filename):
    """Decodes Allwinner ImageWTY"""
    disk_objects = []
    image_content = ""
    with open(filename, 'rb') as file:
        image_content = file.read()
    
    # Decode ImageWTY header
    header = ImageWTYHeader(image_content)

    offset = header.image_header_size
    for i in range(header.num_files):
        disk_object = DiskHeader(header, image_content[offset:offset + header.image_header_size])
        disk_object.load_content(image_content)
        disk_objects.append(disk_object)
        offset += header.image_header_size
    return header, disk_objects

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='allwinner_imagewty')
    parser.add_argument('file')
    parser.add_argument('--verbose', action='store_true', help='list')
    parser.add_argument('--list', action='store_true', help='list')
    parser.add_argument('--extract', help='disk to extract')
    parser.add_argument('--replace', nargs=2, help='disk to replace')
    parser.add_argument('--output', help='output filename')
    args = parser.parse_args()

    header, disk_objects = decode(args.file)

    if args.verbose:
        header.print_details()
    
    if args.list:
        for disk_object in disk_objects:
            if args.verbose:
                disk_object.print_details()
            else:
                print (disk_object.name)

    if args.extract:
        found = False
        for disk_object in disk_objects:
            if disk_object.name == args.extract:
                output_filename = disk_object.name if args.output is None else args.output
                with open(output_filename, 'wb') as file:
                    file.write(disk_object.content)
                if args.verbose:
                    disk_object.print_details()
                found = True
        if not found:
            raise RuntimeError("Cannot find disk with name " + args.extract)
    
    if args.replace:
        disk_name, input_filename = args.replace
        for disk_object in disk_objects:
            if disk_object.name == disk_name:
                output_filename = args.file + ".modified" if args.output is None else args.output
                with open(input_filename, 'rb') as file:
                    input_data = file.read()
                if len(input_data) != disk_object.stored_length:
                    raise RuntimeError("Data to replace must match stored size")
                with open(args.file, 'rb') as file:
                    image_content = file.read()
                with open(output_filename, 'wb') as output_file:
                    output_file.write(image_content[0:disk_object.offset])
                    output_file.write(input_data)
                    output_file.write(image_content[disk_object.offset + disk_object.stored_length:])
                if args.verbose:
                    disk_object.print_details()