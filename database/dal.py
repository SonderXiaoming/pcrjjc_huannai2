import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple
from sqlmodel import SQLModel
from sqlalchemy.future import select
from sqlalchemy import case, delete, desc, distinct, insert, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.expression import func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from .models import Account, PCRBind, JJCHistory
from pathlib import Path
from ..var import LoadBase, Platform

DB_PATH = str(Path(__file__).parent / 'PCRJJC.db')


def pcr_date(timeStamp: int) -> datetime:
    now = datetime.fromtimestamp(
        timeStamp, tz=timezone(timedelta(hours=8)))
    if now.hour < 5:
        now -= timedelta(days=1)
    return now.replace(hour=5, minute=0, second=0, microsecond=0)  # 用5点做基准


class SQLA:
    def __init__(self, url: str):
        self.url = f'sqlite+aiosqlite:///{url}'
        self.engine = create_async_engine(self.url, pool_recycle=1500)
        self.async_session = sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    def create_all(self):
        try:
            asyncio.create_task(self._create_all())
        except RuntimeError:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self._create_all())
            loop.close()

    async def _create_all(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    # 账号部分
    async def select_account(self) -> List[Account]:
        async with self.async_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(Account)
                )
                data = result.scalars().all()
                return data if data else []

    async def insert_account(self, account_list: List[dict]) -> int:
        async with self.async_session() as session:
            async with session.begin():
                for account in account_list:
                    await session.merge(Account(**account))
                return 1

    async def delete_all_account(self) -> int:
        async with self.async_session() as session:
            async with session.begin():
                await session.execute(delete(Account))
                return 1

    # 绑定
    async def get_bind(self, platform: Optional[int] = -1, user_id: Optional[int] = None, group: Optional[int] = None) -> List[PCRBind]:
        async with self.async_session() as session:
            async with session.begin():
                sql = select(PCRBind)
                if platform != -1:
                    sql = sql.filter(PCRBind.platform == platform)
                if user_id:
                    sql = sql.filter(PCRBind.user_id ==
                                     user_id).order_by(PCRBind.id)
                if group:
                    sql = sql.filter(PCRBind.group == group).filter(
                        PCRBind.private == True)
                result = await session.execute(sql)
                data = result.scalars().all()
                return data if data else []

    async def get_private(self, platform: int) -> List[PCRBind]:
        async with self.async_session() as session:
            async with session.begin():
                result = await session.execute(select(func.count().filter(PCRBind.private == True)).where(PCRBind.platform == platform))
                return result.fetchone()

    async def insert_bind(self, bind: dict) -> int:
        async with self.async_session() as session:
            async with session.begin():
                await session.execute(insert(PCRBind).values(**bind))
                return 1

    async def delete_bind(self, user_id: int, platform: Optional[int], pcrid: Optional[PCRBind] = None, group: Optional[int] = None) -> int:
        async with self.async_session() as session:
            async with session.begin():
                sql = delete(PCRBind).where(PCRBind.user_id == user_id)
                if platform:
                    sql = sql.filter(PCRBind.platform == platform)
                if pcrid:
                    sql = sql.filter(PCRBind.pcrid == pcrid)
                if group:
                    sql = sql.filter(PCRBind.group == group).filter(
                        PCRBind.private == True)
                await session.execute(sql)
                return 1

    async def update_bind(self, platform: int, data: dict, user_id: Optional[int] = None, pcrid: Optional[PCRBind] = None) -> int:
        async with self.async_session() as session:
            async with session.begin():
                sql = update(PCRBind).where(PCRBind.platform == platform)
                if user_id:
                    sql = sql.filter(PCRBind.user_id == user_id)
                if pcrid:
                    sql = sql.filter(PCRBind.pcrid == pcrid)
                sql = sql.values(**data)
                await session.execute(sql)
                return 1

    # 竞技场记录
    async def get_up_num(self, platform: int, pcrid: int, date: int) -> Tuple[int]:
        pcr_time: float = pcr_date(date).timestamp()
        async with self.async_session() as session:
            async with session.begin():
                sql = select(func.count().filter(JJCHistory.item == 0),
                             func.count().filter(JJCHistory.item == 1)).where(
                    JJCHistory.pcrid == pcrid,
                    pcr_time + 3600 * 24 > JJCHistory.date,
                    pcr_time < JJCHistory.date,
                    JJCHistory.platform == platform,
                    JJCHistory.before > JJCHistory.after)
                result = await session.execute(sql)
                return result.fetchone()

    async def get_history(self, platform: int, user_id: Optional[int] = 0, pcrid: Optional[int] = 0) -> List[JJCHistory]:
        async with self.async_session() as session:
            async with session.begin():
                sql = select(JJCHistory).where(
                    JJCHistory.platform == platform, JJCHistory.item != 2)
                if user_id:
                    sql = sql.filter(JJCHistory.user_id == user_id)
                if pcrid:
                    sql = sql.filter(JJCHistory.pcrid == pcrid)
                sql = sql.order_by(desc(JJCHistory.date)).limit(50)
                result = await session.execute(sql)
                data = result.scalars().all()
                return data if data else []

    async def insert_history(self, historys: List[JJCHistory]) -> int:
        if not historys:
            return
        async with self.async_session() as session:
            async with session.begin():
                session.add_all(historys)
                return 1

    async def query_load(self) -> LoadBase:
        pcr_time: float = pcr_date(int(datetime.now().timestamp())).timestamp()
        async with self.async_session() as session:
            async with session.begin():
                sql = select(func.count().filter(JJCHistory.platform == Platform.b_id.value)
                             .filter(pcr_time + 3600 * 24 > JJCHistory.date).filter(pcr_time < JJCHistory.date),
                             func.count().filter(JJCHistory.platform == Platform.qu_id.value)
                             .filter(pcr_time + 3600 * 24 > JJCHistory.date).filter(pcr_time < JJCHistory.date),
                             func.count().filter(JJCHistory.platform == Platform.tw_id.value)
                             .filter(pcr_time + 3600 * 24 > JJCHistory.date).filter(pcr_time < JJCHistory.date),
                             func.count().filter(JJCHistory.platform == Platform.b_id.value)
                             .filter(pcr_time - 3600 * 24 < JJCHistory.date).filter(pcr_time > JJCHistory.date),
                             func.count().filter(JJCHistory.platform == Platform.qu_id.value)
                             .filter(pcr_time - 3600 * 24 < JJCHistory.date).filter(pcr_time > JJCHistory.date),
                             func.count().filter(JJCHistory.platform == Platform.tw_id.value)
                             .filter(pcr_time - 3600 * 24 < JJCHistory.date).filter(pcr_time > JJCHistory.date)).where(JJCHistory.is_send == True)
                result = await session.execute(sql)
                send = result.fetchone()
                sql = select(
                    func.count(distinct(PCRBind.user_id)).filter(
                        PCRBind.platform == Platform.b_id.value).filter(PCRBind.private == False),
                    func.count(distinct(PCRBind.pcrid)).filter(
                        PCRBind.platform == Platform.b_id.value).filter(PCRBind.private == False),
                    func.count(distinct(PCRBind.user_id)).filter(
                        PCRBind.platform == Platform.b_id.value).filter(PCRBind.private == True),
                    func.count(distinct(PCRBind.pcrid)).filter(
                        PCRBind.platform == Platform.b_id.value).filter(PCRBind.private == True),
                    func.count(distinct(PCRBind.user_id)).filter(
                        PCRBind.platform == Platform.qu_id.value).filter(PCRBind.private == False),
                    func.count(distinct(PCRBind.pcrid)).filter(
                        PCRBind.platform == Platform.qu_id.value).filter(PCRBind.private == False),
                    func.count(distinct(PCRBind.user_id)).filter(
                        PCRBind.platform == Platform.qu_id.value).filter(PCRBind.private == True),
                    func.count(distinct(PCRBind.pcrid)).filter(
                        PCRBind.platform == Platform.qu_id.value).filter(PCRBind.private == True),
                    func.count(distinct(PCRBind.user_id)).filter(
                        PCRBind.platform == Platform.tw_id.value).filter(PCRBind.private == False),
                    func.count(distinct(PCRBind.pcrid)).filter(
                        PCRBind.platform == Platform.tw_id.value).filter(PCRBind.private == False),
                    func.count(distinct(PCRBind.user_id)).filter(
                        PCRBind.platform == Platform.tw_id.value).filter(PCRBind.private == True),
                    func.count(distinct(PCRBind.pcrid)).filter(
                        PCRBind.platform == Platform.tw_id.value).filter(PCRBind.private == True),
                )
                result = await session.execute(sql)
                bind_num = result.fetchone()
                return LoadBase(b_today_send=send[0], qu_today_send=send[1], tw_today_send=send[2],
                                b_yesterday_send=send[3], qu_yesterday_send=send[4], tw_yesterday_send=send[5],
                                b_group_user=bind_num[0], b_group_pcrid=bind_num[1], b_private_user=bind_num[2],
                                b_private_pcrid=bind_num[3], qu_group_user=bind_num[4], qu_group_pcrid=bind_num[5],
                                qu_private_user=bind_num[6], qu_private_pcrid=bind_num[7], tw_group_user=bind_num[8],
                                tw_group_pcrid=bind_num[9], tw_private_user=bind_num[10], tw_private_pcrid=bind_num[11]
                                )


pcr_sqla = SQLA(DB_PATH)
