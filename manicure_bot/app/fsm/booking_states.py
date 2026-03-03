from aiogram.fsm.state import State, StatesGroup


class BookingStates(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    entering_name = State()
    entering_phone = State()
    confirming = State()


class RescheduleStates(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    confirming = State()
