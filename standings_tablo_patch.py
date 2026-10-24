#!/usr/bin/env python3
"""
post_standings.py: турнирная таблица в стиле «Табло».

  * размер картинки всегда 1280×1440, сколько бы ни было команд: высота строк
    подстраивается, короткая таблица крупнее и стоит по центру;
  * шапка — баннер турнира в стиле «Табло» (по году, турниру и группе);
  * место и очки горят точками табло, лидер в янтарной рамке;
  * столбцы прежние: И, В, П (вместе с ОТ и буллитами), О.

Нужны баннеры «Табло» (generate_banner_v3.py --install).
Запуск (из ~/vk-bot):  python3 standings_tablo_patch.py
Откат:                  git checkout HEAD~1 -- post_standings.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "post_standings.py"

NEW_FUNC = '''def draw_standings_image(title, by_group, out_path):
    """Турнирная таблица в стиле «Табло». Размер всегда 1280×1440."""
    import os
    from datetime import datetime as _dt
    from PIL import ImageFilter
    import generate_banner_v3 as _tb

    S = 2
    W, H = 1280, 1440
    BG, PANEL, PANEL2, EDGE = (8, 11, 18), (17, 21, 31), (13, 17, 26), (48, 56, 74)
    TEXT, MUTED, AMBER = (240, 244, 250), (140, 152, 176), (255, 200, 50)
    fb = lambda s: ImageFont.truetype(FONT_BOLD_PATH, int(s * S))
    fr = lambda s: ImageFont.truetype(FONT_PATH, int(s * S))

    def led(d, text, x, y, cell, color):
        for ch in text:
            for r, row in enumerate(_tb.GLYPHS[ch]):
                for c, bit in enumerate(row):
                    if bit == "1":
                        d.ellipse([x + c * cell, y + r * cell, x + c * cell + cell * 0.84, y + r * cell + cell * 0.84],
                                  fill=color)
            x += cell * 6.2
    led_w = lambda text, cell: len(text) * cell * 6.2 - cell * 1.2

    # --- какой баннер в шапке
    year_m = re.search(r"(20\\d\\d)", title)
    year = year_m.group(1) if year_m else ""
    groups = [g for g in by_group if by_group[g]]
    first_group = groups[0] if groups else None
    letter_m = re.search(r"([АБAB])\\s*$", str(first_group or ""))
    letter = {"А": "a", "A": "a", "Б": "b", "B": "b"}.get(letter_m.group(1) if letter_m else "", "")
    banners = Path(__file__).parent / "banners"
    candidates = ([f"{year}_cup.png"] if ("ФЕДЕРАЦ" in title.upper() or year in ("2016", "2017", "2018")) else
                  [f"{year}_group{letter}_champ.png", f"{year}_champ.png", f"{year}_groupa_champ.png"])
    banner = next((banners / n for n in candidates if (banners / n).exists() and n), None)

    img = Image.new("RGBA", (W * S, H * S), BG + (255,))
    if banner:
        b = Image.open(banner).convert("RGB")
        hdr = b.resize((W * S, int(b.height * W * S / b.width)), Image.LANCZOS)
        img.paste(hdr, (0, 0))
        y = hdr.height
    else:
        y = 40 * S
    d = ImageDraw.Draw(img)
    group_label = ""
    if first_group and len(groups) == 1:
        g = str(first_group).strip()
        group_label = g if g.lower().startswith("группа") else f"группа {g}"
    d.text((36 * S, y + 40 * S), "ТУРНИРНАЯ ТАБЛИЦА", font=fb(32), fill=AMBER, anchor="lm")
    d.text((W * S - 36 * S, y + 40 * S), "  ·  ".join(x for x in (group_label, f"на {_dt.now():%d.%m}") if x),
           font=fr(22), fill=MUTED, anchor="rm")
    y += 84 * S
    cols = [("И", 880), ("В", 960), ("П", 1040), ("О", 1170)]
    for name, x in cols:
        d.text((x * S, y + 16 * S), name, font=fb(18), fill=MUTED, anchor="mm")
    y += 36 * S

    rows = []
    for g in groups:
        if len(groups) > 1:
            rows.append(("group", g))
        rows += [("team", t) for t in by_group[g]]
    area_top, area_bottom = y, (H - 50) * S
    n = max(1, len(rows))
    rh = min((area_bottom - area_top) // n, 118 * S)
    y = area_top + ((area_bottom - area_top) - rh * n) // 2
    scale = rh / (72 * S)
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    lit = []
    i = 0
    for kind, item in rows:
        if kind == "group":
            d.text((36 * S, y + rh // 2), str(item).upper(), font=fb(min(26, 22 * scale)), fill=AMBER, anchor="lm")
            y += rh
            i = 0
            continue
        t = item
        top, bot = y + 4 * S, y + rh - 4 * S
        mid = (top + bot) // 2
        leader = t.get("rank") == 1
        d.rounded_rectangle([20 * S, top, W * S - 20 * S, bot], radius=12 * S, fill=PANEL if i % 2 == 0 else PANEL2,
                            outline=AMBER if leader else EDGE, width=(3 if leader else 1) * S)
        cell = min(6, max(3, int(5 * scale))) * S
        rank = str(t.get("rank", ""))
        if rank.isdigit():
            led(d, rank, 72 * S - led_w(rank, cell) / 2, mid - 3.5 * cell, cell, AMBER)
        lg = int(min(56, 46 * scale)) * S
        logo = _get_logo_image(t["team"], t.get("logo_url"))
        if logo is not None:
            logo = logo.copy()
            logo.thumbnail((lg, lg), Image.LANCZOS)
            img.alpha_composite(logo.convert("RGBA"), (120 * S + (lg - logo.width) // 2, mid - logo.height // 2))
        name = display_team_name(t["team"]).upper()
        name_x = 120 * S + lg + 18 * S
        size = min(30, 24 * scale)
        while size > 14 and d.textlength(name, font=fb(size)) > (cols[0][1] - 50) * S - name_x:
            size -= 1
        d.text((name_x, mid), name, font=fb(size), fill=TEXT, anchor="lm")
        losses = t.get("losses", 0) + t.get("losses_ot", 0) + t.get("losses_so", 0)
        for (cname, x), v in zip(cols[:3], (t.get("games", 0), t.get("wins", 0), losses)):
            d.text((x * S, mid), str(v), font=fr(min(28, 22 * scale)), fill=TEXT, anchor="mm")
        pc = min(7, max(3, int(5.5 * scale))) * S
        ps = str(t.get("points", 0))
        if ps.isdigit():
            px = min(cols[3][1] * S - led_w(ps, pc) / 2, (W - 44) * S - led_w(ps, pc))
            led(gd, ps, px, mid - 3.5 * pc, pc, (255, 160, 0, 170))
            lit.append((ps, px, mid - 3.5 * pc, pc))
        y += rh
        i += 1
    d.text((W * S - 36 * S, H * S - 24 * S), "fhspb.ru  ·  spb.fhr.ru", font=fr(18), fill=MUTED, anchor="rm")
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(8 * S)))
    d = ImageDraw.Draw(img)
    for ps, px, py, pc in lit:          # очки поверх свечения — чёткие
        led(d, ps, px, py, pc, AMBER)
    img = img.convert("RGB").resize((W, H), Image.LANCZOS)
    IMAGES_DIR.mkdir(exist_ok=True)
    tmp_path = f"{out_path}.tmp"
    img.save(tmp_path, format="PNG")
    os.replace(tmp_path, out_path)
    return out_path
'''


def replace_first_function(content, name, new_code):
    start = content.index(f"def {name}(")
    pos = content.index("\n", start) + 1
    while pos < len(content):
        end = content.find("\n", pos)
        end = len(content) if end == -1 else end
        line = content[pos:end]
        if line.strip() and not line[0].isspace():
            break
        pos = end + 1
    return content[:start] + new_code.rstrip("\n") + "\n\n\n" + content[pos:]


def main():
    if not (BASE / "generate_banner_v3.py").exists():
        sys.exit("Нет generate_banner_v3.py — сначала установите баннеры «Табло». Файл НЕ изменён")
    content = TARGET.read_text(encoding="utf-8")
    if "Турнирная таблица в стиле «Табло»" in content:
        print("post_standings.py: уже исправлено")
    else:
        if content.count("def draw_standings_image(") != 1:
            sys.exit("post_standings.py: функция отрисовки не найдена однозначно — файл НЕ изменён")
        shutil.copy(TARGET, TARGET.with_name("post_standings.py.bak_tablo"))
        TARGET.write_text(replace_first_function(content, "draw_standings_image", NEW_FUNC), encoding="utf-8")
        print("post_standings.py: таблицы рисуются в стиле «Табло», 1280×1440")
    cases = BASE / "tests" / "cases.py"
    if cases.exists() and "test_standings_tablo" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест таблицы «Табло»")


TEST_ADD = '''

def test_standings_tablo():
    """Таблица «Табло»: короткая и длинная группа — одинаковый размер 1280×1440."""
    with quiet():
        import post_standings as st
    st._get_logo_image = lambda team, url: None
    st.IMAGES_DIR.mkdir(exist_ok=True)
    row = lambda r, t, p: {"rank": r, "team": t, "games": 9, "wins": 5, "losses": 3, "losses_ot": 1,
                           "losses_so": 0, "points": p, "logo_url": None}
    from PIL import Image
    sizes = []
    for n in (4, 14):
        out = st.IMAGES_DIR / f"t{n}.png"
        st.draw_standings_image("Турнирная таблица — ПЕРВЕНСТВО СПБ 2011 г.р.",
                                {"А": [row(i + 1, f"Команда {i}", 20 - i) for i in range(n)]}, out)
        sizes.append(Image.open(out).size)
    assert sizes == [(1280, 1440), (1280, 1440)], sizes
'''


if __name__ == "__main__":
    main()
