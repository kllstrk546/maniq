"""Кастомні винятки для роботи з базою даних."""


class DatabaseError(Exception):
    """Базовий виняток для помилок БД."""
    pass


class DayNotFoundError(DatabaseError):
    """Робочий день не знайдено."""
    pass


class DayAlreadyExistsError(DatabaseError):
    """Робочий день уже існує."""
    pass


class SlotNotFoundError(DatabaseError):
    """Часовий слот не знайдено."""
    pass


class SlotAlreadyExistsError(DatabaseError):
    """Часовий слот уже існує."""
    pass


class SlotHasBookingError(DatabaseError):
    """На слот уже є активне бронювання."""
    pass


class BookingNotFoundError(DatabaseError):
    """Бронювання не знайдено."""
    pass


class BookingAlreadyExistsError(DatabaseError):
    """У користувача вже є активне бронювання."""
    pass


class SlotNotAvailableError(DatabaseError):
    """Часовий слот недоступний для бронювання."""
    pass


class ReminderNotFoundError(DatabaseError):
    """Нагадування не знайдено."""
    pass


class SchedulePostNotFoundError(DatabaseError):
    """Пост розкладу не знайдено."""
    pass
