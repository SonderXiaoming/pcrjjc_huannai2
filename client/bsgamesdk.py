import asyncio
import json
import time
import hashlib
from . import rsacr
import urllib
from nonebot import logger
import httpx
from json import load
from os.path import join, dirname
from ...multicq_send import group_send, private_send
import hoshino


bililogin = "https://line1-sdk-center-login-sh.biligame.net/"
header = {"User-Agent": "Mozilla/5.0 BSGameSDK", "Content-Type": "application/x-www-form-urlencoded",
          "Host": "line1-sdk-center-login-sh.biligame.net"}
captcha_header = {"Content-Type": "application/json",
                  "User-Agent": "pcrjjc2/1.0.0"}

# 手动过码时限（秒）
gt_wait = 90

# 手动过码网站地址
manual_captch_site = "https://yousite.com"


async def sendpost(url, data):
    async with httpx.AsyncClient() as client:
        return (await client.post(url=url, data=data, headers=header, timeout=20)).json()

async def captchaVerifier(gt, challenge, userid):
    async with httpx.AsyncClient(timeout=30) as AsyncClient:
        try:
            res = await AsyncClient.get(url=f"https://pcrd.tencentbot.top/geetest_renew?captcha_type=1&challenge={challenge}&gt={gt}&userid={userid}&gs=1", headers=captcha_header)
            res = res.json()
            uuid = res["uuid"]
            ccnt = 0
            while (ccnt := ccnt + 1) < 10:
                res = await AsyncClient.get(url=f"https://pcrd.tencentbot.top/check/{uuid}", headers=captcha_header)
                res = res.json()

                if "queue_num" in res:
                    tim = min(int(res['queue_num']), 3) * 10
                    logger.info(f"过码排队，当前有{res['queue_num']}个在前面，等待{tim}s")
                    await asyncio.sleep(tim)
                    continue

                info = res["info"]
                if 'validate' in info:
                    return info["challenge"], info["gt_user_id"], info["validate"]

                if res["info"] in ["fail", "url invalid"]:
                    raise Exception(f"自动过码失败")

                if res["info"] == "in running":
                    logger.info(f"正在过码。等待5s")
                    await asyncio.sleep(5)

            raise Exception(f"自动过码多次失败")

        except Exception as e:
            raise Exception(f"自动过码异常，{e}")


async def captchaVerifier2(*args):
    """
    token的自动过码
    """
    with open(join(join(dirname(__file__), 'api.json'), )) as fp:
        api: dict = load(fp)
    gt = args[0]
    challenge = args[1]
    try:
        async with httpx.AsyncClient() as AsyncClient:
            res = await AsyncClient.get(url=f"{api['api']}&gt={gt}&challenge={challenge}", timeout=30)
            res = json.loads(res.content)
            if res.get("code", -1) != 0:
                raise Exception(f'{res}')
            return challenge, args[2], res["data"]["validate"]
    except Exception as e:
        raise Exception(f"自动过码异常，{e}")


def setsign(data):
    data["timestamp"] = int(time.time())
    data["client_timestamp"] = int(time.time())
    sign = ""
    data2 = ""
    for key in data:
        if key == "pwd":
            pwd = urllib.parse.quote(data["pwd"])
            data2 += f"{key}={pwd}&"
        data2 += f"{key}={data[key]}&"
    for key in sorted(data):
        sign += f"{data[key]}"
    data = sign
    sign = sign + "fe8aac4e02f845b8ad67c427d48bfaf1"
    sign = hashlib.md5(sign.encode()).hexdigest()
    data2 += "sign=" + sign
    return data2


modolrsa = '{"operators":"5","merchant_id":"1","isRoot":"0","domain_switch_count":"0","sdk_type":"1","sdk_log_type":"1","timestamp":"1613035485639","support_abis":"x86,armeabi-v7a,armeabi","access_key":"","sdk_ver":"3.4.2","oaid":"","dp":"1280*720","original_domain":"","imei":"227656364311444","version":"1","udid":"KREhESMUIhUjFnJKNko2TDQFYlZkB3cdeQ==","apk_sign":"e89b158e4bcf988ebd09eb83f5378e87","platform_type":"3","old_buvid":"XZA2FA4AC240F665E2F27F603ABF98C615C29","android_id":"84567e2dda72d1d4","fingerprint":"","mac":"08:00:27:53:DD:12","server_id":"1592","domain":"line1-sdk-center-login-sh.biligame.net","app_id":"1370","version_code":"90","net":"4","pf_ver":"6.0.1","cur_buvid":"XZA2FA4AC240F665E2F27F603ABF98C615C29","c":"1","brand":"Android","client_timestamp":"1613035486888","channel_id":"1","uid":"","game_id":"1370","ver":"2.4.10","model":"MuMu"}'
modollogin = '{"operators":"5","merchant_id":"1","isRoot":"0","domain_switch_count":"0","sdk_type":"1","sdk_log_type":"1","timestamp":"1613035508188","support_abis":"x86,armeabi-v7a,armeabi","access_key":"","sdk_ver":"3.4.2","oaid":"","dp":"1280*720","original_domain":"","imei":"227656364311444","gt_user_id":"fac83ce4326d47e1ac277a4d552bd2af","seccode":"","version":"1","udid":"KREhESMUIhUjFnJKNko2TDQFYlZkB3cdeQ==","apk_sign":"e89b158e4bcf988ebd09eb83f5378e87","platform_type":"3","old_buvid":"XZA2FA4AC240F665E2F27F603ABF98C615C29","android_id":"84567e2dda72d1d4","fingerprint":"","validate":"84ec07cff0d9c30acb9fe46b8745e8df","mac":"08:00:27:53:DD:12","server_id":"1592","domain":"line1-sdk-center-login-sh.biligame.net","app_id":"1370","pwd":"rxwA8J+GcVdqa3qlvXFppusRg4Ss83tH6HqxcciVsTdwxSpsoz2WuAFFGgQKWM1+GtFovrLkpeMieEwOmQdzvDiLTtHeQNBOiqHDfJEKtLj7h1nvKZ1Op6vOgs6hxM6fPqFGQC2ncbAR5NNkESpSWeYTO4IT58ZIJcC0DdWQqh4=","version_code":"90","net":"4","pf_ver":"6.0.1","cur_buvid":"XZA2FA4AC240F665E2F27F603ABF98C615C29","c":"1","brand":"Android","client_timestamp":"1613035509437","channel_id":"1","uid":"","captcha_type":"1","game_id":"1370","challenge":"efc825eaaef2405c954a91ad9faf29a2","user_id":"doo349","ver":"2.4.10","model":"MuMu"}'
modolcaptch = '{"operators":"5","merchant_id":"1","isRoot":"0","domain_switch_count":"0","sdk_type":"1","sdk_log_type":"1","timestamp":"1613035486182","support_abis":"x86,armeabi-v7a,armeabi","access_key":"","sdk_ver":"3.4.2","oaid":"","dp":"1280*720","original_domain":"","imei":"227656364311444","version":"1","udid":"KREhESMUIhUjFnJKNko2TDQFYlZkB3cdeQ==","apk_sign":"e89b158e4bcf988ebd09eb83f5378e87","platform_type":"3","old_buvid":"XZA2FA4AC240F665E2F27F603ABF98C615C29","android_id":"84567e2dda72d1d4","fingerprint":"","mac":"08:00:27:53:DD:12","server_id":"1592","domain":"line1-sdk-center-login-sh.biligame.net","app_id":"1370","version_code":"90","net":"4","pf_ver":"6.0.1","cur_buvid":"XZA2FA4AC240F665E2F27F603ABF98C615C29","c":"1","brand":"Android","client_timestamp":"1613035487431","channel_id":"1","uid":"","game_id":"1370","ver":"2.4.10","model":"MuMu"}'


async def _login(account, password, challenge="", gt_user="", validate=""):
    rsa = await sendpost(bililogin + "api/client/rsa", setsign(json.loads(modolrsa)))
    data = json.loads(modollogin)
    public_key = rsa['rsa_key']
    data["access_key"] = ""
    data["gt_user_id"] = gt_user
    data["uid"] = ""
    data["challenge"] = challenge
    data["user_id"] = account
    data["validate"] = validate
    if validate:
        data["seccode"] = validate + "|jordan"
    data["pwd"] = rsacr.rsacreate(rsa['hash'] + password, public_key)
    return await sendpost(bililogin + "api/client/login", setsign(data))


async def login(bili_account, bili_pwd):
    logger.info(f'logging in with acc={bili_account}, pwd = {bili_pwd}')
    login_sta = await _login(bili_account, bili_pwd)
    if login_sta.get("message", "") == "用户名或密码错误":
        raise Exception("用户名或密码错误")
    if login_sta['code'] == 200000:  # secondary verify
        cap = await sendpost(bililogin+"api/client/start_captcha", setsign(json.loads(modolcaptch)))
        # 尝试自动过码
        try:
            challenge, gt_user_id, captch_done = await captchaVerifier(cap['gt'], cap['challenge'], cap['gt_user_id'])
        except Exception as e:
            logger.error(f'自动过码失败: {e}，尝试手动过码')
            # 尝试手动过码
            try:
                qqid = hoshino.config.SUPERUSERS[0]
                challenge, gt_user_id, captch_done = await manual_captch(cap['challenge'], cap['gt'], cap['gt_user_id'], qqid, bili_account)
            except Exception as e:
                raise Exception(f'手动过码失败: {e}')      
        login_sta = await _login(bili_account, bili_pwd, challenge, gt_user_id, captch_done)
        if login_sta.get("message", "") == "用户名或密码错误":
            raise Exception("用户名或密码错误")
        return login_sta
    else:
        return login_sta
class bsdkclient:

    def __init__(self, account: str, password: str, platform: int):
        self.account = account
        self.password = password
        self.qudao = platform
        if self.qudao == 0:
            self.platform = "2"
        else:
            self.platform = "4"

    async def b_login(self):
        if self.qudao == 0:
            for i in range(3):
                resp = await login(self.account, self.password)
                if resp['code'] == 0:
                    logger.info("geetest or captcha succeed")
                    return resp['uid'], resp['access_key']
        elif self.qudao == 1:
            return self.account, self.password

async def manual_captch_listener(user_id:str):
    while True:
        async with httpx.AsyncClient() as client:
            url = f'{manual_captch_site}/api/block?userid={user_id}'
            try:
                response = await client.get(url, timeout=28)
            except httpx.TimeoutException as e:
                pass
            else:
                if response.status_code == 200:
                    res = response.json()
                    return res["validate"]

async def manual_captch(challenge:str, gt:str, user_id:str, qqid:int, bili_account):
    url = f"{manual_captch_site}/?captcha_type=1&challenge={challenge}&gt={gt}&userid={user_id}&gs=1"
    await private_send(qqid, f'pcr账号{bili_account}登录触发验证码，请在{gt_wait}秒内完成以下链接中的验证内容。')
    await private_send(qqid, url)
    
    try:
        return (challenge, user_id, await asyncio.wait_for(manual_captch_listener(user_id), gt_wait))
    except asyncio.TimeoutError:
        await private_send(qqid, "手动过码获取结果超时")
        raise RuntimeError("手动过码获取结果超时")
    except Exception as e:
        await private_send(qqid, f'手动过码获取结果异常：{e}')
        raise e
