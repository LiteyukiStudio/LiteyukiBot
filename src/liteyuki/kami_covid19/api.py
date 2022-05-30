import os

import aiohttp
import jieba
from PIL import Image
from nonebot.adapters.onebot.v11 import Message

from ..extraApi.base import ExConfig
from ..extraApi.cardimage import Cardimage


def match(kw1, kw2):
    if kw1 in kw2 or kw2 in kw1:
        return True
    else:
        return False


def signNumber(num):
    if num is None:
        return "-"
    if num > 0:
        return "+" + str(num)
    elif num <= 0:
        return str(num)


async def search_data(cityname) -> str:
    async with aiohttp.request("GET", url="https://c.m.163.com/ug/api/wuhan/app/data/list-total",
                               headers={
                                   'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36 QIHU 360SE'
                               }) as data:
        if data.status != 200:
            return "疫情数据查询失败:%s" % data.status
        else:
            data = await data.json()
            # 精准搜索
            for country in data["data"]["areaTree"]:
                if country["name"] == cityname:
                    country["wholeName"] = country["name"]
                    return await covid_data_format_to_message(country)
                else:
                    for province in country["children"]:
                        if province["name"] == cityname:
                            province["wholeName"] = country["name"] + " " + province["name"]
                            return await covid_data_format_to_message(province)
                        else:
                            for city in province["children"]:
                                if city["name"] == cityname:
                                    city["wholeName"] = country["name"] + " " + province["name"] + " " + city["name"]
                                    return await covid_data_format_to_message(city)
            else:
                # 模糊搜索没搜到就分词:
                print("分词")
                kw_list = jieba.lcut(cityname)
                for country in data["data"]["areaTree"]:
                    if match(country["name"], kw_list[0]):
                        for province in country["children"]:
                            if len(kw_list) >= 2 and match(province["name"], kw_list[1]):
                                for city in province["children"]:
                                    if len(kw_list) >= 3 and match(city["name"], kw_list[2]):
                                        city["wholeName"] = country["name"] + " " + province["name"] + " " + city[
                                            "name"]
                                        return await covid_data_format_to_message(city)
                                province["wholeName"] = country["name"] + " " + province["name"]
                                return await covid_data_format_to_message(province)
                        country["wholeName"] = country["name"]
                        return await covid_data_format_to_message(country)
                    else:
                        for province in country["children"]:
                            if match(province["name"], kw_list[0]):
                                for city in province["children"]:
                                    if len(kw_list) >= 2 and match(city["name"], kw_list[1]):
                                        city["wholeName"] = country["name"] + " " + province["name"] + " " + city[
                                            "name"]
                                        return await covid_data_format_to_message(city)
                                province["wholeName"] = country["name"] + " " + province["name"]
                                return await covid_data_format_to_message(province)
                            else:
                                for city in province["children"]:
                                    if match(city["name"], kw_list[0]):
                                        city["wholeName"] = country["name"] + " " + province["name"] + " " + city[
                                            "name"]
                                        return await covid_data_format_to_message(city)
        return "未查询到该地区/国家"


async def covid_data_format_to_message(data: dict):
    print(data)
    confirmNow = data["total"].get("confirm", 0) - data["total"].get("heal", 0) - data["total"].get("dead", 0)
    confirmNowAdd = signNumber(data["today"].get("storeConfirm", None))
    inputNow = data["total"].get("input", None)
    inputAdd = signNumber(data["today"].get("input", None))
    confirmTotal = data["total"].get("confirm", None)
    confirmTotalAdd = signNumber(data["today"].get("confirm", None))
    deadTotal = data["total"].get("dead", None)
    deadTotalAdd = signNumber(data["today"].get("dead", None))
    healTotal = data["total"].get("heal", None)
    healTotalAdd = signNumber(data["today"].get("heal", None))

    message = "%s疫情情况:\n" \
              "- 现有确诊: %s(%s)\n" \
              "- 境外输入: %s(%s)\n" \
              "- 累计确诊: %s(%s)\n" \
              "- 累计死亡: %s(%s%s%s)\n" \
              "- \n" \
              "更新时间\n%s\n数据来源于:网易新闻https://c.m.163.com/ug/api/wuhan/app/data/list-total" % (
                  data.get("wholeName", data.get("name", "未知地点")), confirmNow, confirmNowAdd, inputNow, inputAdd,
                  confirmTotal, confirmTotalAdd, deadTotal, deadTotalAdd, healTotal,
                  healTotalAdd, data["lastUpdateTime"])
    card = Cardimage(Image.open(os.path.join(ExConfig.res_path, "textures/covid19/bg.png")))
    await card.addImage(uvSize=(1, 1), boxSize=(0.2, 0.2), xyOffset=(0, 0), baseAnchor=(0.95, 0.05), imgAnchor=(1, 0),
                        img=Image.open(os.path.join(ExConfig.res_path, "textures/covid19/新冠疫情.png")))
    await card.addText(uvSize=(1, 1), boxSize=(0.7, 0.15), xyOffset=(0, 0), baseAnchor=(0.05, 0.05), textAnchor=(0, 0),
                       content=data.get("wholeName", data.get("name", "未知地点")), color=(255, 255, 255, 255))

    now_pos = await card.addText(uvSize=(1, 1), boxSize=(0.7, 0.1), xyOffset=(0, 0), baseAnchor=(0.05, 0.3),
                                 textAnchor=(0, 0), content="现有确诊: %s(%s)" % (confirmNow, confirmNowAdd),
                                 color=(255, 255, 255, 255))
    await card.addText(uvSize=(1, 1), boxSize=(0.7, 0.1), xyOffset=(0, 0), baseAnchor=(0.05, 0.4), textAnchor=(0, 0),
                       content="累计确诊: %s(%s)" % (confirmTotal, confirmTotalAdd), color=(255, 255, 255, 255))
    await card.addText(uvSize=(1, 1), boxSize=(0.7, 0.1), xyOffset=(0, 0), baseAnchor=(0.05, 0.5), textAnchor=(0, 0),
                       content="累计治愈: %s(%s)" % (healTotal,
                                                 healTotalAdd), color=(255, 255, 255, 255))
    await card.addText(uvSize=(1, 1), boxSize=(0.7, 0.1), xyOffset=(0, 0), baseAnchor=(0.05, 0.6), textAnchor=(0, 0),
                       content="累计死亡: %s(%s)" % (deadTotal, deadTotalAdd), color=(255, 255, 255, 255))
    await card.addText(uvSize=(1, 1), boxSize=(0.7, 0.1), xyOffset=(0, 0), baseAnchor=(0.05, 0.7), textAnchor=(0, 0),
                       content="境外输入: %s(%s)" % (inputNow, inputAdd), color=(255, 255, 255, 255))

    await card.addText(uvSize=(1, 1), boxSize=(0.7, 0.05), xyOffset=(0, 0), baseAnchor=(0.95, 0.95), textAnchor=(1, 1),
                       content=data.get("lastUpdateTime"), color=Cardimage.hex2dec("ffa4a4a4"))
    return Message("[CQ:image,file=file:///%s]" % await card.getPath()), card
