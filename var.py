from enum import Enum
from asyncio import Lock
from pydantic import BaseModel

class Platform(Enum):
    """
    各个平台id，仅储存
    与游戏登录那块无关
    """
    b_id = 0
    qu_id = 1
    tw_id = 2
    tw_other_id = 3

class NoticeType(Enum):
    """
    通知类型id
    """
    jjc = 0
    pjjc = 1
    online = 2

class Priority(Enum):
    """
    优先级，越大优先度越低
    """
    query_all = 10
    detial_query = 2
    query_user = 3
    bind = 4


class BaseSet(Enum):
    """
    max_pri：最大私聊人数
    mode：0为本地查询，1为api查询
    """
    b_max_pri = 0
    qu_max_pri = 0
    tw_max_pri = 0  
    mode = 0

class LoadBase(BaseModel):
    b_group_user: int
    qu_group_user: int
    tw_group_user: int
    b_group_pcrid: int
    qu_group_pcrid: int
    tw_group_pcrid: int
    b_private_user: int
    qu_private_user: int
    tw_private_user: int
    b_private_pcrid: int
    qu_private_pcrid: int
    tw_private_pcrid: int
    b_today_send:int
    qu_today_send: int
    tw_today_send: int
    b_yesterday_send:int
    qu_yesterday_send: int
    tw_yesterday_send: int

queue_dict = {
    Platform.b_id.value: False,
    Platform.qu_id.value: False,
    Platform.tw_id.value: False,
    Platform.tw_other_id.value: False,
}

private_dict = {
    Platform.b_id.value: BaseSet.b_max_pri.value,
    Platform.qu_id.value: BaseSet.qu_max_pri.value,
    Platform.tw_id.value: BaseSet.tw_max_pri.value,
}

platform_dict = {
    Platform.qu_id.value: "渠",
    Platform.tw_id.value: "台",
    "渠": Platform.qu_id.value,
    "台": Platform.tw_id.value
}

platform_tw = {
    1: "美食殿堂",
    2: "真步真步王国",
    3: "破晓之星",
    4: "小小甜心"
}

cache = {}
lck = Lock()
query_cache = {}
jjc_log = {Platform.b_id.value: [],
           Platform.qu_id.value: [],
           Platform.tw_id.value: []}



