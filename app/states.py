from aiogram.fsm.state import State, StatesGroup

class PostStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_media = State()
    editing_content = State()
