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

#pragma once
#include <vapours.hpp>

#define ZSTD_MAGICNUMBER         0x4349425A
#define ZSTD_TRACE               1 /* Nintendo enables this, should we? */
#define ZSTD_LEGACY_SUPPORT      0
#define ZSTD_STATIC_LINKING_ONLY

#include "zstd.h"

namespace ams::util {
    
    constexpr size_t DCtxWorkspaceSize = 0x176E8;

    inline bool DecompressZstdForLoader(void *workspace, void *map_base, size_t map_size, size_t segment_size, size_t compressed_size, const void *compressed_data_buf) {
        /* TODO: how to assert that workspace >= DCtxWorkspaceSize? */

        /* Check decompression margin */
        auto margin           = ZSTD_decompressionMargin(compressed_data_buf, compressed_size);

        if(ZSTD_isError(margin))                               return false;
        if(!util::CanAddWithoutOverflow(margin, segment_size)) return false;
        if(margin + segment_size > map_size)                   return false;

        R_ABORT_UNLESS(ZSTD_estimateDCtxSize() == DCtxWorkspaceSize); /* Why is this a runtime assert in N's code? */

        auto ctx        = ZSTD_initStaticDCtx(workspace, DCtxWorkspaceSize);
        size_t dec_size = ZSTD_decompressDCtx(ctx, map_base, map_size, compressed_data_buf, compressed_size);

        if (ZSTD_isError(dec_size))   return false;
        if (dec_size != segment_size) return false;

        return true;
    }
}

#ifdef AMS_ZSTD_IMPLEMENTATION
#include "zstddeclib.inc"

static_assert(sizeof(ZSTD_DCtx) == ams::util::DCtxWorkspaceSize);
#endif