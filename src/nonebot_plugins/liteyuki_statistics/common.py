from src.utils.base.data import Database, LiteModel


class MessageEventModel(LiteModel):
    TABLE_NAME: str = "message_event"
    time: int = 0

    bot_id: str = ""
    adapter: str = ""

    user_id: str = ""
    group_id: str = ""

    message_id: str = ""
    message: list = []
    message_text: str = ""
    message_type: str = ""


msg_db = Database("data/liteyuki/msg.ldb")
msg_db.auto_migrate(MessageEventModel())