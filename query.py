import traceback
import asyncio
from typing import List, Union
from httpx import HTTPError
from json import loads, dumps, JSONDecodeError
from nonebot import logger
import httpx
from .client.tw_pcrclient import pcrclient as tw_pcrclient
from .client.pcrclient import pcrclient, bsdkclient, ApiException
from .database.dal import PCRBind, pcr_sqla, Account
from .var import BaseSet, Platform, Priority, platform_dict, queue_dict

class MatchError(Exception):
    pass

async def _query(client: Union[tw_pcrclient, pcrclient],  platform_id: int):
    if platform_id == 0:
        viewer_id : str = client.bsdk.account
    else:
        viewer_id: str = client.viewer_id
    queue: asyncio.PriorityQueue = queue_dict[platform_id]
    while True:
        try:
            DA = await queue.get()
            queue.task_done()
            data = DA[2]
            callback, info, result_storage = data
            uid = int(info.pcrid)
            res = await client.callapi('/profile/get_profile', {'target_viewer_id': uid})
            if 'user_info' not in res:
                await client.login()  # 失败重连
                res = await client.callapi('/profile/get_profile', {'target_viewer_id': uid})
            elif res["user_info"]["viewer_id"] != uid:
                raise MatchError
            result_storage["res"] = res
            result_storage["uid"] = uid
            result_storage["bind_info"] = info
            await callback(result_storage)
        except ApiException as e:
            if str(e) == "服务器在维护":
                await asyncio.sleep(e.code)
            else:
                logger.info(f"{viewer_id}查询{uid}失败")
                logger.info(traceback.format_exc())
        except (HTTPError, MatchError):
            logger.info(f"重试：{viewer_id} 对于 {uid} 的查询请求超时或不匹配。")
            try:
                await queue.put(DA)
            except:
                logger.info(f"失败：{viewer_id} 对于 {uid} 重试失败")
                logger.info(traceback.format_exc())
        except:
            logger.info(f"失败：{viewer_id} 未能完成查询请求。")
            logger.info(traceback.format_exc())


async def query1(query_list: List[PCRBind], platform, function, result_storage: dict = {}, priority: int = Priority.query_all.value):
    queue : asyncio.PriorityQueue = queue_dict[platform]
    if platform == Platform.tw_id.value:
        temp1 = []
        temp2 = []
        for query in query_list:
            if query.pcrid // 1000000000 == 1:
                temp1.append(query)
            else:
                temp2.append(query)
        if queue:
            if priority == Priority.query_all.value:
                await queue.join()
            await asyncio.gather(*map(lambda info: queue.put((priority, (info.pcrid, info.user_id, info.platform), (function, info, result_storage))), [i for i in temp1]))
        if not queue and temp1:
            logger.warn(f"未绑定台一服务器的查询账户，但有贱民查，已自动忽略")
        queue2 : asyncio.PriorityQueue = queue_dict[Platform.tw_other_id.value]
        if queue2:
            if priority == Priority.query_all.value:
                await queue2.join()
            await asyncio.gather(*map(lambda info: queue2.put((priority, (info.pcrid, info.user_id, info.platform), (function, info, result_storage))), [i for i in temp2]))
        if not queue2 and temp2:
            logger.warn(f"未绑定台其他服务器的查询账户，但有贱民查，已自动忽略")
        return
    if not queue:
        logger.warn(f"未绑定{platform_dict.get(platform, 'B服')}服务器的查询账户，但有贱民查，已自动忽略")
        return
    if priority == Priority.query_all.value:
        await queue.join()
    await asyncio.gather(*map(lambda info: queue.put((priority, (info.pcrid, info.user_id, info.platform), (function, info, result_storage))), [i for i in query_list]))


async def query2(query_list: List[PCRBind], platform: int, function, result_storage: dict ={}, priority:int=Priority.query_all.value):
    data = dumps([i.pcrid for i in query_list])
    async with httpx.AsyncClient() as client:
        async with client.stream("POST", f"https://神秘api/batch?priority={priority}", data=data, headers={"Content-Type": "application/json"}, timeout=None) as response:
            async for chunk in response.aiter_bytes():
                try:
                    result = loads(chunk.decode()[6:])
                    code = result["code"]
                    if code == 0:
                        result_storage["uid"] = result["data"]['viewer_id']
                        result_storage["res"] = {"user_info": result["data"]}
                        result_storage["bind_info"] = query_list[result["data"]['viewer_id']["id"]]
                        await function(result_storage)
                    elif code == 503:
                        sleep_time = response.headers["retry-after"]
                        return sleep_time
                    else:
                        logger.info(f"服务器异常{result['code']}")
                except JSONDecodeError:
                    pass
                except:
                    logger.info(traceback.format_exc())
                    logger.info(f"竞技场查询失败")

query_all = query2 if BaseSet.mode.value else query1

async def login_all():
    acinfo: List[Account] = await pcr_sqla.select_account()
    loop = asyncio.get_event_loop()
    for i in acinfo:
        if i.platform == Platform.tw_id.value:
            tw_platform = int(i.viewer_id)//1000000000
            client = tw_pcrclient(i.account, i.password, i.viewer_id, tw_platform)
            if tw_platform != 1:
                if not queue_dict[3]:
                    queue_dict[3] = asyncio.PriorityQueue()
                loop.create_task(_query(client, 3))
            else:
                if not queue_dict[2]:
                    queue_dict[2] = asyncio.PriorityQueue()
                loop.create_task(_query(client, 2))
        else:
            client = pcrclient(bsdkclient(i.account, i.password, i.platform))
        
        """
        try:
            await client.login()
        except:
            logger.warn(f"ID{int(i.viewer_id) or i.account}, 服务器：{platform_dict.get(i.platform, 'B服')}加载失败，后续会尝试自动重连")
        """
        
        if i.platform != Platform.tw_id.value:
            if not queue_dict[i.platform]:
                queue_dict[i.platform] = asyncio.PriorityQueue()
            loop.create_task(_query(client, i.platform))

        logger.info(f"加载账号：ID{int(i.viewer_id) or i.account}, 服务器：{platform_dict.get(i.platform, 'B服')}")
    
