import asyncio
import json
import os
import sqlite3
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageColor
from hoshino.modules.priconne import chara
import time
from pathlib import Path
import zhconv
from hoshino.aiorequests import run_sync_func
from hoshino import util
from ..var import Platform

path = Path(__file__).parent # 获取文件所在目录的绝对路径
font_cn_path = str(path / 'fonts' / 'SourceHanSansCN-Medium.otf')  # Path是路径对象，必须转为str之后ImageFont才能读取
font_tw_path = str(path / 'fonts' / 'pcrtwfont.ttf')
ICON_STARS = (1, 3, 6)
TALENT_NAMES = {
    1: "火",
    2: "水",
    3: "风",
    4: "光",
    5: "暗",
}


def _as_nonnegative_int(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def format_talent_stage(clear_count) -> str:
    """将深域通关数转换为最后通关的章节-关卡。"""
    clear_count = _as_nonnegative_int(clear_count)
    if not clear_count:
        return "未通关"
    chapter = (clear_count - 1) // 10 + 1
    stage = (clear_count - 1) % 10 + 1
    return f"{chapter}-{stage}"


def format_talent_progress(data) -> list[str]:
    """返回固定顺序的五属性深域显示文本。"""
    quest_info = data.get("quest_info", {}) if isinstance(data, dict) else {}
    talent_quest = quest_info.get("talent_quest", []) if isinstance(quest_info, dict) else []
    progress = {}
    if isinstance(talent_quest, list):
        for item in talent_quest:
            if not isinstance(item, dict):
                continue
            talent_id = _as_nonnegative_int(item.get("talent_id"))
            if talent_id in TALENT_NAMES:
                progress[talent_id] = _as_nonnegative_int(item.get("clear_count"))

    result = []
    for talent_id, talent_name in TALENT_NAMES.items():
        clear_count = progress.get(talent_id)
        if clear_count is None:
            result.append(f"{talent_name}属性深域：--")
        else:
            result.append(
                f"{talent_name}属性深域：{format_talent_stage(clear_count)}（{clear_count}关）"
            )
    return result


KNIGHT_RANK_DB_ENV = "PCR_KNIGHT_RANK_DB"
# autopcr 与本插件是 modules 下的同级目录，Path 操作会跟随 autopcr 软链接。
MODULES_DIR = Path(__file__).resolve().parents[2]
KNIGHT_RANK_DB_DIR = MODULES_DIR / "autopcr" / "cache" / "db"
# 本地开发时使用 Downloads 中的数据库作为回退。
LOCAL_KNIGHT_RANK_DB = Path(__file__).resolve().parents[3] / "202608281041.db"


def _resolve_knight_rank_db(db_path=None):
    """优先使用配置路径，否则选择服务器缓存目录中最新的数据库。"""
    configured_path = db_path or os.environ.get(KNIGHT_RANK_DB_ENV)
    if configured_path:
        configured_path = Path(configured_path)
        if configured_path.is_file():
            return configured_path
        if configured_path.is_dir():
            candidates = list(configured_path.glob("*.db"))
            if candidates:
                return max(candidates, key=lambda item: item.stat().st_mtime)
        return None

    candidates = list(KNIGHT_RANK_DB_DIR.glob("*.db"))
    if candidates:
        return max(candidates, key=lambda item: item.stat().st_mtime)
    if LOCAL_KNIGHT_RANK_DB.is_file():
        return LOCAL_KNIGHT_RANK_DB
    return None


@lru_cache(maxsize=4)
def _load_knight_rank_table(db_path: str, modified_time: float) -> tuple[tuple[int, int], ...]:
    """从游戏 master.db 读取 (累计经验, 品级) 阈值。"""
    try:
        with sqlite3.connect(db_path) as connection:
            rows = connection.execute(
                "SELECT total_exp, knight_rank "
                "FROM experience_knight_rank ORDER BY total_exp"
            ).fetchall()
    except (OSError, sqlite3.Error):
        return ()

    return tuple(
        (total_exp, rank)
        for total_exp, rank in rows
        if _as_nonnegative_int(total_exp) is not None
        and _as_nonnegative_int(rank) is not None
    )


def rank_from_knight_exp(exp, db_path=None):
    """按累计经验查找已达到的最高公主骑士品级。"""
    exp = _as_nonnegative_int(exp)
    if exp is None:
        return None

    resolved_path = _resolve_knight_rank_db(db_path)
    if resolved_path is None:
        return None
    try:
        modified_time = resolved_path.stat().st_mtime
    except OSError:
        return None
    table = _load_knight_rank_table(str(resolved_path), modified_time)
    rank = None
    for threshold, candidate in table:
        if threshold > exp:
            break
        rank = candidate
    return rank


def format_princess_knight_info(data) -> tuple[str, str]:
    """读取公主骑士品级和累计经验，缺少品级时按经验表换算。"""
    user_info = data.get("user_info", {}) if isinstance(data, dict) else {}
    if not isinstance(user_info, dict):
        user_info = {}

    rank = None
    for key in (
        "princess_knight_rank",
        "princess_knight_rank_level",
        "princess_knight_level",
    ):
        rank = _as_nonnegative_int(user_info.get(key))
        if rank is not None:
            break

    exp = _as_nonnegative_int(user_info.get("princess_knight_rank_total_exp"))
    if rank is None:
        rank = rank_from_knight_exp(exp)
    rank_text = f"公主骑士品级：Lv.{rank}" if rank is not None else "公主骑士品级：未知"
    exp_text = f"累计经验：{exp:,}" if exp is not None else "累计经验：--"
    return rank_text, exp_text


def get_server(platform:int)-> str:
    if platform == Platform.b_id.value:
        return 'bilibili官方服务器'
    elif platform == Platform.qu_id.value:
        return '渠道服第三方服务器'
    else:
        return "台服"

def get_frame(user_id):
    current_dir = path / 'frame.json'
    with open(current_dir, 'r', encoding='UTF-8') as f:
        f_data = json.load(f)
    id_list = list(f_data['customize'].keys())
    if user_id not in id_list:
        frame_tmp = f_data['default_frame']
    else:
        frame_tmp = f_data['customize'][user_id]
    return frame_tmp

def _TraditionalToSimplified(hant_str: str):
    '''
    Function: 将 hant_str 由繁体转化为简体
    '''
    return zhconv.convert(str(hant_str), 'zh-hans')

def _cut_str(obj: str, sec: int):
    """
    按步长分割字符串
    """
    return [obj[i: i+sec] for i in range(0, len(obj), sec)]


def format_viewer_id(viewer_id) -> str:
    """按三位分组返回完整 UID，兼容国服 13 位 UID。"""
    text = _TraditionalToSimplified(str(viewer_id))
    return "  ".join(_cut_str(text, 3))


def normalize_unit_rarity(value, default=3):
    """将接口星级规范到 1-6；异常值回退到默认三星。"""
    rarity = _as_nonnegative_int(value)
    if rarity is None or rarity < 1:
        return default
    return min(rarity, 6)


def _unit_base_id(unit_data) -> int | None:
    raw_id = unit_data.get("id") if isinstance(unit_data, dict) else None
    text = str(raw_id)
    if len(text) < 4 or not text[:4].isdigit():
        return None
    return int(text[:4])


def _star_points(cx, cy, outer_radius, inner_radius):
    import math
    points = []
    for index in range(10):
        radius = outer_radius if index % 2 == 0 else inner_radius
        angle = -math.pi / 2 + index * math.pi / 5
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return points


def draw_unit_stars(draw, rarity, x, y, size=13):
    """在助战头像下绘制最多六颗金星，避免依赖外部星级图片。"""
    rarity = normalize_unit_rarity(rarity)
    for index in range(6):
        color = (250, 190, 55, 255) if index < rarity else (222, 222, 222, 255)
        outline = (169, 122, 25, 255) if index < rarity else (180, 180, 180, 255)
        draw.polygon(_star_points(x + index * (size * 1.45), y, size, size * .42),
                     fill=color, outline=outline)


def icon_rarity_variant(rarity) -> int:
    """将实际星级映射到游戏提供的 1/3/6 星头像资源档位。"""
    rarity = normalize_unit_rarity(rarity)
    if rarity <= 2:
        return 1
    if rarity <= 5:
        return 3
    return 6


def _ensure_chara_icon_dir(unit_id: int) -> None:
    icon_path = Path(chara.R.img(f'priconne/unit/icon_unit_{unit_id}31.png').path)
    icon_path.parent.mkdir(parents=True, exist_ok=True)


def _resource_icon_path(unit_id: int, rarity: int):
    """返回实际星级对应的 1/3/6 星头像资源，找不到时返回 None。"""
    variant = icon_rarity_variant(rarity)
    candidate = Path(chara.R.img(f'priconne/unit/icon_unit_{unit_id}{variant}1.png').path)
    return str(candidate) if candidate.is_file() else None


async def _get_chara_icon_path(unit_id: int, rarity: int = 3) -> str:
    rarity = normalize_unit_rarity(rarity)
    _ensure_chara_icon_dir(unit_id)
    resource_path = _resource_icon_path(unit_id, rarity)
    if resource_path:
        return resource_path
    return (await chara.fromid(unit_id).get_icon()).path

def _generate_info_pic_internal(data, uid, platform, pic_dir):
    '''
    个人资料卡生成
    pic_dir: 已通过异步 get_icon 预解析的头像图标路径，避免触发 icon 属性里的 run_until_complete
    '''
    frame_tmp = get_frame(uid)
    im = Image.open(path / 'img' / 'template.png').convert("RGBA") # 图片模板
    im_frame = Image.open(path / 'img' / 'frame' / f'{frame_tmp}').convert("RGBA") # 头像框
    user_avatar = Image.open(pic_dir).convert("RGBA")
    user_avatar = user_avatar.resize((90, 90))
    im.paste(user_avatar, (44, 150), mask=user_avatar)
    im_frame = im_frame.resize((100, 100))
    im.paste(im=im_frame, box=(39, 145), mask=im_frame)

    cn_font = ImageFont.truetype(font_cn_path, 18) # Path是路径对象，必须转为str之后ImageFont才能读取
    # tw_font = ImageFont.truetype(str(font_tw_path), 18) # 字体有点问题，暂时别用

    font = cn_font # 选择字体

    cn_font_resize = ImageFont.truetype(font_cn_path, 16)
    # tw_font_resize = ImageFont.truetype(font_tw_path, 16) # 字体有点问题，暂时别用

    font_resize = cn_font_resize #选择字体

    draw = ImageDraw.Draw(im)
    font_black = (77, 76, 81, 255)

    # 资料卡 个人信息
    user_name_text = _TraditionalToSimplified(data["user_info"]["user_name"])
    user_name_text = util.filt_message(str(user_name_text))
    team_level_text = _TraditionalToSimplified(data["user_info"]["team_level"])
    team_level_text = util.filt_message(str(team_level_text))
    total_power_text = _TraditionalToSimplified(
        data["user_info"]["total_power"])
    total_power_text = util.filt_message(str(total_power_text))
    clan_name_text = _TraditionalToSimplified(data["clan_name"])
    clan_name_text = util.filt_message(str(clan_name_text))
    user_comment_arr = _TraditionalToSimplified(data["user_info"]["user_comment"])
    user_comment_arr = util.filt_message(str(user_comment_arr))
    user_comment_arr = _cut_str(user_comment_arr, 25)
    last_login_time_text = _TraditionalToSimplified(time.strftime(
        "%Y/%m/%d %H:%M:%S", time.localtime(data["user_info"]["last_login_time"]))).split(' ')

    draw.text((194, 120), user_name_text, font_black, font)

    w, h = font_resize.getsize(team_level_text)
    draw.text((568 - w, 168), team_level_text, font_black, font_resize)
    w, h = font_resize.getsize(total_power_text)
    draw.text((568 - w, 210), total_power_text, font_black, font_resize)
    w, h = font_resize.getsize(clan_name_text)
    draw.text((568 - w, 250), clan_name_text, font_black, font_resize)
    for index, value in enumerate(user_comment_arr):
        draw.text((170, 310 + (index * 22)), value, font_black, font_resize)
    draw.text((34, 350), last_login_time_text[0] + "\n" +
              last_login_time_text[1], font_black, font_resize)
    draw.text((34, 392), get_server(platform), font_black, font_resize)

    # 资料卡 冒险经历
    normal_quest_text = _TraditionalToSimplified(
        data["quest_info"]["normal_quest"][2])
    hard_quest_text = _TraditionalToSimplified(
        data["quest_info"]["hard_quest"][2])
    very_hard_quest_text = _TraditionalToSimplified(
        data["quest_info"]["very_hard_quest"][2])

    w, h = font_resize.getsize(normal_quest_text)
    draw.text((550 - w, 498), normal_quest_text, font_black, font_resize)
    w, h = font_resize.getsize("H" + hard_quest_text +
                           " / VH" + very_hard_quest_text)
    draw.text((550 - w, 530), "H" + hard_quest_text +
              " / VH", font_black, font_resize)
    w, h = font_resize.getsize(very_hard_quest_text)
    draw.text((550 - w, 530), very_hard_quest_text, font_black, font_resize)

    arena_group_text = _TraditionalToSimplified(
        data["user_info"]["arena_group"])
    arena_time_text = _TraditionalToSimplified(time.strftime(
        "%Y/%m/%d", time.localtime(data["user_info"]["arena_time"])))
    arena_rank_text = _TraditionalToSimplified(data["user_info"]["arena_rank"])
    grand_arena_group_text = _TraditionalToSimplified(
        data["user_info"]["grand_arena_group"])
    grand_arena_time_text = _TraditionalToSimplified(time.strftime(
        "%Y/%m/%d", time.localtime(data["user_info"]["grand_arena_time"])))
    grand_arena_rank_text = _TraditionalToSimplified(
        data["user_info"]["grand_arena_rank"])

    w, h = font_resize.getsize(arena_time_text)
    draw.text((550 - w, 598), arena_time_text, font_black, font_resize)
    w, h = font_resize.getsize(arena_group_text+"场")
    draw.text((550 - w, 630), arena_group_text+"场", font_black, font_resize)
    w, h = font_resize.getsize(arena_rank_text+"名")
    draw.text((550 - w, 662), arena_rank_text+"名", font_black, font_resize)
    w, h = font_resize.getsize(grand_arena_time_text)
    draw.text((550 - w, 704), grand_arena_time_text, font_black, font_resize)
    w, h = font_resize.getsize(grand_arena_group_text+"场")
    draw.text((550 - w, 738), grand_arena_group_text+"场", font_black, font_resize)
    w, h = font_resize.getsize(grand_arena_rank_text+"名")
    draw.text((550 - w, 772), grand_arena_rank_text+"名", font_black, font_resize)

    unit_num_text = _TraditionalToSimplified(data["user_info"]["unit_num"])
    open_story_num_text = _TraditionalToSimplified(
        data["user_info"]["open_story_num"])

    w, h = font_resize.getsize(unit_num_text)
    draw.text((550 - w, 844), unit_num_text, font_black, font_resize)
    w, h = font_resize.getsize(open_story_num_text)
    draw.text((550 - w, 880), open_story_num_text, font_black, font_resize)

    tower_cleared_floor_num_text = _TraditionalToSimplified(
        data["user_info"]["tower_cleared_floor_num"])
    tower_cleared_ex_quest_count_text = _TraditionalToSimplified(
        data["user_info"]["tower_cleared_ex_quest_count"])

    w, h = font_resize.getsize(tower_cleared_floor_num_text+"阶")
    draw.text((550 - w, 949), tower_cleared_floor_num_text +
              "阶", font_black, font_resize)
    w, h = font_resize.getsize(tower_cleared_ex_quest_count_text)
    draw.text((550 - w, 984), tower_cleared_ex_quest_count_text,
              font_black, font_resize)

    viewer_id_text = format_viewer_id(data["user_info"]["viewer_id"])
    bbox = draw.textbbox((0, 0), viewer_id_text, font=font)
    viewer_id_width = bbox[2] - bbox[0]
    draw.text((138 + (460 - 138) / 2 - viewer_id_width / 2, 1058),
              viewer_id_text, (255, 255, 255, 255), font=font)

    return im

def _draw_support_position(support_data, im, fnt, rgb, im_frame, bbox, icon_paths):
    """绘制好友、地下城和战队共用的支援小卡。"""
    unit_data = support_data.get('unit_data', {})
    unit_id = _unit_base_id(unit_data)
    if unit_id is None:
        return im
    rarity = normalize_unit_rarity(unit_data.get('unit_rarity'))
    pic_dir = icon_paths[(unit_id, rarity)]

    im_yuansu = Image.open(path / 'img' / 'yuansu.png').convert("RGBA")
    avatar = Image.open(pic_dir).convert("RGBA").resize((115, 115))
    im_yuansu.paste(im=avatar, box=(28, 78), mask=avatar)
    im_frame = im_frame.resize((128, 128))
    im_yuansu.paste(im=im_frame, box=(22, 72), mask=im_frame)

    yuansu_draw = ImageDraw.Draw(im_yuansu)
    draw_unit_stars(yuansu_draw, rarity, 39, 204, size=8)
    icon_name_text = _TraditionalToSimplified(chara.fromid(unit_id).name)
    icon_LV_text = str(unit_data.get('unit_level', '--'))
    icon_rank_text = str(unit_data.get('promotion_level', '--'))
    yuansu_draw.text(xy=(167, 36.86), text=icon_name_text, font=fnt, fill=rgb)
    yuansu_draw.text(xy=(340, 101.8), text=icon_LV_text, font=fnt, fill=rgb)
    yuansu_draw.text(xy=(340, 159.09), text=icon_rank_text, font=fnt, fill=rgb)
    im.paste(im=im_yuansu, box=bbox)
    return im


def _friend_support_position(fr_data, im, fnt, rgb, im_frame, bbox, icon_paths):
    return _draw_support_position(fr_data, im, fnt, rgb, im_frame, bbox, icon_paths)


def _clan_support_position(clan_data, im, fnt, rgb, im_frame, bbox, icon_paths):
    return _draw_support_position(clan_data, im, fnt, rgb, im_frame, bbox, icon_paths)

def _generate_support_pic_internal(data, uid, icon_paths):
    '''
    支援界面图片合成
    icon_paths: {unit_id: path} 已通过异步 get_icon 预解析的图标路径字典
    '''
    frame_tmp = get_frame(uid)
    im = Image.open(path / 'img' / 'support.png').convert("RGBA") # 支援图片模板
    im_frame = Image.open(path / 'img' / 'frame' / f'{frame_tmp}').convert("RGBA") # 头像框

    fnt = ImageFont.truetype(font=font_cn_path, size=30)
    rgb = ImageColor.getrgb('#4e4e4e')

    # 判断玩家设置的支援角色应该存在的位置
    for fr_data in data['friend_support_units']: # 若列表为空，则不会进行循环
        if fr_data['position'] == 1: # 好友支援位1
            bbox = (1284, 156)
            im = _friend_support_position(fr_data, im, fnt, rgb, im_frame, bbox, icon_paths)
        elif fr_data['position'] == 2: # 好友支援位2
            bbox = (1284, 459)
            im = _friend_support_position(fr_data, im, fnt, rgb, im_frame, bbox, icon_paths)

    for clan_data in data['clan_support_units']:
        if clan_data['position'] == 1: # 地下城位置1
            bbox = (43, 156)
            im = _clan_support_position(clan_data, im, fnt, rgb, im_frame, bbox, icon_paths)
        elif clan_data['position'] == 2: # 地下城位置2
            bbox = (43, 459)
            im = _clan_support_position(clan_data, im, fnt, rgb, im_frame, bbox, icon_paths)
        elif clan_data['position'] == 3: # 战队位置1
            bbox = (665, 156)
            im = _clan_support_position(clan_data, im, fnt, rgb, im_frame, bbox, icon_paths)
        elif clan_data['position'] == 4: # 战队位置2
            bbox = (665, 459)
            im = _clan_support_position(clan_data, im, fnt, rgb, im_frame, bbox, icon_paths)

    return im

TALENT_COLORS = {
    1: ((244, 116, 78), (255, 233, 205)),
    2: ((72, 165, 225), (218, 244, 255)),
    3: ((105, 190, 93), (225, 249, 213)),
    4: ((91, 155, 226), (222, 235, 255)),
    5: ((146, 91, 205), (239, 220, 255)),
}


def _draw_talent_icon(draw, box, talent_id):
    """资源不完整时绘制稳定的属性色块占位图标。"""
    left, top, right, bottom = box
    accent, background = TALENT_COLORS[talent_id]
    draw.rounded_rectangle(box, radius=18, fill=background, outline=accent, width=3)
    cx = (left + right) // 2
    cy = (top + bottom) // 2 - 7
    draw.ellipse((cx - 42, cy - 42, cx + 42, cy + 42), fill=accent)
    symbol = ("火", "水", "风", "光", "暗")[talent_id - 1]
    symbol_font = ImageFont.truetype(font_cn_path, 44)
    bounds = draw.textbbox((0, 0), symbol, font=symbol_font)
    draw.text((cx - (bounds[2] - bounds[0]) / 2, cy - (bounds[3] - bounds[1]) / 2),
              symbol, fill=(255, 255, 255), font=symbol_font)


def _generate_talent_pic_internal(data, uid):
    """按深域参考图生成五属性横向进度图。"""
    width, height = 1280, 720
    image = Image.new("RGB", (width, height), (255, 181, 221))
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(font_cn_path, 38)
    label_font = ImageFont.truetype(font_cn_path, 28)
    body_font = ImageFont.truetype(font_cn_path, 30)
    small_font = ImageFont.truetype(font_cn_path, 24)
    title_color = (80, 126, 210)
    text_color = (75, 75, 82)

    draw.rounded_rectangle((42, 28, width - 42, height - 28), radius=38,
                           fill=(255, 255, 255), outline=(255, 245, 252), width=8)
    title = "深域进度"
    title_width = draw.textbbox((0, 0), title, font=title_font)[2]
    draw.text(((width - title_width) // 2, 52), title, fill=title_color, font=title_font)
    draw.line((84, 120, width - 84, 120), fill=(184, 211, 244), width=3)

    progress = format_talent_progress(data)
    card_width, card_height = 202, 278
    gap = 22
    start_x = (width - (card_width * 5 + gap * 4)) // 2
    for index, progress_text in enumerate(progress):
        talent_id = index + 1
        left = start_x + index * (card_width + gap)
        top = 152
        right, bottom = left + card_width, top + card_height
        accent, background = TALENT_COLORS[talent_id]
        draw.rounded_rectangle((left, top, right, bottom), radius=18,
                               fill=(255, 255, 255), outline=(224, 224, 234), width=2)
        _draw_talent_icon(draw, (left + 21, top + 20, right - 21, top + 178), talent_id)
        stage = progress_text.split("：", 1)[-1].split("（", 1)[0]
        stage_bounds = draw.textbbox((0, 0), stage, font=body_font)
        draw.text((left + (card_width - (stage_bounds[2] - stage_bounds[0])) / 2,
                   top + 204), stage, fill=text_color, font=body_font)
        draw.line((left + 22, bottom - 34, right - 22, bottom - 34), fill=(199, 218, 244), width=2)
        label = ("火属性", "水属性", "风属性", "光属性", "暗属性")[index]
        label_bounds = draw.textbbox((0, 0), label, font=small_font)
        draw.text((left + (card_width - (label_bounds[2] - label_bounds[0])) / 2,
                   bottom - 28), label, fill=accent, font=small_font)

    rank_text, exp_text = format_princess_knight_info(data)
    for row, (label, value) in enumerate((("公主骑士经验", exp_text.replace("累计经验：", "")),
                                           ("公主骑士RANK", rank_text.replace("公主骑士品级：Lv.", "")))):
        y = 472 + row * 74
        label_box = (472, y, 684, y + 45)
        draw.rounded_rectangle(label_box, radius=8, fill=(91, 151, 231))
        draw.text((label_box[0] + 16, y + 5), label, fill=(255, 255, 255), font=label_font)
        draw.text((712, y + 5), value, fill=text_color, font=body_font)
        draw.line((712, y + 48, 1000, y + 48), fill=(184, 211, 244), width=2)

    draw.text((width - 235, height - 58), "数据仅供参考", fill=(110, 110, 120), font=small_font)
    return image


async def generate_talent_pic(data, uid):
    """在工作线程中生成独立的深域信息图。"""
    return await run_sync_func(_generate_talent_pic_internal, data, uid)


async def generate_support_pic(data, uid):
    '''
    在 async 上下文异步预解析所有支援角色图标路径，再进入线程执行图片合成
    '''
    icon_paths = {}
    support_units = (
        list(data.get('friend_support_units', []))
        + list(data.get('clan_support_units', []))
    )
    icon_keys = set()
    for support_data in support_units:
        unit_data = support_data.get('unit_data', {})
        unit_id = _unit_base_id(unit_data)
        if unit_id is None:
            continue
        rarity = normalize_unit_rarity(unit_data.get('unit_rarity'))
        icon_keys.add((unit_id, rarity))

    # 同一张头像只加载一次；不同头像并发下载，减少支援图的网络等待。
    loaded_icons = await asyncio.gather(
        *(_get_chara_icon_path(unit_id, rarity) for unit_id, rarity in icon_keys)
    )
    icon_paths.update(zip(icon_keys, loaded_icons))
    return await run_sync_func(_generate_support_pic_internal, data, uid, icon_paths)

async def generate_info_pic(data, uid, platform):
    '''
    在 async 上下文异步预解析头像图标路径，再进入线程执行图片合成
    '''
    try:
        id_favorite = int(str(data['favorite_unit']['id'])[0:4])
    except (KeyError, TypeError, ValueError):
        id_favorite = 1000
    pic_dir = await _get_chara_icon_path(id_favorite)
    return await run_sync_func(_generate_info_pic_internal, data, uid, platform, pic_dir)
