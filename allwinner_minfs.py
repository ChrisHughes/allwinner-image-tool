import argparse
import struct

# TBC: These are guesses
FLAG_DIR = 1
FLAG_COMPRESSION = 2
FLAG_COMPRESSION_TYPE_LZMA = 4

class MINFSHeader:
    def __init__(self, bytes):
        
        # Check magic string
        if bytes[0:5] != b'MINFS':
            raise RuntimeError("Bad header")
        # Decode MinFS header
        self.version = struct.unpack('<H', bytes[6:8])[0]
        self.offset = struct.unpack('<L', bytes[8:12])[0]
        self.root_size = struct.unpack('<L', bytes[12:16])[0]
        self.file_count = struct.unpack('<L', bytes[16:20])[0]
        self.tree_size = struct.unpack('<L', bytes[20:24])[0]       # Size of directory block
        self.fdata_length = struct.unpack('<L', bytes[24:28])[0]    # Size of data block
        self.image_size = struct.unpack('<L', bytes[28:32])[0]

    def to_bytes(self):
        header = b'MINFS\x00'
        header += struct.pack('<H', self.version)
        header += struct.pack('<L', self.offset)
        header += struct.pack('<L', self.root_size)
        header += struct.pack('<L', self.file_count)
        header += struct.pack('<L', self.tree_size)
        header += struct.pack('<L', self.fdata_length)
        header += struct.pack('<L', self.image_size)
        return header
    
    def print_details(self):
        print ("Version", self.version)
        print ("Offset", self.offset)
        print ("Root size", self.root_size)
        print ("File count", self.file_count)
        print ("Tree size", self.tree_size)
        print ("FData length", self.fdata_length)
        print ("Image size", self.image_size)
        print ("")

class MINFSFile:
    def __init__(self, bytes, offset):
        self.binary_buffer = bytes
        self.header_offset = offset
        
        self.flash_offset = struct.unpack('<L', bytes[offset:offset+4])[0]
        offset = offset + 4
        
        self.raw_size = struct.unpack('<L', bytes[offset:offset+4])[0]
        offset = offset + 4

        self.uncompressed_size = struct.unpack('<L', bytes[offset:offset+4])[0]
        offset = offset + 4

        self.entry_length = struct.unpack('<H', bytes[offset:offset+2])[0]
        offset = offset + 2

        self.flags = struct.unpack('<H', bytes[offset:offset+2])[0]
        offset = offset + 2

        self.name_length = struct.unpack('<H', bytes[offset:offset+2])[0]
        offset = offset + 2

        self.extra_length = struct.unpack('<H', bytes[offset:offset+2])[0]
        offset = offset + 2

        self.name = bytes[offset:offset+self.name_length].decode("utf-8")
        offset = offset + self.name_length

        self.extra_data = bytes[offset:offset+self.extra_length]
        offset = offset + self.extra_length

        self.content = bytes[self.flash_offset : self.flash_offset + self.raw_size]

    def header(self):
        header = b''
        header += struct.pack('<L', self.flash_offset)
        header += struct.pack('<L', self.raw_size)
        header += struct.pack('<L', self.uncompressed_size)
        header += struct.pack('<H', self.entry_length)
        header += struct.pack('<H', self.flags)
        header += struct.pack('<H', self.name_length)
        header += struct.pack('<H', self.extra_length)
        header += self.name.encode('utf-8')
        header += self.extra_data
        header += b'\x00' * (self.entry_length - len(header))
        return header

    def print_details(self):
        print ("Name", self.name)
        print ("Flash offset", self.flash_offset)
        print ("Raw size", self.raw_size)
        print ("Uncompressed size", self.uncompressed_size)
        print ("Entry length", self.entry_length)
        print ("Flags", self.flags)
        print ("Name length", self.name_length)
        print ("Extra length", self.extra_length)
        print ("")

    def extract(self):
        """Extracts file to disk"""
        file_object.print_details()
        if self.flags & FLAG_COMPRESSION:
            raise RuntimeError("Handling compressed files not yet implemented")
        content = self.binary_buffer[self.flash_offset:self.flash_offset + self.raw_size]
        with open(self.name, 'wb') as file:
            file.write(content)

    def replace_content(self, content):
        if self.flags & FLAG_COMPRESSION:
            raise RuntimeError("Handling compressed files not yet implemented")
        self.raw_size = len(content)
        self.uncompressed_size = len(content)
        self.content = content
        
def decode(filename):
    """Decodes Allwinner Minfs FEX"""
    file_objects = []
    image_content = ""
    with open(filename, 'rb') as file:
        image_content = file.read()
    
    # Decode MinFS header
    header = MINFSHeader(image_content)

    offset = header.offset
    for file_index in range(header.file_count):
        file_object = MINFSFile(image_content, offset)
        file_objects.append(file_object)
        offset += file_object.entry_length

    offset = file_objects[0].flash_offset

    return header, file_objects

def replace(header, file_objects, file_object_to_replace, new_file):
    """Replaces file with new contents"""

    new_file_content = ""
    with open(new_file, 'rb') as file:
        new_file_content = file.read()

    file_object_to_replace.replace_content(new_file_content)

    # Recompute file offsets
    fdata_start = header.offset + header.tree_size + 24
    offset = fdata_start
    for file_object in file_objects:
        if file_object.flags & FLAG_DIR:
            continue
        file_object.flash_offset = offset

        offset += file_object.raw_size + file_object.raw_size % 2

        # Byte align offset
        offset += offset % 4
    header.fdata_length = offset - fdata_start

    # Fail if offset exceeds image_size
    if offset >= header.image_size:
        raise RuntimeError("Data exceeds image capacity!")

def write(filename, header, file_objects):
    offset = 0
    with open(filename, 'wb') as file:
        # Write MinFS header
        header_bytes = header.to_bytes()
        file.write(header_bytes)
        file.write(b'\x00' * (header.offset - len(header_bytes)))
        offset = header.offset

        # Write directory listing
        for file_object in file_objects:
            file_header = file_object.header()
            file.write(file_header)
            offset += len(file_header)

        # Padding after directory listing
        file.write(b'\x00' * 24)
        offset += 24

        # Write each file content
        for file_object in file_objects:
            if file_object.flags & FLAG_DIR:
                continue
            if offset != file_object.flash_offset:
                raise RuntimeError("Offset mismatch in " + file_object.name + " " + str(offset) + " != " + str(file_object.flash_offset))
            content = file_object.content
            file.write(content)
            offset += file_object.raw_size
            file_content_end_offset = offset
            offset += file_object.raw_size % 2
            offset += offset % 4
            padding = offset - file_content_end_offset
            file.write(b'\x00' * padding)
        
        # Write remainder of block
        file.write(b'\x00' * (header.image_size - offset))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='allwinner_minfs')
    parser.add_argument('file')
    parser.add_argument('--verbose', action='store_true', help='list')
    parser.add_argument('--list', action='store_true', help='list')
    parser.add_argument('--extract', help='file to extract')
    parser.add_argument('--replace', nargs=2, help='replace contents of named file')
    parser.add_argument('--output', help='output filename')

    args = parser.parse_args()
    header, file_objects = decode(args.file)
    
    if args.verbose:
        header.print_details()

    if args.list:
        for file_object in file_objects:
            if args.verbose:
                file_object.print_details()
            else:
                print(file_object.name)
    
    if args.extract:
        file_to_extract = args.extract
        for file_object in file_objects:
            if file_object.name == file_to_extract:
                file_object.extract()

    if args.replace:
        file_to_extract, new_file = args.replace
        for file_object in file_objects:
            if file_object.name == file_to_extract:
                replace(header, file_objects, file_object, new_file)
                output_filename = args.file + ".modified" if args.output is None else args.output
                write(output_filename, header, file_objects)
                break
