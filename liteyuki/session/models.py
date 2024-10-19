from pydantic import BaseModel

class User(BaseModel):
    """
    用户信息
    Attributes:
        id: 用户ID
        name: 用户名
        nick: 用户昵称
        avatar: 用户头像图链接
    """
    id: str
    name: str | None
    nick: str | None
    avatar: str | None

class Scene(BaseModel):
    """
    场景信息
    Attributes:
        id: 场景ID
        type: 场景类型
        name: 场景名
        avatar: 场景头像图链接
        parent: 父场景
    """
    id: str
    type: str
    name: str | None
    avatar: str | None
    parent: "Scene | None"

class Session(BaseModel):
    """
    会话信息
    Attributes:
        self_id: 机器人ID
        adapter: 适配器ID
        scope: 会话范围
        scene: 场景信息
        user: 用户信息
        member: 成员信息，仅频道及群聊有效
        operator: 操作者信息，仅频道及群聊有效
    """
    self_id: str
    adapter: str
    scope: str
    scene: Scene
    user: User
    member: "Member | None"
    operator: "Member | None"