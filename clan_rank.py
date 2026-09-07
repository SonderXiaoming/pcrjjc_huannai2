"""通过已登录的 PCR 官方客户端查询公会战排名。

仅使用游戏内公会搜索和详情接口 ``/clan/search_clan``、
``/clan/others_info``。不使用 BigFun、B站网页 Cookie、网页签名或
``/clan_battle/period_ranking`` 翻页。详细查询任意 UID 时，不能使用
登录账号的 ``my_clan_data`` 作为目标 UID 的排名。
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)
CACHE_TTL = 10 * 60
_cache: Dict[tuple, tuple[float, Optional[dict]]] = {}
_cache_lock = asyncio.Lock()


def _normalize(value: Any) -> str:
    """返回公会名原文，保留空格、大小写及其他有效字符。"""
    if value is None:
        return ""
    return str(value)


def _as_int(value: Any) -> Optional[int]:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value



async def _query_clan_info_rank(
    client: Any,
    clan_name: str,
    target_uid: Optional[int] = None,
) -> Optional[dict]:
    """轮询同名公会，在成员列表中确认目标 UID 后读取排名。"""
    target_uid = _as_int(target_uid)
    if target_uid is None:
        logger.warning("公会详情查询跳过: 缺少目标 UID")
        return None
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


async def query_clan_battle_rank(
    client: Any,
    clan_name: Any,
    platform: int,
    target_uid: Optional[int] = None,
) -> Optional[dict]:
    """按公会名称搜索候选，并通过成员 UID 确认目标公会。"""
    normalized = _normalize(clan_name)
    target_uid = _as_int(target_uid)
    if target_uid is None:
        logger.warning("公会排名查询跳过: 缺少目标 UID，禁止仅按公会名称返回排名")
        return None
    logger.info(
        "公会排名查询开始: clan=%r normalized=%r target_uid=%s platform=%s client=%s",
        clan_name,
        normalized,
        target_uid,
        platform,
        type(client).__name__ if client is not None else None,
    )
    if client is None or platform != 0 or not normalized:
        logger.warning(
            "公会排名查询跳过: client=%s platform=%s clan_valid=%s",
            client is not None,
            platform,
            bool(normalized),
        )
        return None

    cache_key = (id(client), normalized, platform, target_uid)
    async with _cache_lock:
        cached = _cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < CACHE_TTL:
            return cached[1]

    result = await _query_clan_info_rank(
        client,
        str(clan_name),
        target_uid=target_uid,
    )
    async with _cache_lock:
        _cache[cache_key] = (time.monotonic(), result)
    return result
