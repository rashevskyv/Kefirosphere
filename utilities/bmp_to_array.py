#!/usr/bin/env python3
"""Convert a BMP/PNG image to a C array for boot splash screen.

Usage: bmp_to_array.py <image_path> <array_name> <output_directory>

Arguments:
  image_path       Path to the source image (BMP or PNG)
  array_name       Name of the C array to generate (e.g. SplashScreen)
  output_directory Directory where boot_splash_kefir.inc will be written
                   (typically stratosphere/boot/source/ inside Atmosphere)
"""

import os
import sys
import numpy as np
from PIL import Image


def bmp_to_array(image_path, array_name, output_dir):
    output_path = os.path.join(output_dir, 'boot_splash_kefir.inc')

    if os.path.exists(output_path):
        os.remove(output_path)

    img = Image.open(image_path).convert('RGB')
    width, height = img.size
    img_array = np.array(img)

    def rgb_to_hex(r, g, b):
        return (0xFF << 24) + (r << 16) + (g << 8) + b

    colors = [rgb_to_hex(r, g, b) for r, g, b in img_array.reshape(-1, 3)]

    array_str = ', '.join(f'0x{color:08X}' for color in colors)

    output = f'''
/*
 * Copyright (c) Atmosphère-NX
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms and conditions of the GNU General Public License,
 * version 2, as published by the Free Software Foundation.
 *
 * This program is distributed in the hope it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

constexpr size_t SplashScreenX = 0;
constexpr size_t SplashScreenY = 0;

constexpr size_t SplashScreenW = {width};
constexpr size_t SplashScreenH = {height};

constexpr u32 {array_name}[] = {{{array_str}}};

static_assert(sizeof({array_name}) == sizeof(u32) * SplashScreenW * SplashScreenH, "Incorrect {array_name} definition!");
'''

    with open(output_path, 'w', encoding='utf-8') as header_file:
        header_file.write(output)

    print(f'{output_path} generated successfully!')


def main():
    if len(sys.argv) != 4:
        print(f'Usage: {sys.argv[0]} <image_path> <array_name> <output_directory>', file=sys.stderr)
        sys.exit(1)

    image_path = sys.argv[1]
    array_name = sys.argv[2]
    output_dir = sys.argv[3]

    bmp_to_array(image_path, array_name, output_dir)


if __name__ == '__main__':
    main()
