import nonebot

from nonebot.adapters import satori
from nonebot.adapters.satori.models import User


class UserInfo:
    user_infos: dict = {}

    async def load_friends(self, bot: satori.Bot):
        nonebot.logger.info("Update user info from friends")
        friend_response = await bot.friend_list()
        while friend_response.next is not None:
            for i in friend_response.data:
                i: User = i
                self.user_infos[str(i.id)] = i
            friend_response = await bot.friend_list(next_token=friend_response.next)

        for i in friend_response.data:
            i: User = i
            self.user_infos[str(i.id)] = i

        nonebot.logger.info("Finish update user info")

    async def get(self, uid: int | str) -> User | None:
        try:
            return self.user_infos[str(uid)]
        except KeyError:
            return None

    async def put(self, user: User) -> bool:
        """
        向用户信息数据库中添加/修改一项，返回值仅代表数据是否变更，不代表操作是否成功
        Args:
            user: 要加入数据库的用户

        Returns: 当数据库中用户信息发生变化时返回 True, 否则返回 False

        """
        try:
            old_user: User = self.user_infos[str(user.id)]
            attr_edited = False
            if user.name is not None:
                if old_user.name != user.name:
                    attr_edited = True
                    self.user_infos[str(user.id)].name = user.name
            if user.nick is not None:
                if old_user.nick != user.nick:
                    attr_edited = True
                    self.user_infos[str(user.id)].nick = user.nick
            if user.avatar is not None:
                if old_user.avatar != user.avatar:
                    attr_edited = True
                    self.user_infos[str(user.id)].avatar = user.avatar
            return attr_edited
        except KeyError:
            self.user_infos[str(user.id)] = user
            return True

    def __init__(self):
        pass


user_infos = UserInfo()
