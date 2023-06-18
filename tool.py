from asyncio import get_event_loop
from json import load
from os.path import join, dirname
import glob
from .database.dal import pcr_sqla
from .client.playerpref import decryptxml
account_path = join(dirname(__file__), "account")
with open(join(account_path, 'account.json')) as fp:
    acinfo: list = load(fp)

xml_files = glob.glob(join(account_path, "*.xml"))
for xml_file in xml_files:
    tw_account = decryptxml(xml_file)

    acinfo.append({
            "viewer_id": tw_account['VIEWER_ID_lowBits'],
            "account": tw_account['UDID'],
            "password": tw_account['SHORT_UDID_lowBits'],
            "platform": 2
        })

async def refresh_account():
    await pcr_sqla._create_all()
    await pcr_sqla.delete_all_account()
    await pcr_sqla.insert_account(acinfo)
    print("done")

async def recover_binds():
    with open(join(account_path, 'bind1.json')) as fp:
        binds: list = load(fp)
        binds = binds["arena_bind"]
        for user in binds:
            player = binds[user]
            for i, pcrid in enumerate(player["pcrid"]):
                await pcr_sqla.insert_bind({"platform": 0,
                                                "pcrid": pcrid,
                                                "name": player["pcrName"][i],
                                                "group": player["gid"],
                                                "user_id": int(user),
                                                "jjc_notice": bool(player["noticeType"][i]//1000),
                                                "pjjc_notice": bool(player["noticeType"][i] % 1000//100),
                                                "up_notice": bool(player["noticeType"][i] % 100//10),
                                                "online_notice": player["noticeType"][i] % 10
                                                }
                                               )
    with open(join(account_path, 'bind2.json')) as fp:
        binds: list = load(fp)
        binds = binds["arena_bind"]
        for user in binds:
            player = binds[user]
            for i, pcrid in enumerate(player["pcrid"]):
                await pcr_sqla.insert_bind({"platform": 1,
                                                "pcrid": pcrid,
                                                "name": player["pcrName"][i],
                                                "group": player["gid"],
                                                "user_id": int(user),
                                                "jjc_notice": bool(player["noticeType"][i]//1000),
                                                "pjjc_notice": bool(player["noticeType"][i] % 1000//100),
                                                "up_notice": bool(player["noticeType"][i] % 100//10),
                                                "online_notice": player["noticeType"][i] % 10
                                                }
                                               )
async def ADD_COLUMN():
    async with pcr_sqla.async_session() as session:
        async with session.begin():
            await session.execute('ALTER TABLE JJCHistory ADD COLUMN is_send BOOLEAN DEFAULT 1')
            return 1
