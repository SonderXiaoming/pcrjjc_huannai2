import asyncio
from copy import deepcopy
from datetime import datetime
import traceback
from typing import List
from .img.text2img import image_draw
from hoshino.util import pic2b64
from .database.dal import JJCHistory, pcr_sqla, PCRBind
from .query import query_all
from .img.create_img import generate_info_pic, generate_support_pic
from ..multicq_send import group_send, private_send
from nonebot import MessageSegment, logger
from hoshino.typing import CQEvent
from .var import NoticeType, Platform, platform_dict, platform_tw, query_cache, cache, lck, jjc_log

class ApiException(Exception):

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def get_platform_id(ev: CQEvent) -> int:
    info: str = ev.raw_message
    return platform_dict.get(info[0], Platform.b_id.value)

def get_qid(ev: CQEvent) -> int:
    qid = ev.user_id
    for message in ev.message:
        if message.type == 'at':
            if message.data['qq'] != 'all':
                return int(message.data['qq'])
    return qid

def get_tw_platform(pcrid:int) -> str:
    return platform_tw[pcrid//1000000000]

async def query_loop(platform: int):
    start = datetime.now().timestamp()
    while True:
        try:
            logger.info(f"{platform_dict.get(platform, '')}竞技场推送开始")
            binds = await pcr_sqla.get_bind(platform)
            if sleep_time := await query_all(binds, platform, query_rank):
                await asyncio.sleep(sleep_time)
            await asyncio.sleep(1)
            logger.info(f"{platform_dict.get(platform, '')}竞技场推送结束，用时{int(datetime.now().timestamp()-start)-1}")
            start = datetime.now().timestamp()
            await pcr_sqla.insert_history(jjc_log[platform])
            jjc_log[platform].clear()
        except:
            logger.error(traceback.print_exc())


async def query_rank(data):
    global cache, timeStamp
    timeStamp = int(datetime.now().timestamp())
    try:
        info = data["res"]['user_info']
    except:
        return
    bind: PCRBind = data["bind_info"]
    res = [int(info['arena_rank']), int(info['grand_arena_rank']),
           int(info['last_login_time'])]
    if (bind.pcrid, bind.user_id, bind.platform) not in cache:
        cache[(bind.pcrid, bind.user_id, bind.platform)] = res
    else:
        last = deepcopy(cache[(bind.pcrid, bind.user_id, bind.platform)])
        cache[(bind.pcrid, bind.user_id, bind.platform)][0] = res[0]
        cache[(bind.pcrid, bind.user_id, bind.platform)][1] = res[1]
        cache[(bind.pcrid, bind.user_id, bind.platform)][2] = res[2]
        if res[0] != last[0]:
            await sendNotice(res[0], last[0], bind, NoticeType.jjc.value)
        if res[1] != last[1]:
            await sendNotice(res[1], last[1], bind, NoticeType.pjjc.value)
        if res[2] != last[2]:
            await sendNotice(res[2], last[2], bind, NoticeType.online.value)


async def detial_query(data):
    res = data["res"]
    bot = data["bot"]
    ev = data["ev"]
    pcrid = data["uid"]
    platfrom = data["platform"]
    try:
        logger.info('开始生成竞技场查询图片...')  # 通过log显示信息
        result_image = await generate_info_pic(res, pcrid, platfrom)
        result_image = pic2b64(result_image)  # 转base64发送，不用将图片存本地
        result_image = MessageSegment.image(result_image)
        result_support = await generate_support_pic(res, pcrid)
        result_support = pic2b64(result_support)  # 转base64发送，不用将图片存本地
        result_support = MessageSegment.image(result_support)
        logger.info('竞技场查询图片已准备完毕！')
        await bot.send_group_msg(self_id=ev.self_id, group_id=int(ev.group_id), message=f"\n{str(result_image)}\n{result_support}")
    except ApiException as e:
        await bot.send_group_msg(self_id=ev.self_id, group_id=int(ev.group_id), message=f'查询出错，{e}')


async def user_query(data: dict):
    global lck
    pcrid = data["uid"]
    info = data["info"]
    platfrom = data["platform"]
    try:
        res = data["res"]['user_info']
        last_login = datetime.fromtimestamp(
            int(res["last_login_time"])).strftime("%H：%M")
        jjc_up, grand_jjc_up = await pcr_sqla.get_up_num(platfrom, pcrid, int(datetime.now().timestamp()))
        extra = "" if platfrom != Platform.tw_id.value else f"服务器：{get_tw_platform(pcrid)}\n"
        extra += f'''上升: {jjc_up}次 / {grand_jjc_up}次\n'''
        query = f'【{info[pcrid]+1}】{res["user_name"]}\n{res["arena_rank"]}({res["arena_group"]}场) / {res["grand_arena_rank"]}({res["grand_arena_group"]}场)\n{extra}最近上号{last_login}\n\n'
    except:
        logger.error(traceback.print_exc())
        query = "查询失败"

    async with lck:
        ev = data["ev"]
        query_list: list = query_cache[ev.user_id]
        query_list.append(query)
        if len(query_list) == len(info):
            bot = data["bot"]
            query_list.sort()
            pic = image_draw(''.join(query_list))
            await bot.send_group_msg(self_id=ev.self_id, group_id=int(ev.group_id), message=f'[CQ:image,file={pic}]')


async def bind_pcrid(data):
    bot = data["bot"]
    ev = data["ev"]
    pcrid = data["uid"]
    info: dict = data["info"]
    try:
        res = data["res"]['user_info']
        qid = ev.user_id
        have_bind: List[PCRBind] = await pcr_sqla.get_bind(info["platform"], qid)
        bind_num = len(have_bind)
        if bind_num >= 8:
            reply = '您订阅了太多账号啦！'
        elif pcrid in [bind.pcrid for bind in have_bind]:
            reply = '这个uid您已经订阅过了，不要重复订阅！'
        else:
            info["name"] = info["name"] if info["name"] else res["user_name"]
            await pcr_sqla.insert_bind(info)
            reply = '添加成功！已为您开启群聊推送！'
    except:
        logger.error(traceback.format_exc())
        reply = f'找不到这个uid，大概率是你输错了！'
    await bot.send_group_msg(self_id=ev.self_id, group_id=int(ev.group_id), message=reply)


async def sendNotice(new: int, old: int, info: PCRBind, noticeType: int):
    global timeStamp, jjc_log
    if noticeType == NoticeType.online.value:
        change = '上线了！'
    else:
        if noticeType == NoticeType.jjc.value:
            change = '\njjc: '
        else:
            change = '\npjjc: '
        if new < old:
            change += f'''{old}->{new} [▲{old-new}]'''
        else:
            change += f'''{old}->{new} [▽{new-old}]'''
# -----------------------------------------------------------------
    msg = ''
    onlineNotice = False
    is_send = False
    if info.online_notice and noticeType == NoticeType.online.value:
        if (new-old) < (60 if info.online_notice == 3 else 60 * 10):
            cache[(info.pcrid, info.user_id, info.platform)][2] = old  # 间隔太短，不更新缓存
        # 类型1，只在特定时间播报
        elif info.online_notice != 1 or ((new % 86400//3600+8) % 24 == 14 and new % 3600 // 60 >= 30):
            onlineNotice = True

    if (((noticeType == NoticeType.jjc.value and info.jjc_notice) or
         (noticeType == NoticeType.pjjc.value and info.pjjc_notice)) and
            (info.up_notice or (new > old))) or (noticeType == NoticeType.online.value and onlineNotice):
        logger.info(f'Send Notice FOR {info.user_id}({info.pcrid})')
        msg = info.name + change
        is_send = True
        if info.private:
            await private_send(int(info.user_id), msg)
        else:
            await group_send(info.group, msg + f'[CQ:at,qq={info.user_id}]')
    if (noticeType != NoticeType.online.value) or is_send: #上线提醒没报的没必要记录
        jjc_log[info.platform].append(JJCHistory(user_id=info.user_id,
                                                pcrid=info.pcrid,
                                                name=info.name,
                                                platform=info.platform,
                                                date=timeStamp,
                                                before=old,
                                                after=new,
                                                is_send=is_send,
                                                item=noticeType
                                                ))
