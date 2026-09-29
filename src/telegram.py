class TelegramClient:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token=bot_token; self.chat_id=chat_id
    def send_video(self, path: str, caption: str) -> int: raise NotImplementedError
    def send_photo(self, path: str, caption: str) -> int: raise NotImplementedError
    def send_document(self, path: str, caption: str) -> int: raise NotImplementedError
