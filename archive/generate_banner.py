#!/usr/bin/env python3
"""Яркий, динамичный баннер в стиле спортивного постера:
тёмный диагональный фон, линии скорости, объёмные цифры года с тенью,
акцентная лента-подпись для группы А/Б."""

from PIL import Image, ImageDraw, ImageFont
import math

FONT_PATH_BLACK = "/usr/share/fonts/truetype/google-fonts/Poppins-Black.ttf"
FONT_PATH_BOLD = "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf"
FONT_PATH_CYRILLIC = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

W, H = 640, 220

LOGO_PATH = "fhspb_logo.png"


def get_font(size, black=True):
    import os
    path = FONT_PATH_BLACK if (black and os.path.exists(FONT_PATH_BLACK)) else FONT_PATH_BOLD
    return ImageFont.truetype(path, size)


def make_banner(year, group=None, accent="#00C2FF",
                 tournament_type=None, badge_label=None, out_path=None):
    img = Image.new("RGB", (W, H), "#0B1220")
    draw = ImageDraw.Draw(img)

    draw.polygon(
        [(W * 0.62, 0), (W, 0), (W, H), (W * 0.30, H)],
        fill=accent,
    )
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.polygon([(W * 0.62, 0), (W * 0.74, 0), (W * 0.42, H), (W * 0.30, H)], fill=(0, 0, 0, 60))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    for i in range(6):
        x0 = -20 + i * 14
        draw.line([(x0, H * 0.15), (x0 + 55, H * 0.85)], fill="#1C2942", width=5)

    if tournament_type or badge_label:
        badge_colors = {
            "КУБОК": "#FFC107",
            "ПЕРВЕНСТВО": "#7C4DFF",
        }
        badge_color = badge_colors.get((tournament_type or "").upper(), "#7C4DFF")
        badge_font = ImageFont.truetype(FONT_PATH_CYRILLIC, 22)
        label = badge_label if badge_label else (tournament_type.upper() + " СПБ")
        lbbox = draw.textbbox((0, 0), label, font=badge_font)
        lw = lbbox[2] - lbbox[0]
        lh = lbbox[3] - lbbox[1]
        pad_x, pad_y = 14, 8
        badge_w = lw + pad_x * 2
        badge_h = lh + pad_y * 2
        badge_x0, badge_y0 = 14, 14
        draw.rounded_rectangle(
            [badge_x0, badge_y0, badge_x0 + badge_w, badge_y0 + badge_h],
            radius=6, fill=badge_color,
        )
        draw.text(
            (badge_x0 + pad_x - lbbox[0], badge_y0 + pad_y - lbbox[1]),
            label, font=badge_font, fill="#0B1220",
        )

    year_size = 148 if not group else 112
    year_font = get_font(year_size)
    bbox = draw.textbbox((0, 0), year, font=year_font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    cx = W * 0.42
    cy = H / 2 - (26 if group else 0) + (14 if (tournament_type or badge_label) else 0)
    x = cx - text_w / 2 - bbox[0]
    y = cy - text_h / 2 - bbox[1]

    shadow_offset = 6
    draw.text((x + shadow_offset, y + shadow_offset), year, font=year_font, fill="#00000055")
    draw.text((x - 2, y - 2), year, font=year_font, fill=accent)
    draw.text((x, y), year, font=year_font, fill="white")

    if group:
        group_font = get_font(38)
        gbbox = draw.textbbox((0, 0), group, font=group_font)
        gw = gbbox[2] - gbbox[0]
        gh = gbbox[3] - gbbox[1]
        gy_center = cy + text_h / 2 + 32
        pad_x, pad_y = 22, 10
        ribbon_w = gw + pad_x * 2
        ribbon_h = gh + pad_y * 2
        rx0 = cx - ribbon_w / 2
        ry0 = gy_center - ribbon_h / 2
        draw.rounded_rectangle(
            [rx0, ry0, rx0 + ribbon_w, ry0 + ribbon_h], radius=8, fill=accent
        )
        gx = cx - gw / 2 - gbbox[0]
        gy = gy_center - gh / 2 - gbbox[1]
        draw.text((gx, gy), group, font=group_font, fill="#0B1220")

    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo_size = 108
        logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
        logo_x = int(W * 0.90 - logo_size / 2)
        logo_y = int(H * 0.28 - logo_size / 2)
        img.paste(logo, (logo_x, logo_y), logo)
    except FileNotFoundError:
        pass

    draw.rectangle([0, 0, W - 1, H - 1], outline="#2A3B5C", width=2)

    if out_path:
        img.save(out_path)
    return img


def generate_all_banners(output_dir):
    """Генерирует полный набор баннеров: Кубок (по возрасту, БЕЗ групп) +
    Первенство (по возрасту И группам А/Б, кроме 2009/2010)."""
    import os
    os.makedirs(output_dir, exist_ok=True)

    count = 0

    cup_ages = {
        "2010": "#00C2FF", "2011": "#00C2FF", "2012": "#00C2FF",
        "2013": "#00C2FF", "2014": "#00C2FF", "2015": "#00C2FF",
        "2016": "#00C2FF", "2017": "#00C2FF", "2018": "#00C2FF",
    }
    for year, accent in cup_ages.items():
        badge_label = "КУБОК ФЕДЕРАЦИИ" if year in ("2016", "2017", "2018") else None
        filepath = os.path.join(output_dir, f"{year}_cup.png")
        make_banner(year, group=None, accent=accent, tournament_type="КУБОК",
                    badge_label=badge_label, out_path=filepath)
        count += 1

    championship_configs = [
        ("2009", None, "#00C2FF"),
        ("2010", None, "#00C2FF"),
        ("2011", "GROUP A", "#FF3D5A"), ("2011", "GROUP B", "#00C2FF"),
        ("2012", "GROUP A", "#FF3D5A"), ("2012", "GROUP B", "#00C2FF"),
        ("2013", "GROUP A", "#FF3D5A"), ("2013", "GROUP B", "#00C2FF"),
        ("2014", "GROUP A", "#FF3D5A"), ("2014", "GROUP B", "#00C2FF"),
        ("2015", "GROUP A", "#FF3D5A"), ("2015", "GROUP B", "#00C2FF"),
    ]
    for year, group, accent in championship_configs:
        group_suffix = f"_{group.replace(' ', '').lower()}" if group else ""
        filepath = os.path.join(output_dir, f"{year}{group_suffix}_champ.png")
        make_banner(year, group=group, accent=accent, tournament_type="ПЕРВЕНСТВО",
                    out_path=filepath)
        count += 1

    print(f"\nСгенерировано баннеров: {count}")


if __name__ == "__main__":
    generate_all_banners("banners")
