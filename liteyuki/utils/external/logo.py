async def get_user_icon(platform: str, user_id: str) -> str:
    """
    获取用户头像
    Args:
        platform: qq, telegram, discord...
        user_id: 1234567890

    Returns:
        str: 头像链接
    """
    match platform:
        case "qq":
            return f"http://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
        case "telegram":
            return f"https://t.me/i/userpic/320/{user_id}.jpg"
        case "discord":
            return f"https://cdn.discordapp.com/avatars/{user_id}/"
        case _:
            return ""


async def get_group_icon(platform: str, group_id: str) -> str:
    """
    获取群组头像
    Args:
        platform: qq, telegram, discord...
        group_id: 1234567890

    Returns:
        str: 头像链接
    """
    match platform:
        case "qq":
            return f"http://p.qlogo.cn/gh/{group_id}/{group_id}/640"
        case "telegram":
            return f"https://t.me/c/{group_id}/"
        case "discord":
            return f"https://cdn.discordapp.com/icons/{group_id}/"
        case _:
            return ""
