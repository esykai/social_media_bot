class UserState:
    def __init__(self):
        self.media_files = []
        self.description = ""
        self.selected_platforms = {"telegram": True, "x": True}
        self.menu_message_id = None
        self.current_mode = "idle"  # idle, adding_media, adding_text

# Глобальный словарь для хранения состояний пользователей
user_states = {}
