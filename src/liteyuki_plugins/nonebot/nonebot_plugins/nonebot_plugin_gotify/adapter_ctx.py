from pydantic import BaseModel


class Context(BaseModel):
    user_id: str
    nickname: str
    message: str
    message_type: str | None = None

    def handle(self, event):
        pass

