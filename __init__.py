import asyncio
from datetime import datetime
import os
from json import load, dump
import re
from typing import Dict, List
from nonebot import get_bot, on_command, on_startup
from hoshino import priv, Service
from hoshino.config import SUPERUSERS
from hoshino.typing import HoshinoBot, CQEvent
from nonebot import NoticeSession, MessageSegment
from .utils import bind_pcrid, detial_query, get_platform_id, get_tw_platform, query_loop, user_query, get_qid
from .query import login_all, query_all
from .var import BaseSet, LoadBase, platform_dict, query_cache, queue_dict, private_dict, Platform, Priority
from .tool import refresh_account
from .img.text2img import image_draw
from .database.dal import pcr_sqla, PCRBind

sv_b = Service('b服竞技场推送', help_="发送【竞技场帮助】", bundle='pcr查询')
sv_qu = Service('渠服竞技场推送', help_="发送【渠竞技场帮助】", bundle='pcr查询')
sv_tw = Service('台服竞技场推送', help_="发送【台竞技场帮助】", bundle='pcr查询')


@sv_tw.on_fullmatch('台竞技场帮助')
@sv_b.on_fullmatch('竞技场帮助')
@sv_qu.on_fullmatch('渠竞技场帮助')
async def send_jjchelp(bot: HoshinoBot, ev: CQEvent):
    platform_id = get_platform_id(ev)
    platform_name = platform_dict.get(platform_id, "")
    sv_help = f'''\t\t\t\t\t【{platform_name}竞技场帮助】
可以添加的订阅：[jjc][pjjc][排名上升][上线提醒]
# 排名上升提醒对jjc和pjjc同时生效
# 每个QQ号至多添加8个uid的订阅
# 默认开启jjc、pjjc，关闭排名上升、上线提醒
# 手动查询时，返回昵称、jjc/pjjc排名、场次、
jjc/pjjc当天排名上升次数、最后登录时间。
# 支持群聊使用。只允许群聊使用！！！
------------------------------------------------
命令格式：
# 只绑定1个uid时，绑定的序号可以不填。
[绑定的序号]1~8对应绑定的第1~8个uid，序号0表示全部
1）{platform_name}竞技场绑定[uid][昵称]（昵称可省略）
2）{platform_name}删除竞技场绑定[绑定的序号]（这里序号不可省略）
3）{platform_name}清空竞技场绑定
4）{platform_name}竞技场查询[uid]/@某人
（uid可省略，@为查别人，uid优先级大于at）
5）{platform_name}竞技场订阅状态[@某人](@某人省略为查自己)
6）{platform_name}竞技场修改昵称 [绑定的序号] [新昵称]
7）{platform_name}竞技场设置[开启/关闭][订阅内容][绑定的序号]
8）{platform_name}竞技场/击剑记录[绑定的序号]（序号可省略）
9）{platform_name}竞技场设置1110[绑定的序号]
# 0表示关闭，1表示开启
# 4个数字依次代表jjc、pjjc、排名上升、上线提醒
# 例如：“竞技场设置1011 2” “竞技场设置1110 0”
# 上线提醒：第4位表示上线提醒等级，可以写0~3
0表示关闭，1表示10分钟cd，仅在2点半~3点报，
2表示10分钟cd，全天报；3表示1分钟cd全天报。
每天5点会把上线提醒等级3改成2，有需要的可以再次手动开启。
11）在本群推送（限群聊发送，无需好友）'''
    if not priv.check_priv(ev, priv.SUPERUSER):
        pic = image_draw(sv_help)
    else:
        sv_help_adm = f'''------------------------------------------------
管理员帮助：
1）pcrjjc负载查询
2）{platform_name}pcrjjc删除绑定[qq号]
3）{platform_name}pcrjjc关闭私聊推送
'''
        pic = image_draw(sv_help+sv_help_adm)
    await bot.send(ev, f'[CQ:image,file={pic}]')

# ========================================查询========================================


@sv_b.on_fullmatch('查询竞技场订阅数')
@sv_qu.on_fullmatch('渠查询竞技场订阅数')
@sv_tw.on_fullmatch('台查询竞技场订阅数')
async def pcrjjc_number(bot: HoshinoBot, ev: CQEvent):
    platform_id = get_platform_id(ev)
    await bot.send(ev, f'当前竞技场已订阅的账号数量为【{len(await pcr_sqla.get_bind(platform_id))}】个')


@sv_b.on_rex(r'^竞技场查询 ?(\d+)?$')
@sv_qu.on_rex(r'^渠竞技场查询 ?(\d+)?$')
@sv_tw.on_rex(r'^台竞技场查询 ?(\d+)?$')
async def on_query_arena(bot: HoshinoBot, ev: CQEvent):
    ret: re.Match = ev['match']
    qid = get_qid(ev)
    platform_id = get_platform_id(ev)
    query_dict: Dict[int, int] = {}
    if ret.group(1):
        valid_len = 13 if platform_id != Platform.tw_id.value else 10
        if (len(ret.group(1))) != (valid_len):
            await bot.send(ev, f'位数不对，uid是{valid_len}位的！')
            return
        pcrid = int(ret.group(1))
        query_list = [PCRBind(platform=platform_id, pcrid=pcrid)]  # 手动查询的列表
        query_dict[pcrid] = 0
    else:
        query_list: List[PCRBind] = await pcr_sqla.get_bind(platform_id, qid)
        for i, bind in enumerate(query_list):
            query_dict[bind.pcrid] = i
    query_cache[ev.user_id] = []
    await query_all(query_list, platform_id, user_query, {"bot": bot, "ev": ev, "info": query_dict, "platform": platform_id}, Priority.query_user.value)


@sv_b.on_fullmatch('竞技场订阅状态')
@sv_qu.on_fullmatch('渠竞技场订阅状态')
@sv_tw.on_fullmatch('台竞技场订阅状态')
async def send_arena_sub_status(bot: HoshinoBot, ev: CQEvent):
    qid = get_qid(ev)
    platfrom_id = get_platform_id(ev)
    user_bind: List[PCRBind] = await pcr_sqla.get_bind(platfrom_id, qid)
    if not user_bind:
        await bot.send(ev, '您还没有绑定竞技场！')
        return
    gid = ev.group_id
    member_info = await bot.get_group_member_info(group_id=gid, user_id=qid)
    name = member_info["card"] or member_info["nickname"]
    reply = f'{name}（{qid}）的竞技场订阅列表：\n\n群号：{user_bind[0].group}\n推送方式：{"私聊推送" if user_bind[0].private else "群聊推送"}\n'
    for i, bind in enumerate(user_bind):
        reply += f'\n【{i+1}】{bind.name}（{bind.pcrid}）\n'
        reply += "" if platfrom_id != Platform.tw_id.value else f"服务器：{get_tw_platform(bind.pcrid)}\n"
        noticeType = '推送内容：'
        if bind.jjc_notice:
            noticeType += 'jjc、'
        if bind.pjjc_notice:
            noticeType += 'pjjc、'
        if bind.up_notice:
            noticeType += '排名上升、'
        if bind.online_notice:
            noticeType += f'上线提醒LV{bind.online_notice}、'

        if noticeType == '推送内容：':
            noticeType += '无'
        else:
            noticeType = noticeType.strip('、')

        reply += noticeType + '\n'
    reply += '###上线提醒LV越高，提醒越频繁。详情见竞技场帮助\n'
    await bot.send(ev, f'[CQ:image,file={image_draw(reply)}]')


@sv_b.on_rex(r'^(?:击剑|竞技场)记录 ?(\d)?$')
@sv_qu.on_rex(r'^渠(?:击剑|竞技场)记录 ?(\d)?$')
@sv_tw.on_rex(r'^台(?:击剑|竞技场)记录 ?(\d)?$')
async def jjc_log_query(bot: HoshinoBot, ev: CQEvent):
    qid = get_qid(ev)
    platform_id = get_platform_id(ev)
    user_bind: List[PCRBind] = await pcr_sqla.get_bind(platform_id, qid)

    if not user_bind:
        await bot.send(ev, '您还没有绑定竞技场！')
        return

    ret: re.Match = ev["match"]
    pcrid_id_input = int(ret.group(1)) if ret.group(1) else 0

    if pcrid_id_input > len(user_bind):
        await bot.send(ev, '序号超出范围，请检查您绑定的竞技场列表')
        return

    msg = '没有击剑记录！'
    member_info = await bot.get_group_member_info(group_id=ev.group_id, user_id=qid)
    if jjc_historys := await pcr_sqla.get_history(platform_id, qid, user_bind[pcrid_id_input-1].pcrid if pcrid_id_input else 0):
        msg = f'\t\t\t\t【{member_info["card"] or member_info["nickname"]}的击剑记录】\n' + "\n".join(
            [f"{datetime.fromtimestamp(history.date).strftime('%H:%M:%S')} {history.name} {'jjc ' if not history.item else 'pjjc'}：{history.before}->{history.after} [{'▲' if history.before > history.after else '▽'}{abs(history.after-history.before)}]"
             for history in jjc_historys])

    await bot.send(ev, f'[CQ:image,file={image_draw(msg)}]')

# ========================================竞技场绑定========================================


@sv_b.on_rex(r'^竞技场绑定 ?(\d+) ?(\S+)?$')
@sv_qu.on_rex(r'^渠竞技场绑定 ?(\d+) ?(\S+)?$')
@sv_tw.on_rex(r'^台竞技场绑定 ?(\d+) ?(\S+)?$')
async def on_arena_bind(bot: HoshinoBot, ev: CQEvent):
    ret: re.Match = ev["match"]
    if len(nickname := ret.group(2) if ret.group(2) else "") > 12:
        await bot.send(ev, '昵称不能超过12个字，换个短一点的昵称吧~')
        return
    pcr_id = int(ret.group(1))
    platform_id = get_platform_id(ev)
    await query_all([PCRBind(platform=platform_id, pcrid=pcr_id, name=nickname, group=ev.group_id, user_id=ev.user_id)], platform_id, bind_pcrid,
                {"bot": bot, "ev": ev, "info": {"platform": platform_id, "pcrid": pcr_id, "name": nickname, "group": ev.group_id, "user_id": ev.user_id}}, Priority.bind.value)


@sv_b.on_rex(r'^删除竞技场绑定 ?(\d)?$')
@sv_qu.on_rex(r'^渠删除竞技场绑定 ?(\d)?$')
@sv_tw.on_rex(r'^台删除竞技场绑定 ?(\d)?$')
async def delete_arena_sub(bot: HoshinoBot, ev: CQEvent):
    qid = ev.user_id
    ret: re.Match = ev["match"]
    if not ret.group(1):
        await bot.send(ev, '输入格式不对！“删除竞技场绑定+【序号】”（序号不可省略）')
        return
    platform_id = get_platform_id(ev)
    user_bind: List[PCRBind] = await pcr_sqla.get_bind(platform_id, qid)
    pcrid_num = len(user_bind)
    if 0 < (pcrid_id := int(ret.group(1))) <= pcrid_num:
        delete_bind = user_bind[pcrid_id-1]
        result = f'您已成功删除：【{pcrid_id}】{delete_bind.name}（{delete_bind.pcrid}）'
        await pcr_sqla.delete_bind(qid, platform_id, delete_bind.pcrid)
        await bot.send(ev, result)
    else:
        await bot.send(ev, '输入的序号超出范围！')


@sv_b.on_fullmatch('清空竞技场绑定')
@sv_qu.on_fullmatch('渠清空竞技场绑定')
@sv_tw.on_fullmatch('台清空竞技场绑定')
async def pcrjjc_del(bot: HoshinoBot, ev: CQEvent):
    qid = ev.user_id
    platform_id = get_platform_id(ev)
    user_bind: List[PCRBind] = await pcr_sqla.get_bind(platform_id, qid)
    if not user_bind:
        await bot.send(ev, '您还没有绑定竞技场！')
        return
    reply = '删除成功！\n' + \
        "\n".join([f'【{i+1}】{bind.name}\n（{bind.pcrid}）' for i,
                  bind in enumerate(user_bind)])
    await pcr_sqla.delete_bind(qid, platform_id)
    await bot.send(ev, reply)

# ========================================竞技场设置========================================


@sv_b.on_rex(r'^竞技场修改昵称 ?(\d)? (\S+)$')
@sv_qu.on_rex(r'^渠竞技场修改昵称 ?(\d)? (\S+)$')
@sv_tw.on_rex(r'^台竞技场修改昵称 ?(\d)? (\S+)$')
async def change_nickname(bot: HoshinoBot, ev: CQEvent):
    qid = ev.user_id
    platform_id = get_platform_id(ev)
    user_bind: List[PCRBind] = await pcr_sqla.get_bind(platform_id, qid)

    if not user_bind:
        await bot.send(ev, '您还没有绑定竞技场！')
        return

    pcrid_num = len(user_bind)
    ret: re.Match = ev["match"]
    if not (pcrid_id := ret.group(1)) and pcrid_num != 1:
        await bot.send(ev, '您绑定了多个uid，更改昵称时需要加上序号。')
        return

    pcrid_id = int(pcrid_id) if pcrid_id else 1

    if len(ret.group(2)) > 12:
        await bot.send(ev, '昵称不能超过12个字，换个短一点的昵称吧~')
        return

    if pcrid_id > pcrid_num or not pcrid_num:
        await bot.send(ev, '序号超出范围，请检查您绑定的竞技场列表')
        return

    name = ret.group(2)
    await pcr_sqla.update_bind(platform_id, {"name": name}, qid, user_bind[pcrid_id-1].pcrid)
    await bot.send(ev, '更改成功！')


@sv_b.on_fullmatch('在本群推送')
@sv_qu.on_fullmatch('渠在本群推送')
@sv_tw.on_fullmatch('台在本群推送')
async def group_set(bot: HoshinoBot, ev: CQEvent):
    await pcr_sqla.update_bind(get_platform_id(ev), {"group": ev.group_id, "private": False}, ev.user_id)
    await bot.send(ev, '设置成功！已为您开启推送。')


@on_command('private_notice', aliases=('换私聊推送', '渠换私聊推送', '台换私聊推送'), only_to_me=False)
async def private_notice(session: NoticeSession):
    platform_id = get_platform_id(session.event)
    if len(await pcr_sqla.get_private(platform_id)) >= private_dict[platform_id]:
        await session.send('私聊推送用户已达上限！')
        return
    if session.ctx['message_type'] != 'private':
        await session.send('仅限好友私聊使用！')
        return
    bot = get_bot()
    qid = session.ctx['user_id']
    await pcr_sqla.update_bind(platform_id, {"private": True}, qid)
    await session.send('设置成功！已为您开启推送。已通知管理员！')
    await bot.send_private_msg(user_id=SUPERUSERS[0], message=f'{qid}开启了私聊jjc推送！')


@sv_b.on_rex(r'^竞技场设置 ?(开启|关闭) ?(jjc|pjjc|排名上升|上线提醒) ?(\d)?$')
@sv_qu.on_rex(r'^渠竞技场设置 ?(开启|关闭) ?(jjc|pjjc|排名上升|上线提醒) ?(\d)?$')
@sv_tw.on_rex(r'^台竞技场设置 ?(开启|关闭) ?(jjc|pjjc|排名上升|上线提醒) ?(\d)?$')
async def set_noticeType(bot: HoshinoBot, ev: CQEvent):
    qid = ev.user_id
    ret: re.Match = ev["match"]
    turn_on = True if str(ret.group(1)) == '开启'else False
    change = ret.group(2)
    pcrid_id = int(ret.group(3)) if ret.group(
        3) else 1 if pcrid_num == 1 else -1
    platform_id = get_platform_id(ev)
    user_bind: List[PCRBind] = await pcr_sqla.get_bind(platform_id, qid)

    if not user_bind:
        await bot.send(ev, '您还没有绑定jjc，绑定方式：\n[竞技场绑定 uid] uid在pcr个人简介里')
        return

    pcrid_num = len(user_bind)  # 这个qq号绑定的pcrid个数

    if 0 <= pcrid_id <= pcrid_num:  # 设置成功！
        if change == 'jjc':
            change_dict = {"jjc_notice": turn_on}
        elif change == 'pjjc':
            change_dict = {"pjjc_notice": turn_on}
        elif change == '排名上升':
            change_dict = {"up_notice": turn_on}
        elif change == '上线提醒':
            change_dict = {"online_notice": 1 if turn_on else 0}
        reply = '设置成功！'
        await pcr_sqla.update_bind(platform_id, change_dict, qid, user_bind[pcrid_id-1].pcrid if pcrid_id else None)
    else:
        reply = '序号超出范围或者绑定多个没填序号，请检查您绑定的竞技场列表'

    await bot.send(ev, reply)


@sv_b.on_rex(r'^竞技场设置 ?([01]{3}[0123]) ?(\d)?$')
@sv_qu.on_rex(r'^渠竞技场设置 ?([01]{3}[0123]) ?(\d)?$')
@sv_tw.on_rex(r'^台竞技场设置 ?([01]{3}[0123]) ?(\d)?$')
async def set_allType(bot: HoshinoBot, ev: CQEvent):
    qid = ev.user_id
    platform_id = get_platform_id(ev)
    user_bind: List[PCRBind] = await pcr_sqla.get_bind(platform_id, qid)
    if not user_bind:
        await bot.send(ev, '您还没有绑定竞技场！')
        return
    ret: re.Match = ev["match"]
    pcrid_num = len(user_bind)
    change: str = ret.group(1)
    pcrid_id = int(ret.group(2)) if ret.group(
        2) else 1 if pcrid_num == 1 else -1
    if 0 <= pcrid_id <= pcrid_num:
        change_dict = {}
        change_dict["jjc_notice"] = bool(int(change[0]))
        change_dict["pjjc_notice"] = bool(int(change[1]))
        change_dict["up_notice"] = bool(int(change[2]))
        change_dict["online_notice"] = int(change[3])
        reply = '设置成功！'
        await pcr_sqla.update_bind(platform_id, change_dict, qid, user_bind[pcrid_id-1].pcrid if pcrid_id else None)
    else:
        reply = '序号超出范围或者绑定多个没填序号，请检查您绑定的竞技场列表'
    await bot.send(ev, reply)

# ========================================管理员指令========================================


@sv_b.on_fullmatch('pcrjjc负载查询')
async def load_query(bot: HoshinoBot, ev: CQEvent):
    if not priv.check_priv(ev, priv.SUPERUSER):
        return
    load: LoadBase = await pcr_sqla.query_load()
    msg = f'''pcrjjc负载：
B服：
群聊用户数量：{load.b_group_user} 群聊绑定的uid：{load.b_group_pcrid}个
私聊用户数量：{load.b_private_user} 私聊绑定的uid：{load.b_private_pcrid}个
昨天推送次数：{load.b_yesterday_send} 今天推送次数：{load.b_today_send}
渠道服：
群聊用户数量：{load.qu_group_user} 群聊绑定的uid：{load.qu_group_pcrid}个
私聊用户数量：{load.qu_private_user} 私聊绑定的uid：{load.qu_private_pcrid}个
昨天推送次数：{load.qu_yesterday_send} 今天推送次数：{load.qu_today_send}
台服：
群聊用户数量：{load.tw_group_user} 群聊绑定的uid：{load.tw_group_pcrid}个
私聊用户数量：{load.tw_private_user} 私聊绑定的uid：{load.tw_private_pcrid}个
昨天推送次数：{load.tw_yesterday_send} 今天推送次数：{load.tw_today_send}'''
    pic = image_draw(msg)
    await bot.send(ev, f'[CQ:image,file={pic}]')


@sv_b.on_fullmatch('pcrjjc关闭私聊推送')
@sv_qu.on_fullmatch('渠pcrjjc关闭私聊推送')
@sv_tw.on_fullmatch('台pcrjjc关闭私聊推送')
async def no_private(bot: HoshinoBot, ev: CQEvent):
    if not priv.check_priv(ev, priv.SUPERUSER):
        return
    platform_id = get_platform_id(ev)
    await pcr_sqla.update_bind(platform_id, {"private": False})
    await bot.send(ev, '所有设置为私聊推送的用户的推送已关闭！')


@sv_b.on_rex(r'^pcrjjc删除绑定 ?(\d{6,10})')
@sv_qu.on_rex(r'^渠pcrjjc删除绑定 ?(\d{6,10})')
@sv_tw.on_rex(r'^台pcrjjc删除绑定 ?(\d{6,10})')
async def del_binds(bot: HoshinoBot, ev: CQEvent):
    if not priv.check_priv(ev, priv.SUPERUSER):
        return
    ret: re.Match = ev["match"]
    qid = int(ret.group(1))
    platform_id = get_platform_id(ev)
    user_bind: List[PCRBind] = await pcr_sqla.get_bind(platform_id, qid)
    if user_bind:
        await pcr_sqla.delete_bind(qid, platform_id)
        reply = '删除成功！'
    else:
        reply = '绑定列表中找不到这个qq号！'
    await bot.send(ev, reply)

# ========================================头像框========================================

# 头像框设置文件不存在就创建文件，并且默认彩色
current_dir = os.path.join(os.path.dirname(__file__), 'frame.json')
if not os.path.exists(current_dir):
    data = {"default_frame": "color.png", "customize": {}}
    with open(current_dir, 'w', encoding='UTF-8') as f:
        dump(data, f, indent=4, ensure_ascii=False)


@sv_b.on_rex(r'^详细查询 ?(\d+)?$')
@sv_qu.on_rex(r'^渠详细查询 ?(\d+)?$')
@sv_tw.on_rex(r'^台详细查询 ?(\d+)?$')
async def on_query_arena_all(bot: HoshinoBot, ev: CQEvent):
    ret: re.Match = ev['match']
    id = ret.group(1)
    if not id:
        await bot.send(ev, '请在详细查询后带上uid或编号', at_sender=True)
        return
    qid = get_qid(ev)
    platform_id = get_platform_id(ev)
    user_bind: List[PCRBind] = await pcr_sqla.get_bind(platform_id, qid)
    if len(id) == 1:
        if not user_bind:
            await bot.send(ev, '您还未绑定竞技场', at_sender=True)
            return
        if len(user_bind) < int(id):
            await bot.send(ev, '输入的序号超出范围，可发送竞技场查询查看你的绑定', at_sender=True)
            return
    bind = PCRBind(platform=platform_id, pcrid=int(id)) if len(
        id) > 1 else user_bind[int(id) - 1]
    await query_all([bind], platform_id, detial_query, {"bot": bot, "ev": ev, "platform":platform_id}, Priority.detial_query.value)


@sv_b.on_prefix('竞技场换头像框', '更换竞技场头像框', '更换头像框')
async def change_frame(bot: HoshinoBot, ev: CQEvent):
    user_id = ev.user_id
    frame_tmp = ev.message.extract_plain_text()
    path = os.path.join(os.path.dirname(__file__), 'img/frame/')
    frame_list = os.listdir(path)
    if not frame_list:
        await bot.send(ev, 'img/frame/路径下没有任何头像框，请联系维护组检查目录')
    if frame_tmp not in frame_list:
        msg = f'文件名输入错误，命令样例：\n更换头像框 color.png\n目前可选文件有：\n' + \
            '\n'.join(frame_list)
        await bot.send(ev, msg)
    data = {str(user_id): frame_tmp}
    current_dir = os.path.join(os.path.dirname(__file__), 'frame.json')
    with open(current_dir, 'r', encoding='UTF-8') as f:
        f_data = load(f)
    f_data['customize'] = data
    with open(current_dir, 'w', encoding='UTF-8') as rf:
        dump(f_data, rf, indent=4, ensure_ascii=False)
    await bot.send(ev, f'已成功选择头像框:{frame_tmp}')
    frame_path = os.path.join(os.path.dirname(
        __file__), f'img/frame/{frame_tmp}')
    msg = MessageSegment.image(f'file:///{os.path.abspath(frame_path)}')
    await bot.send(ev, msg)


@sv_b.on_fullmatch('查竞技场头像框', '查询竞技场头像框', '查询头像框')
async def see_a_see_frame(bot: HoshinoBot, ev: CQEvent):
    user_id = str(ev.user_id)
    current_dir = os.path.join(os.path.dirname(__file__), 'frame.json')
    with open(current_dir, 'r', encoding='UTF-8') as f:
        f_data = load(f)
    id_list = list(f_data['customize'].keys())
    if user_id not in id_list:
        frame_tmp = f_data['default_frame']
    else:
        frame_tmp = f_data['customize'][user_id]
    path = os.path.join(os.path.dirname(__file__), f'img/frame/{frame_tmp}')
    msg = MessageSegment.image(f'file:///{os.path.abspath(path)}')
    await bot.send(ev, msg)

# ========================================AUTO========================================


@on_startup
async def on_arena_schedule():
    if not BaseSet.mode.value:
        await refresh_account()
        await login_all()
    loop = asyncio.get_event_loop()
    for platform in range(0, 2+1):
        if queue_dict[platform] or BaseSet.mode.value:
            loop.create_task(query_loop(platform))


@sv_b.on_notice('group_decrease.leave', 'group_decrease.kick')
@sv_qu.on_notice('group_decrease.leave', 'group_decrease.kick')
@sv_tw.on_notice('group_decrease.leave', 'group_decrease.kick')
async def leave_notice(session: NoticeSession):
    uid = session.ctx['user_id']
    gid = session.ctx['group_id']
    if await pcr_sqla.get_bind(user_id=uid, group=gid):
        bot = get_bot()
        await pcr_sqla.delete_bind(uid, group=gid)
        await bot.send_group_msg(group_id=gid, message=f'{uid}退群了，已自动删除其绑定在本群的竞技场订阅推送')
