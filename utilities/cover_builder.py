import os
import sys
import datetime
import random
import shutil
from PIL import Image, ImageDraw, ImageFont

# Add utilities path for shared helpers
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def draw_rotated_text(img, text, font, landscape_x, landscape_y, fill=(0, 0, 0, 255), offset=(0,0), scale_x=1.0, scale_y=1.0, pixel_scale=1, resampling=Image.Resampling.NEAREST, anti_aliasing=False):
    # Get bounding box of text
    bbox = font.getbbox(text)
    w = bbox[2]
    h = bbox[3]
    
    pad_x = max(0, offset[0])
    pad_y = max(0, offset[1])
    
    mask_mode = 'L' if anti_aliasing else '1'
    fill_val = 255 if anti_aliasing else 1
    
    txt_mask = Image.new(mask_mode, (w + pad_x, h + pad_y), 0)
    txt_draw = ImageDraw.Draw(txt_mask)
    txt_draw.text((0, 0), text, font=font, fill=fill_val)
    
    # Draw second layer if offset is provided
    if offset[0] != 0 or offset[1] != 0:
        txt_draw.text((offset[0], offset[1]), text, font=font, fill=fill_val)
        
    txt_mask = txt_mask.convert('L')
    
    # Apply pixel scaling and stretch via chosen resampling
    if pixel_scale != 1 or scale_x != 1.0 or scale_y != 1.0:
        new_w = int(txt_mask.width * pixel_scale * scale_x)
        new_h = int(txt_mask.height * pixel_scale * scale_y)
        txt_mask = txt_mask.resize((new_w, new_h), resampling)
        
    landscape_w = txt_mask.width
    if landscape_x == "center":
        landscape_x = (1280 - landscape_w) // 2
    
    # Rotate 90 CCW
    txt_rot = txt_mask.rotate(90, expand=True)
    
    # Position
    portrait_x = landscape_y
    portrait_y = 1280 - landscape_x - txt_rot.height
    
    # Paste using the mask
    color_layer = Image.new('RGBA', txt_rot.size, fill)
    img.paste(color_layer, (portrait_x, portrait_y), txt_rot)

from state_manager import state
from fetch_tools import get_env_var

def draw_hos_composite(img, version_text, landscape_x, landscape_y):
    digits_dir = os.path.join(BOOTLOGO_DIR, "digits")
    # Predictable jitter based on text content
    random.seed(version_text)
    
    def build_text_image(txt, scale_factor, use_jitter=True):
        chars = []
        for c in txt:
            if c == ' ': continue
            elif c == '.': c_name = "comma.png"
            elif c == '%': c_name = "%.png"
            else: c_name = f"{c}.png"
            
            p = os.path.join(digits_dir, c_name)
            if os.path.exists(p):
                c_img = Image.open(p).convert("RGBA")
                
                if getattr(sys.modules[__name__], 'HOS_DIGIT_ROTATION', 0) != 0:
                    c_img = c_img.rotate(HOS_DIGIT_ROTATION, expand=True)
                    
                new_w = int(c_img.width * scale_factor)
                
                j_scale = 1.0
                if use_jitter and HOS_JITTER_Y > 0.0:
                    j_scale = random.uniform(1.0 - HOS_JITTER_Y, 1.0 + HOS_JITTER_Y)
                new_h = max(1, int(c_img.height * scale_factor * j_scale))
                
                c_img = c_img.resize((new_w, new_h), Image.Resampling.NEAREST)
                chars.append(c_img)
                
        if not chars: return None
        
        total_w = sum(c.width for c in chars) + HOS_LETTER_SPACING * (len(chars) - 1)
        max_h = max(c.height for c in chars)
        
        out = Image.new('RGBA', (total_w, max_h), (0,0,0,0))
        cx = 0
        for c in chars:
            # Bottom align
            cy = max_h - c.height
            out.alpha_composite(c, dest=(cx, cy))
            cx += c.width + HOS_LETTER_SPACING
        return out
        
    ver_img = build_text_image(version_text, HOS_VERSION_SCALE, use_jitter=True)
    pct_img = build_text_image("%", HOS_PERCENT_SCALE, use_jitter=True)
    hos_img = build_text_image("HOS", HOS_LETTERS_SCALE, use_jitter=False)
    
    if not ver_img and not pct_img and not hos_img: return
    
    # Dimensions if all exist... we'll just position them relatively
    w_ver = ver_img.width if ver_img else 0
    h_ver = ver_img.height if ver_img else 0
    
    w_pct = pct_img.width if pct_img else 0
    h_pct = pct_img.height if pct_img else 0
    
    w_hos = hos_img.width if hos_img else 0
    h_hos = hos_img.height if hos_img else 0
    
    pct_x = w_ver + HOS_PERCENT_OFFSET_X
    pct_y = HOS_PERCENT_OFFSET_Y
    
    hos_x = pct_x + w_pct + HOS_LETTERS_OFFSET_X
    hos_y = pct_y + HOS_LETTERS_OFFSET_Y
    
    min_y = min(0, pct_y, hos_y)
    max_y = max(h_ver, pct_y + h_pct, hos_y + h_hos)
    
    total_w = hos_x + w_hos
    total_h = max_y - min_y
    
    combined = Image.new('RGBA', (total_w, total_h), (0,0,0,0))
    if ver_img: combined.alpha_composite(ver_img, dest=(0, -min_y))
    if pct_img: combined.alpha_composite(pct_img, dest=(pct_x, pct_y - min_y))
    if hos_img: combined.alpha_composite(hos_img, dest=(hos_x, hos_y - min_y))
    
    # Recolor to match TEXT_COLOR
    blank = Image.new("RGBA", combined.size, TEXT_COLOR)
    # Use alpha map from combined
    blank.putalpha(combined.split()[3])
    combined = blank
    
    # Optional double layer pseudo-bold effect matching common settings
    if TEXT_OFFSET_X != 0 or TEXT_OFFSET_Y != 0:
        comb_double = Image.new('RGBA', (combined.width + max(0, TEXT_OFFSET_X), combined.height + max(0, TEXT_OFFSET_Y)), (0,0,0,0))
        comb_double.alpha_composite(combined, dest=(TEXT_OFFSET_X, TEXT_OFFSET_Y))
        comb_double.alpha_composite(combined, dest=(0,0))
        combined = comb_double
        
    rot = combined.rotate(90, expand=True)
    
    lx = landscape_x
    if lx == "center":
        lx = (1280 - combined.width) // 2
        
    px = landscape_y
    py = 1280 - lx - rot.height
    
    img.alpha_composite(rot, dest=(px, py))
    
def get_season(month):
    if month in (3, 4, 5): return "spring"
    elif month in (6, 7, 8): return "summer"
    elif month in (9, 10, 11): return "autumn"
    else: return "winter"

_kefir_root = get_env_var("KEFIR_ROOT_DIR") or r"D:\git\dev\_kefir"
BOOTLOGO_DIR = os.path.join(_kefir_root, "bootlogo", "blank")
OUT_DIR = os.path.join(_kefir_root, "bootlogo", "temp")
DEBUG_GENERATE_Z1 = True  # Always generate update logo for now (forces copy)

# ==========================================
# TEXT CONFIGURATION
# ==========================================
FONT_SIZE = 17
TEXT_COLOR = (0, 0, 0, 255) # Black

# Double-draw offset (for pseudo-bold or custom rendering). Set to 0 to disable.
TEXT_OFFSET_X = 0
TEXT_OFFSET_Y = 0

# Vertical text scale (1.0 = normal, 1.5 = 50% stretched upwards)
TEXT_SCALE_Y = 1.6

# Horizontal text scale (1.0 = normal)
TEXT_SCALE_X = 1.2

# Pixelation factor (renders font smaller by this factor, then scales up)
TEXT_PIXELATION_SCALE = 1.6

# Interpolation mode for scaling: Image.Resampling.NEAREST, Image.Resampling.BILINEAR, Image.Resampling.BICUBIC
TEXT_RESAMPLING = Image.Resampling.NEAREST

# Enable/disable anti-aliasing (smooth edges) for text rendering
TEXT_ANTI_ALIASING = True

# Coordinates for text in Landscape view (1280x720)
TEXT_X = 973
TEXT_Y_LINE1 = 326
TEXT_Y_LINE2 = TEXT_Y_LINE1 + FONT_SIZE+6
TEXT_Y_LINE3 = TEXT_Y_LINE1 + FONT_SIZE * 2 + 12

# ==========================================
# HOS VERSION CONFIGURATION (Using PNG Digits)
# ==========================================
HOS_TEXT_X = "center"
HOS_TEXT_Y = 365 # Just under the logo

HOS_DIGIT_ROTATION = -90    # -90 means 90 degrees clockwise
HOS_LETTER_SPACING = 5      # Space between characters globally

HOS_VERSION_SCALE = 1.0

HOS_PERCENT_SCALE = 1.0
HOS_PERCENT_OFFSET_X = 10   # Space between "22.10" and "%"
HOS_PERCENT_OFFSET_Y = 0    # Vertical shift for "%" relative to "22.10"

HOS_LETTERS_SCALE = 1.0
HOS_LETTERS_OFFSET_X = 10   # Space between "%" and "HOS"
HOS_LETTERS_OFFSET_Y = 0    # Vertical shift for "HOS" relative to "%"

# Vertical jitter for heights (e.g. 0.15 = up to 15% random stretch/squash)
HOS_JITTER_Y = 0.05
# ==========================================
# DECAL POSITION CONFIGURATION
# ==========================================
UPDATING_X = 27
UPDATING_Y = "center" # integer or "center" for vertical alignment

TAGS_X = 15
TAGS_Y = 17

LOGO_X = 13
LOGO_Y = 402

RELEASES_X = 120
RELEASES_Y = 980
RELEASES_ROTATION = 90 # 90 degrees CCW
# ==========================================

def build_covers():
    os.makedirs(OUT_DIR, exist_ok=True)
    now = datetime.datetime.now()
    current_season = get_season(now.month)
    
    last_date_str = state.get("LAST_RELEASE_DATE")
    last_season = None
    if last_date_str:
        try:
            last_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d %H:%M:%S")
            last_season = get_season(last_date.month)
        except Exception:
            pass
            
    # Read KEF_VERSION
    kef_version = "Unknown"
    version_file = os.path.join(_kefir_root, "version")
    if os.path.exists(version_file):
        with open(version_file, "r", encoding="utf-8") as f:
            kef_version = f.read().strip()
            
    # Extract versions and remove 'v' prefixes and dots
    hekate_ver = state.get("HEKATE_LATEST_VERSION", "???").lstrip("v").replace(".", "")
    ams_ver = state.get("ATMOSPHERE_LATEST_VERSION", "???").lstrip("v").replace(".", "")
    
    date_line = now.strftime("%d.%m.%Y")
    version_line = f"{kef_version}-{hekate_ver}-{ams_ver}"
    
    bg_path = os.path.join(BOOTLOGO_DIR, f"{current_season}.png")
    if not os.path.exists(bg_path):
        print(f"Error: Background file not found -> {bg_path}")
        return
        
    bg = Image.open(bg_path).convert("RGBA")
    
    updating_dec = Image.open(os.path.join(BOOTLOGO_DIR, "updating.png")).convert("RGBA")
    tags_dec = Image.open(os.path.join(BOOTLOGO_DIR, "tags.png")).convert("RGBA")
    logo_dec = Image.open(os.path.join(BOOTLOGO_DIR, "logo.png")).convert("RGBA")
    releases_dec = Image.open(os.path.join(BOOTLOGO_DIR, "for releases.png")).convert("RGBA")
    if RELEASES_ROTATION != 0:
        releases_dec = releases_dec.rotate(RELEASES_ROTATION, expand=True)
    
    font_path = os.path.join(_kefir_root, "bootlogo", "fonts", "dotmat.ttf")
    # Load font smaller according to pixelation scale
    font = ImageFont.truetype(font_path, max(1, FONT_SIZE // TEXT_PIXELATION_SCALE))
    
    print(f"Building covers for season: {current_season} (Last season: {last_season})")
    # Extract HOS version and format (remove last dot)
    hos_ver_raw = state.get("HOS_VERSION", "???")
    if "." in hos_ver_raw:
        parts = hos_ver_raw.rsplit(".", 1)
        hos_formatted = "".join(parts)
    else:
        hos_formatted = hos_ver_raw
        
    # Generate Image 1 (only if season changed or debug is true)
    if DEBUG_GENERATE_Z1 or last_season != current_season:
        z1 = bg.copy()
        
        upd_y = UPDATING_Y
        if upd_y == "center":
            upd_y = (1280 - updating_dec.height) // 2
            
        z1.alpha_composite(updating_dec, dest=(UPDATING_X, upd_y))
        z1_out = os.path.join(OUT_DIR, "Z1_update.bmp")
        z1.save(z1_out, "BMP")
        print(f"Generated {z1_out}")
    else:
        print("Season didn't change, skipping Image 1 generation.")

    # Generate Image 2 
    z2 = bg.copy()
    z2.alpha_composite(tags_dec, dest=(TAGS_X, TAGS_Y))
    z2.alpha_composite(logo_dec, dest=(LOGO_X, LOGO_Y))
    
    draw_rotated_text(z2, date_line, font, TEXT_X, TEXT_Y_LINE1, fill=TEXT_COLOR, offset=(TEXT_OFFSET_X, TEXT_OFFSET_Y), scale_x=TEXT_SCALE_X, scale_y=TEXT_SCALE_Y, pixel_scale=TEXT_PIXELATION_SCALE, resampling=TEXT_RESAMPLING, anti_aliasing=TEXT_ANTI_ALIASING)
    draw_rotated_text(z2, version_line, font, TEXT_X, TEXT_Y_LINE2, fill=TEXT_COLOR, offset=(TEXT_OFFSET_X, TEXT_OFFSET_Y), scale_x=TEXT_SCALE_X, scale_y=TEXT_SCALE_Y, pixel_scale=TEXT_PIXELATION_SCALE, resampling=TEXT_RESAMPLING, anti_aliasing=TEXT_ANTI_ALIASING)
    
    # Draw custom HOS composite
    draw_hos_composite(z2, hos_formatted, HOS_TEXT_X, HOS_TEXT_Y)
    
    z2_out = os.path.join(OUT_DIR, "Z2_regular.bmp")
    z2.save(z2_out, "BMP")
    print(f"Generated {z2_out}")
    
    # Generate Image 3
    z3 = z2.copy()
    draw_rotated_text(z3, "8GB DRAM Edition", font, TEXT_X, TEXT_Y_LINE3, fill=TEXT_COLOR, offset=(TEXT_OFFSET_X, TEXT_OFFSET_Y), scale_x=TEXT_SCALE_X, scale_y=TEXT_SCALE_Y, pixel_scale=TEXT_PIXELATION_SCALE, resampling=TEXT_RESAMPLING, anti_aliasing=TEXT_ANTI_ALIASING)
    z3_out = os.path.join(OUT_DIR, "Z3_8gb.bmp")
    z3.save(z3_out, "BMP")
    print(f"Generated {z3_out}")

    # Generate Image 4
    z4 = z2.copy()
    z4.alpha_composite(releases_dec, dest=(RELEASES_X, RELEASES_Y))
    # rotate -90 is clockwise in pillow
    z4_rotated = z4.rotate(-90, expand=True) 
    z4_out = os.path.join(OUT_DIR, "Z4_final.png")
    z4_rotated.save(z4_out, "PNG")
    print(f"Generated {z4_out}")

    # ==========================================
    # DEPLOY TO FINAL LOCATIONS
    # ==========================================
    deploy_map = {
        "Z1_update.bmp": os.path.join(_kefir_root, "kefir", "bootloader", "updating.bmp"),
        "Z2_regular.bmp": os.path.join(_kefir_root, "kefir", "bootloader", "bootlogo_kefir.bmp"),
        "Z3_8gb.bmp": os.path.join(_kefir_root, "kefir", "config", "8gb", "bootloader", "bootlogo_kefir.bmp"),
        "Z4_final.png": os.path.join(_kefir_root, "kefir.png"),
    }

    for src_name, dst_path in deploy_map.items():
        src_path = os.path.join(OUT_DIR, src_name)
        if os.path.exists(src_path):
            dst_dir = os.path.dirname(dst_path)
            if not os.path.exists(dst_dir):
                os.makedirs(dst_dir, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            print(f"Deployed: {src_name} -> {dst_path}")

    # Save new state
    state.set("LAST_RELEASE_DATE", now.strftime("%Y-%m-%d %H:%M:%S"))
    print("Cover Builder completed successfully. State updated.")

if __name__ == '__main__':
    build_covers()
