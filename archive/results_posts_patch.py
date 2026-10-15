#!/usr/bin/env python3
"""
post_schedule.py: «баннер с результатами» в постах дня.

  * пока результатов нет — обычный баннер; с первым результатом картинка
    заменяется на баннер с результатами (results_banner.py) и обновляется
    по мере окончания матчей;
  * подпись: сыгранный матч — «📺 команды» + «📋 Протокол матча», несыгранный —
    «📺 команды» + «🕐 время» (LIVE — как раньше);
  * Кубок СПб, Кубок Федерации, Первенство и Кубок России;
  * не больше RESULTS_EDITS_PER_RUN замен картинки за прогон (старые посты
    месяца обновятся за несколько прогонов, без риска ограничений Telegram);
  * если results_banner.py недоступен — в подписи остаётся «Итог матча».

Запуск (из ~/vk-bot, рядом должен лежать results_banner.py):
    python3 results_posts_patch.py
Резервная копия: post_schedule.py.bak_results
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "post_schedule.py"

# ---------------------------------------------------------------- подпись
CAPTION_OLD = '''        result_lines = []
        if effective_score:
            result_lines.append(f"Итог матча: {score_to_keycaps(effective_score)}")
            protocol_link = spb_match["game_url"] if spb_match else m["protocol_url"]
            result_lines.append(f"<a href=\\"{protocol_link}\\">Протокол матча</a>")

        common_lines = [team_line, time_line]
'''
CAPTION_NEW = '''        result_lines = []
        if effective_score:
            if not RESULTS_IMAGES_ENABLED:
                result_lines.append(f"Итог матча: {score_to_keycaps(effective_score)}")
            protocol_link = spb_match["game_url"] if spb_match else m["protocol_url"]
            result_lines.append(f"📋 <a href=\\"{protocol_link}\\">Протокол матча</a>")

        # Сыгранный матч: время уже не нужно — счёт на картинке с результатами.
        if effective_score and RESULTS_IMAGES_ENABLED:
            common_lines = [team_line]
        else:
            common_lines = [team_line, time_line]
'''

# ------------------------------------------------------ Кубок / Первенство
PT_NEW_OLD = '''                message_id = send_photo(topic_id, banner_path, caption)
                state[state_key] = {
                    "message_id": message_id,
                    "caption": caption,
                }
'''
PT_NEW_NEW = '''                img, img_fp = _results_image(state_key, banner_path, day_matches, spb_lookup,
                                             _results_title(age, group, tournament_type), None)
                message_id = send_photo(topic_id, img or banner_path, caption)
                state[state_key] = {
                    "message_id": message_id,
                    "caption": caption,
                    "image_fp": img_fp,
                }
'''
PT_UPD_OLD = '''            if existing.get("caption") != caption:
                print(f"\\n[ОБНОВЛЕНИЕ] {age} г.р. {group or ''} {tournament_type} — {date_label}")
                print(caption)
                if not dry_run:
                    edit_caption(existing["message_id"], caption, topic_id=topic_id)
                    existing["caption"] = caption
                    save_state(state)
                    time.sleep(1)
                else:
                    print("  (dry-run — не отредактировано)")
'''
PT_UPD_NEW = '''            _update_day_post(existing, state, state_key, topic_id, banner_path, caption,
                             day_matches, spb_lookup, _results_title(age, group, tournament_type),
                             f"{age} г.р. {group or ''} {tournament_type} — {date_label}", dry_run)
'''

# ------------------------------------------------------------ Кубок России
KR_NEW_OLD = '''                message_id = send_photo(topic_id, KUBOK_ROSSII_BANNER, caption)
                state[state_key] = {"message_id": message_id, "caption": caption}
'''
KR_NEW_NEW = '''                img, img_fp = _results_image(state_key, KUBOK_ROSSII_BANNER, day_matches, spb_lookup,
                                             f"Кубок России {age} г.р.", None)
                message_id = send_photo(topic_id, img or KUBOK_ROSSII_BANNER, caption)
                state[state_key] = {"message_id": message_id, "caption": caption, "image_fp": img_fp}
'''
KR_UPD_OLD = '''            if existing.get("caption") != caption:
                print(f"\\n[ОБНОВЛЕНИЕ] {age} г.р. КУБОК РОССИИ — {date_label}")
                print(caption)
                if not dry_run:
                    edit_caption(existing["message_id"], caption, topic_id=topic_id)
                    existing["caption"] = caption
                    save_state(state)
                    time.sleep(1)
                else:
                    print("  (dry-run — не отредактировано)")
'''
KR_UPD_NEW = '''            _update_day_post(existing, state, state_key, topic_id, KUBOK_ROSSII_BANNER, caption,
                             day_matches, spb_lookup, f"Кубок России {age} г.р.",
                             f"{age} г.р. КУБОК РОССИИ — {date_label}", dry_run)
'''

# ------------------------------------------------------- новые функции
FUNC_ANCHOR = "def process_tournament("
FUNC_ADD = '''# ===================== Баннер с результатами в постах дня =====================
try:
    import results_banner
except Exception as _e:
    print(f"[WARN] results_banner.py недоступен ({_e}) — посты без картинки с результатами")
    results_banner = None
RESULTS_IMAGES_ENABLED = results_banner is not None
RESULTS_IMAGES_DIR = Path(__file__).parent / "results_images"
RESULTS_EDITS_PER_RUN = 15
_results_edits_done = 0


def _results_title(age, group, tournament_type):
    return results_banner.results_title(age, group, tournament_type) if results_banner else ""


def _results_image(state_key, banner_path, day_matches, spb_lookup, title, known_fp):
    """(картинка, отпечаток). Пока результатов нет — (None, None): обычный
    баннер. Перерисовывает, только если результаты изменились."""
    if not RESULTS_IMAGES_ENABLED:
        return None, None
    rows = []
    for m in day_matches:
        score = m.get("score")
        if not score and spb_lookup:
            sm = spb_lookup.get(build_match_key(plain_date(m["date"]), m["team1"], m["team2"]))
            score = (sm or {}).get("score")
        rows.append({"time": m.get("time"), "team1": m["team1"], "team2": m["team2"], "score": score})
    if not any(results_banner.split_score(r["score"]) for r in rows):
        return None, None
    fp = json.dumps(sorted((r["time"] or "", r["team1"], r["team2"], r["score"] or "") for r in rows),
                    ensure_ascii=False)
    RESULTS_IMAGES_DIR.mkdir(exist_ok=True)
    out = RESULTS_IMAGES_DIR / (re.sub(r"[^0-9A-Za-z_.-]", "_", state_key) + ".png")
    if fp == known_fp and out.exists():
        return out, fp
    try:
        results_banner.render(banner_path, rows, day_matches[0]["date"], _group_of(state_key), title, out)
        return out, fp
    except Exception as e:
        print(f"[WARN] Не удалось нарисовать результаты для {state_key}: {e}")
        return None, known_fp


def _group_of(state_key):
    tid = state_key.split("_", 1)[0]
    for _age, group, t in CHAMPIONSHIP_CONFIG:
        if str(t) == tid:
            return group
    return None


def edit_media(message_id, image_path, caption, topic_id=None):
    """Заменяет картинку поста вместе с подписью."""
    media = json.dumps({"type": "photo", "media": "attach://photo",
                        "caption": caption, "parse_mode": "HTML"}, ensure_ascii=False)
    payload = {"chat_id": TG_CHAT_ID, "message_id": message_id, "media": media}
    if topic_id is not None:
        payload["reply_markup"] = _build_share_buttons(topic_id, message_id)
    with open(image_path, "rb") as f:
        data = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageMedia",
                             data=payload, files={"photo": f}, timeout=30).json()
    if not data.get("ok") and "message is not modified" not in str(data.get("description", "")):
        raise RuntimeError(f"Telegram editMessageMedia error: {data}")


def _update_day_post(existing, state, state_key, topic_id, banner_path, caption,
                     day_matches, spb_lookup, title, label, dry_run):
    global _results_edits_done
    img, img_fp = _results_image(state_key, banner_path, day_matches, spb_lookup, title,
                                 existing.get("image_fp"))
    image_changed = img_fp != existing.get("image_fp")
    caption_changed = existing.get("caption") != caption
    if not image_changed and not caption_changed:
        return
    if image_changed and _results_edits_done >= RESULTS_EDITS_PER_RUN:
        return    # лимит замен картинок за прогон — остальное на следующем прогоне
    print(f"\\n[ОБНОВЛЕНИЕ{' + картинка' if image_changed else ''}] {label}")
    print(caption)
    if dry_run:
        print("  (dry-run — не отредактировано)")
        return
    if image_changed:
        _results_edits_done += 1
        edit_media(existing["message_id"], img or banner_path, caption, topic_id)
        existing["image_fp"] = img_fp
    else:
        edit_caption(existing["message_id"], caption, topic_id=topic_id)
    existing["caption"] = caption
    save_state(state)
    time.sleep(1)


'''


def main():
    if not (BASE / "results_banner.py").exists():
        print("ВНИМАНИЕ: рядом нет results_banner.py — сначала скачайте его. Файл НЕ изменён.")
        sys.exit(1)
    content = TARGET.read_text(encoding="utf-8")
    if "def _update_day_post(" in content:
        print("Уже применено.")
        return
    checks = [("подпись", CAPTION_OLD), ("новый пост (Кубок/Первенство)", PT_NEW_OLD),
              ("обновление (Кубок/Первенство)", PT_UPD_OLD), ("новый пост (Кубок России)", KR_NEW_OLD),
              ("обновление (Кубок России)", KR_UPD_OLD), ("process_tournament", FUNC_ANCHOR)]
    missing = [n for n, s in checks if content.count(s) != 1]
    if missing:
        print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing), "— файл НЕ изменён")
        sys.exit(1)
    shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_results"))
    content = content.replace(CAPTION_OLD, CAPTION_NEW)
    content = content.replace(PT_NEW_OLD, PT_NEW_NEW).replace(PT_UPD_OLD, PT_UPD_NEW)
    content = content.replace(KR_NEW_OLD, KR_NEW_NEW).replace(KR_UPD_OLD, KR_UPD_NEW)
    content = content.replace(FUNC_ANCHOR, FUNC_ADD + FUNC_ANCHOR, 1)
    TARGET.write_text(content, encoding="utf-8")
    print("Баннер с результатами встроен (резервная копия: post_schedule.py.bak_results)")


if __name__ == "__main__":
    main()
