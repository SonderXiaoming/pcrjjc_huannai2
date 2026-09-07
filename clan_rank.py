"""通过已登录的 PCR 官方客户端查询公会战排名。

优先使用游戏内公会搜索和详情接口 ``/clan/search_clan``、
``/clan/others_info``；必要时再使用 ``/clan_battle/period_ranking``。
不使用 BigFun、B站网页 Cookie 或网页签名。详细查询任意 UID 时，
不能使用登录账号的 ``my_clan_data`` 作为目标 UID 的排名。
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)
CACHE_TTL = 10 * 60
PAGE_SIZE = 10
MAX_RANK = 200
MAX_PAGES = MAX_RANK // PAGE_SIZE
# 官方 period_ranking 的 page 是 0-based：page=0 返回第 1-10 名。
FIRST_PAGE = 0
_cache: Dict[tuple, tuple[float, Optional[dict]]] = {}
_cache_lock = asyncio.Lock()


def _normalize(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split()).casefold().replace(" ", "")


def _as_int(value: Any) -> Optional[int]:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value


def _period_ranking(data: Any) -> list:
    if not isinstance(data, dict):
        return []
    ranking = data.get("period_ranking")
    return ranking if isinstance(ranking, list) else []


def _match_entry(entries: list, clan_name: str) -> Optional[dict]:
    wanted = _normalize(clan_name)
    if not wanted:
        return None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if _normalize(entry.get("clan_name")) != wanted:
            continue
        rank = _as_int(entry.get("rank"))
        if rank is None or rank <= 0:
            continue
        return {
            "rank": rank,
            "clan_name": entry.get("clan_name") or clan_name,
            "clan_battle_id": _as_int(entry.get("clan_battle_id")),
        }
    return None


def _battle_id(data: Any) -> Optional[int]:
    return _as_int(data.get("clan_battle_id")) if isinstance(data, dict) else None


async def _query_clan_info_rank(
    client: Any,
    clan_name: str,
    target_uid: Optional[int] = None,
) -> Optional[dict]:
    """轮询同名公会，在成员列表中确认目标 UID 后读取排名。"""
    try:
        search_data = await client.callapi(
            "/clan/search_clan",
            {
                "clan_name": clan_name,
                "join_condition": 0,
                "member_condition_range": 0,
                "activity": 0,
                "clan_battle_mode": 0,
            },
        )
    except Exception:
        logger.warning("按名称搜索公会失败: clan=%r", clan_name, exc_info=True)
        return None

    if not isinstance(search_data, dict):
        logger.warning("公会搜索返回不是字典: clan=%r type=%s", clan_name, type(search_data).__name__)
        return None
    candidates = search_data.get("list")
    if not isinstance(candidates, list):
        logger.warning("公会搜索返回没有 list: clan=%r keys=%s", clan_name, list(search_data.keys()))
        return None

    wanted = _normalize(clan_name)
    logger.info("公会名称搜索完成: clan=%r candidates=%s", clan_name, len(candidates))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_name = candidate.get("clan_name")
        clan_id = _as_int(candidate.get("clan_id"))
        if not clan_id or _normalize(candidate_name) != wanted:
            continue
        try:
            detail_data = await client.callapi(
                "/clan/others_info",
                {"clan_id": clan_id},
            )
        except Exception:
            logger.warning("读取公会详情失败: clan=%r clan_id=%s", clan_name, clan_id, exc_info=True)
            continue
        if not isinstance(detail_data, dict):
            continue
        clan = detail_data.get("clan")
        detail = clan.get("detail") if isinstance(clan, dict) else None
        members = clan.get("members") if isinstance(clan, dict) else None
        if not isinstance(detail, dict):
            continue
        detail_name = detail.get("clan_name") or candidate_name or clan_name
        if _normalize(detail_name) != wanted:
            continue
        if target_uid is not None:
            member_uids = {
                _as_int(member.get("viewer_id"))
                for member in members
                if isinstance(member, dict)
            } if isinstance(members, list) else set()
            if target_uid not in member_uids:
                logger.info(
                    "同名公会未找到目标 UID，继续轮询: clan=%r clan_id=%s members=%s",
                    clan_name,
                    clan_id,
                    len(member_uids),
                )
                continue
        rank = _as_int(detail.get("current_period_ranking"))
        if rank is None or rank <= 0:
            rank = _as_int(detail.get("grade_rank"))
        logger.info(
            "公会详情排名结果: clan=%r clan_id=%s current_period_ranking=%r grade_rank=%r",
            clan_name,
            clan_id,
            detail.get("current_period_ranking"),
            detail.get("grade_rank"),
        )
        if rank is not None and rank > 0:
            return {
                "rank": rank,
                "clan_name": detail_name,
                "clan_id": clan_id,
                "source": "clan/others_info",
                "history": 0,
            }
    logger.info("公会详情中没有有效当前排名: clan=%r", clan_name)
    return None


async def _call_period_ranking(
    client: Any,
    battle_id: Optional[int],
    page: int,
    is_first: int = 0,
    retry_login: bool = True,
) -> Optional[dict]:
    """调用官方总榜接口；page 从 0 开始，首个请求标记 is_first。"""
    # 这些字段来自官方 ClanBattlePeriodRankingRequest 模型。游戏客户端
    # 会把可选整数以 0 一并发送；只发送 page 会得到业务错误 status=3。
    # 明确关闭 is_my_clan，避免服务端只返回登录账号自己的公会。
    clan_id = getattr(client, "clan_id", None)
    if not clan_id and hasattr(client, "refresh_clan_id"):
        try:
            await client.refresh_clan_id()
        except Exception:
            logger.warning("刷新登录账号公会信息失败", exc_info=True)
        clan_id = getattr(client, "clan_id", None)
    if not clan_id:
        logger.warning(
            "公会战总榜请求跳过: 登录账号未加入公会，无法满足官方接口的 clan_id 要求"
        )
        return None

    request = {
        "clan_id": clan_id,
        "clan_battle_id": battle_id or 0,
        "period": 0,
        "month": 0,
        "page": page,
        "is_my_clan": 0,
        "is_first": is_first,
    }
    logger.info(
        "公会战总榜请求开始: battle_id=%s page=%s is_first=%s request=%r",
        battle_id,
        page,
        is_first,
        request,
    )
    try:
        data = await client.callapi("/clan_battle/period_ranking", request)
        if not isinstance(data, dict):
            logger.warning("公会战总榜返回不是字典: battle_id=%s page=%s type=%s", battle_id, page, type(data).__name__)
            return None
        entries = _period_ranking(data)
        error = data.get("server_error")
        if error is not None:
            logger.warning(
                "公会战总榜服务器拒绝请求: battle_id=%s page=%s error=%r",
                battle_id,
                page,
                error,
            )
            # status=3 是官方协议中的会话失效。刷新一次登录后重试，
            # 避免把会话过期误判为公会没有排名。
            if retry_login and isinstance(error, dict) and error.get("status") == 3:
                logger.info("公会战总榜会话可能已失效，刷新登录后重试: page=%s", page)
                try:
                    await client.login()
                except Exception:
                    logger.warning("刷新公会战查询登录会话失败", exc_info=True)
                    return None
                return await _call_period_ranking(
                    client,
                    battle_id,
                    page,
                    is_first=is_first,
                    retry_login=False,
                )
            return None
        logger.info(
            "公会战总榜请求完成: requested_battle_id=%s page=%s returned_battle_id=%s keys=%s entries=%s ranks=%s",
            battle_id,
            page,
            data.get("clan_battle_id"),
            list(data.keys()),
            len(entries),
            [item.get("rank") for item in entries[:3] if isinstance(item, dict)],
        )
        return data
    except Exception:
        logger.warning(
            "官方公会战总榜接口调用失败: battle_id=%s page=%s",
            battle_id,
            page,
            exc_info=True,
        )
        return None


async def _find_in_period(client: Any, clan_name: str, battle_id: Optional[int], start_page: int = FIRST_PAGE) -> Optional[dict]:
    """遍历一个会战期次的总榜，按公会名寻找目标公会。"""
    for page in range(start_page, MAX_PAGES):
        data = await _call_period_ranking(client, battle_id, page)
        if data is None:
            return None
        entries = _period_ranking(data)
        if not entries:
            return None
        result = _match_entry(entries, clan_name)
        if result is not None:
            result["clan_battle_id"] = _battle_id(data) or battle_id
            return result
        logger.info(
            "公会总榜本页未命中: clan=%r battle_id=%s page=%s rank_range=%s-%s",
            clan_name,
            battle_id,
            page,
            entries[0].get("rank") if isinstance(entries[0], dict) else None,
            entries[-1].get("rank") if isinstance(entries[-1], dict) else None,
        )
        # 返回不足一页时已经到达总榜末尾。
        if len(entries) < PAGE_SIZE:
            return None
    logger.info("前 %s 名内未找到公会，停止继续翻榜: battle_id=%s", MAX_RANK, battle_id)
    return {"rank": MAX_RANK + 1, "clan_name": clan_name, "rank_overflow": True, "clan_battle_id": battle_id}


async def query_clan_battle_rank(
    client: Any,
    clan_name: Any,
    platform: int,
    target_uid: Optional[int] = None,
) -> Optional[dict]:
    """从总排名表查询当前期排名，当前期无结果时回退上一期。

    这里不读取 ``my_clan_data.rank``，因为详细查询的 UID 可能不是登录
    client 对应的账号。总榜按页返回，必须逐页匹配目标公会名。
    """
    normalized = _normalize(clan_name)
    target_uid = _as_int(target_uid)
    logger.info(
        "公会排名查询开始: clan=%r normalized=%r target_uid=%s platform=%s client=%s",
        clan_name,
        normalized,
        target_uid,
        platform,
        type(client).__name__ if client is not None else None,
    )
    if client is None or platform != 0 or not normalized:
        logger.warning("公会排名查询跳过: client=%s platform=%s clan_valid=%s", client is not None, platform, bool(normalized))
        return None

    cache_key = (id(client), normalized, platform, target_uid)
    async with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < CACHE_TTL:
            return cached[1]

    # clan/others_info 是游戏内公会搜索使用的公开详情接口，不要求
    # 登录账号属于目标公会，也不读取登录账号的 my_clan_data.rank。
    # 它返回目标公会自己的 current_period_ranking，优先于总榜接口。
    result = await _query_clan_info_rank(client, str(clan_name), target_uid=target_uid)
    if result is not None:
        async with _cache_lock:
            _cache[cache_key] = (time.monotonic(), result)
        return result

    # 官方 period_ranking 接口仍要求请求者本身已加入公会；这里的
    # clan_id 只用于通过接口校验，目标 UID 的排名仍须从总榜匹配。
    if not getattr(client, "clan_id", None) and hasattr(client, "refresh_clan_id"):
        try:
            await client.refresh_clan_id()
        except Exception:
            logger.warning("刷新登录账号公会信息失败", exc_info=True)
    if not getattr(client, "clan_id", None):
        logger.warning("公会排名查询不可用: 搜索详情无当前排名，且登录账号未加入公会")
        result = {
            "unavailable": "登录账号未加入公会且公会详情暂无当前排名",
            "clan_name": clan_name,
        }
        async with _cache_lock:
            _cache[cache_key] = (time.monotonic(), result)
        return result
    result = None
    current = await _call_period_ranking(client, None, FIRST_PAGE, is_first=1)
    if current is not None:
        current_id = _battle_id(current)
        result = _match_entry(_period_ranking(current), str(clan_name))
        if result is not None:
            logger.info("公会排名当前第1页命中: clan=%r rank=%s battle_id=%s", clan_name, result.get("rank"), current_id)
            result["clan_battle_id"] = current_id
            result["history"] = 0
        else:
            # 已经请求过第 1 页，继续从第 2 页扫描当前期。
            result = await _find_in_period(client, str(clan_name), current_id, start_page=FIRST_PAGE + 1)
            if result is not None and not result.get("rank_overflow"):
                logger.info("公会排名当前期命中: clan=%r rank=%s battle_id=%s", clan_name, result.get("rank"), result.get("clan_battle_id"))
                result["history"] = 0
            elif current_id is not None and current_id > 1:
                logger.info("当前期总榜未命中，开始查询上一期: clan=%r battle_id=%s", clan_name, current_id - 1)
                result = await _find_in_period(
                    client,
                    str(clan_name),
                    current_id - 1,
                    start_page=FIRST_PAGE,
                )
                if result is not None and not result.get("rank_overflow"):
                    logger.info("公会排名上一期命中: clan=%r rank=%s battle_id=%s", clan_name, result.get("rank"), result.get("clan_battle_id"))
                    result["history"] = 1
                elif result is not None and result.get("rank_overflow"):
                    logger.info("本期和上一期前 %s 名均未找到公会", MAX_RANK)
                    result = {"rank_overflow": True, "clan_name": clan_name, "clan_battle_id": current_id - 1, "history": 1}
                else:
                    result = None

    async with _cache_lock:
        _cache[cache_key] = (time.monotonic(), result)
    return result
