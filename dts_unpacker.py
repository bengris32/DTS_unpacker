#!/usr/bin/env python3
#
# Copyright (C) 2024 bengris32
# Copyright (C) 2017 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#

import os
import shutil

from ctypes import sizeof, Structure, c_char, c_int
from argparse import ArgumentParser
from gzip import decompress as gzip_decompress
from json import dump as json_dump

HSDT_MAGIC = b"HSDT"
GZIP_MAGIC = b"\x1f\x8b"


# See: https://github.com/96boards-hikey/tools-images-hikey960/blob/master/build-from-source/mkdtimg
class dt_head_info(Structure):
    _fields_ = [("magic", c_char * 4), ("version", c_int), ("dt_count", c_int)]


class dt_entry_t(Structure):
    _fields_ = [
        ("reserved0", c_char * 8),
        ("dtb_size", c_int),
        ("reserved1", c_int),
        ("dtb_offset", c_int),
        ("reserved2", c_int),
        ("reserved3", c_char * 8),
        ("reserved4", c_char * 8),
    ]


class DTEntry:
    def __init__(self, dt_entry, dt):
        self.size = dt_entry.dtb_size
        self.offset = dt_entry.dtb_offset
        self.compressed = dt[:2] == GZIP_MAGIC
        self._dt = dt

    @property
    def dt(self):
        if self.compressed:
            return gzip_decompress(self._dt)
        else:
            return self._dt

    @property
    def as_dict(self):
        return {
            "dtb_size": self.size,
            "dtb_offset": self.offset,
            "compressed": self.compressed,
        }


def extract_dt(f, dt_entry):
    f.seek(dt_entry.dtb_offset)
    return DTEntry(dt_entry, f.read(dt_entry.dtb_size))


def read_dtb(f):
    b_header = f.read(sizeof(dt_head_info))
    header = dt_head_info.from_buffer_copy(b_header)
    assert header.magic == HSDT_MAGIC, "Invalid magic!"

    entries = [
        dt_entry_t.from_buffer_copy(f.read(sizeof(dt_entry_t)))
        for _ in range(header.dt_count)
    ]

    dts = [extract_dt(f, entry) for entry in entries]

    return header, dts


def main():
    parser = ArgumentParser()
    parser.add_argument(
        "-i", "--input", help="DTS image to extract.", type=str, required=True
    )
    parser.add_argument(
        "-p",
        "--preserve",
        help="If image is gzipped, don't decompress.",
        action="store_true",
        default=False,
    )
    args = parser.parse_args()

    # Clear out "output/"
    if os.path.exists("output"):
        shutil.rmtree("output")
    os.makedirs("output")

    with open(args.input, "rb") as f:
        header, entries = read_dtb(f)

    for entry in entries:
        with open(os.path.join("output", f"{entry.offset}.dtb"), "xb") as f:
            dt = entry._dt if args.preserve else entry.dt
            f.write(dt)

    info = {
        "image_version": header.version,
        "image_dt_count": header.dt_count,
        "image_dts": [entry.as_dict for entry in entries],
    }
    with open("image_info.json", "x") as f:
        json_dump(info, f, indent=4)

    print(f"Successfully dumped {header.dt_count} dtbs.")


if __name__ == "__main__":
    main()
