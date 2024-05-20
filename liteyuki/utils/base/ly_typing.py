from nonebot.adapters.onebot import v11, v12
from nonebot.adapters import satori

T_Bot = v11.Bot | v12.Bot | satori.Bot
T_GroupMessageEvent = v11.GroupMessageEvent | v12.GroupMessageEvent
T_PrivateMessageEvent = v11.PrivateMessageEvent | v12.PrivateMessageEvent
T_MessageEvent = v11.MessageEvent | v12.MessageEvent | satori.MessageEvent
T_Message = v11.Message | v12.Message | satori.Message
