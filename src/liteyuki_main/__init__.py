import json
import os
import random

import nonebot
from nonebot import get_driver, logger, on_command
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from src.api.adapter import Bot, Message, MessageEvent
from src.api.resource import Language, ResourcePack, load_resource_from_index, language_data, system_lang
from src.api.data import Data

# register superuser
driver = get_driver()

# load resource pack
load_resource_from_index()


@driver.on_bot_connect
async def detect_superuser(bot: Bot):
    db = Data('common', 'config')
    db.remove('auth_code')
    if not len(bot.config.superusers):
        auth_code = str(random.randint(1000, 9999))
        db.set('auth_code', auth_code)
        nonebot.logger.opt(colors=True).warning(Language().get('log.main.no_superusers', CS=list(bot.config.command_start)[0], AUTH_CODE=auth_code))


cmd_reg_su = on_command(cmd='SU')
su_test = on_command(cmd='ST', permission=SUPERUSER)


@cmd_reg_su.handle()
async def _(bot: Bot, event: MessageEvent, arg: Message = CommandArg(), ):
    db = Data('common', 'config')
    ul = Language.get_user_language(event.user_id)
    auth_code = db.get('auth_code', None)
    if isinstance(auth_code, str):
        if str(arg) == auth_code:
            bot.config.superusers.add(event.user_id)
            await cmd_reg_su.send(ul.get('msg.main.suc_to_reg_su', USER_ID=event.user_id))
            logger.opt(colors=True).success(Language().get('log.main.suc_to_reg_su', USER_ID=event.user_id))
        else:
            await cmd_reg_su.send(ul.get('msg.main.fail_to_reg_su', USER_ID=event.user_id))
            logger.opt(colors=True).warning(Language().get('log.main.fail_to_reg_su', USER_ID=event.user_id))


@su_test.handle()
async def _():
    await su_test.send('suc')
