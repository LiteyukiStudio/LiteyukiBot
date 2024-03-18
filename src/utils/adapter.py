from nonebot.adapters.onebot import v11, v12


Bot = v11.Bot | v12.Bot
GroupMessageEvent = v11.GroupMessageEvent | v12.GroupMessageEvent
PrivateMessageEvent = v11.PrivateMessageEvent | v12.PrivateMessageEvent
MessageEvent = v11.MessageEvent | v12.MessageEvent
