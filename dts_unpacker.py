#!/usr/bin/env python3
#
# Copyright (C) 2024 bengris32
# Copyright (C) 2017 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from ctypes import sizeof, Structure, c_char, c_int, c_ubyte, c_ulonglong
from argparse import ArgumentParser
from gzip import decompress as gzip_decompress
from json import dump as json_dump
import os.path

HSDT_MAGIC = b"HSDT"
GZIP_MAGIC = b"\x1f\x8b"
LOWEST_PAGE_SIZE = 2048


# See: https://github.com/96boards-hikey/tools-images-hikey960/blob/master/build-from-source/mkdtimg
class dt_head_info(Structure):
    _fields_ = [("magic", c_char * 4), ("version", c_int), ("dt_count", c_int)]


class dt_entry_t(Structure):
    _fields_ = [
        ("board_id", c_ubyte * 4),
        ("reserved", c_ubyte * 4),
        ("dtb_size", c_int),
        ("vrl_size", c_int),
        ("dtb_offset", c_int),
        ("vrl_offset", c_int),
        ("dtb_file", c_ulonglong),  # ?
        ("vrl_file", c_ulonglong),  # ?
    ]


class DTEntry:
    def __init__(self, dt_entry):
        self.board_id = dt_entry.board_id

        self.dtb_size = dt_entry.dtb_size
        self.dtb_offset = dt_entry.dtb_offset

        self.vrl_size = dt_entry.vrl_size
        self.vrl_offset = dt_entry.vrl_offset

        self.compressed = False
        self._dt = None
        self.vrl = None

    def read_image(self, start, f):
        f.seek(start + self.dtb_offset)
        self._dt = f.read(self.dtb_size)

        f.seek(start + self.vrl_offset)
        self.vrl = f.read(self.vrl_size)

        self.compressed = self._dt[:2] == GZIP_MAGIC

    @property
    def dt(self):
        if self.compressed:
            return gzip_decompress(self._dt)
        else:
            return self._dt

    @property
    def as_dict(self):
        return {
            "board_id": bytes(self.board_id).decode(),
            "dtb_size": self.dtb_size,
            "dtb_offset": self.dtb_offset,
            "vrl_size": self.vrl_size,
            "vrl_offset": self.vrl_offset,
            "compressed": self.compressed,
        }


def extract_dt(start, f, dt_entry):
    entry = DTEntry(dt_entry)
    entry.read_image(start, f)

    return entry


def find_hsdt_magic(f):
    current_pos = 0
    last_pos = 0

    while True:
        # This search method assumes that the start of the image is aligned to page size.
        buffer = f.read(LOWEST_PAGE_SIZE)
        current_pos += LOWEST_PAGE_SIZE

        if buffer.find(HSDT_MAGIC) != -1:
            print("Found HSDT header at", hex(last_pos))
            return last_pos

        last_pos = current_pos

def read_dtb(f):
    magic_pos = find_hsdt_magic(f)
    f.seek(magic_pos)

    b_header = f.read(sizeof(dt_head_info))
    header = dt_head_info.from_buffer_copy(b_header)

    entries = [
        dt_entry_t.from_buffer_copy(f.read(sizeof(dt_entry_t)))
        for _ in range(header.dt_count)
    ]

    dts = [extract_dt(magic_pos * 2, f, entry) for entry in entries]

    return header, dts


def main():
    parser = ArgumentParser()
    parser.add_argument(
        "-i", "--input", help="DTS image to extract.", type=str, required=True
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output directory where extracted images are placed.",
        type=str,
        default="dtb",
    )
    parser.add_argument(
        "-p",
        "--preserve",
        help="If image is gzipped, don't decompress.",
        action="store_true",
        default=False,
    )
    args = parser.parse_args()
    os.makedirs(args.output, exist_ok=True)

    with open(args.input, "rb") as f:
        header, entries = read_dtb(f)

    for entry in entries:
        with open(os.path.join(args.output, f"{entry.dtb_offset}.dtb"), "xb") as f:
            dt = entry._dt if args.preserve else entry.dt
            f.write(dt)

        if entry.vrl_offset:
            with open(os.path.join(args.output, f"{entry.vrl_offset}.vrl"), "xb") as f:
                f.write(entry.vrl)

    info = {
        "image_version": header.version,
        "image_dt_count": header.dt_count,
        "image_dts": [entry.as_dict for entry in entries],
    }
    with open(os.path.join(args.output, "image_info.json"), "x") as f:
        json_dump(info, f, indent=4)

    print(f"Successfully dumped {header.dt_count} dtbs.")


if __name__ == "__main__":
    main()
