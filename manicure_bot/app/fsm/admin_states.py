from aiogram.fsm.state import State, StatesGroup


class AdminContentStates(StatesGroup):
    editing_prices = State()
    editing_portfolio_url = State()
