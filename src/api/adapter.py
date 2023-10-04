from nonebot.adapters import onebot

Bot = onebot.V11Bot | onebot.V12Bot
Message = onebot.V11Message | onebot.V12Message

Event = onebot.V11Event.Event | onebot.V12Event.Event
MessageEvent = onebot.V11Event.MessageEvent | onebot.V12Event.MessageEvent
GroupMessageEvent = onebot.V11Event.GroupMessageEvent | onebot.V12Event.GroupMessageEvent
