import aiosqlite
from config import DB_PATH


def get_db() -> aiosqlite.Connection:
    """Повертає з'єднання з базою даних."""
    return aiosqlite.connect(DB_PATH)


async def _recreate_bookings_table(db: aiosqlite.Connection) -> None:
    """Перебудовує таблицю bookings з актуальним CHECK за статусами."""
    await db.execute("PRAGMA foreign_keys=OFF")
    await db.execute("BEGIN")
    try:
        await db.execute(
            """
            CREATE TABLE bookings_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                time_slot_id INTEGER NOT NULL,
                client_name TEXT,
                client_phone TEXT,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'cancelled', 'cancelled_by_user', 'completed')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cancelled_at TIMESTAMP,
                FOREIGN KEY (time_slot_id) REFERENCES time_slots(id) ON DELETE CASCADE
            )
            """
        )

        async with db.execute("PRAGMA table_info(bookings)") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}

        client_name_expr = "client_name" if "client_name" in columns else "NULL"
        client_phone_expr = "client_phone" if "client_phone" in columns else "NULL"

        await db.execute(
            f"""
            INSERT INTO bookings_new (
                id, user_id, time_slot_id, client_name, client_phone, status, created_at, cancelled_at
            )
            SELECT
                id, user_id, time_slot_id, {client_name_expr}, {client_phone_expr}, status, created_at, cancelled_at
            FROM bookings
            """
        )

        await db.execute("DROP TABLE bookings")
        await db.execute("ALTER TABLE bookings_new RENAME TO bookings")
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    finally:
        await db.execute("PRAGMA foreign_keys=ON")


async def _ensure_bookings_schema(db: aiosqlite.Connection) -> None:
    """Гарантує наявність колонок client_name/client_phone і статусу cancelled_by_user."""
    async with db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='bookings'"
    ) as cursor:
        table_row = await cursor.fetchone()

    table_sql = (table_row[0] or "") if table_row else ""
    has_cancelled_by_user = "cancelled_by_user" in table_sql

    async with db.execute("PRAGMA table_info(bookings)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}

    if "client_name" not in columns:
        await db.execute("ALTER TABLE bookings ADD COLUMN client_name TEXT")
    if "client_phone" not in columns:
        await db.execute("ALTER TABLE bookings ADD COLUMN client_phone TEXT")

    if not has_cancelled_by_user:
        await _recreate_bookings_table(db)


async def _ensure_reminders_schema(db: aiosqlite.Connection) -> None:
    """Гарантує наявність колонок для планувальника нагадувань."""
    async with db.execute("PRAGMA table_info(reminders)") as cursor:
        columns = {row[1] for row in await cursor.fetchall()}

    if "remind_at" not in columns:
        await db.execute("ALTER TABLE reminders ADD COLUMN remind_at TIMESTAMP")
    if "job_id" not in columns:
        await db.execute("ALTER TABLE reminders ADD COLUMN job_id TEXT")
    if "status" not in columns:
        await db.execute("ALTER TABLE reminders ADD COLUMN status TEXT")
    if "cancelled_at" not in columns:
        await db.execute("ALTER TABLE reminders ADD COLUMN cancelled_at TIMESTAMP")

    await db.execute(
        "UPDATE reminders SET remind_at = COALESCE(remind_at, scheduled_at) WHERE remind_at IS NULL"
    )
    await db.execute(
        """
        UPDATE reminders
        SET status = CASE
            WHEN status IN ('scheduled', 'sent', 'cancelled') THEN status
            WHEN is_sent = 1 THEN 'sent'
            ELSE 'scheduled'
        END
        """
    )


async def init_db() -> None:
    """Ініціалізує базу даних: створює таблиці та індекси."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Налаштування SQLite
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")

        # Робочі дні майстра
        await db.execute("""
            CREATE TABLE IF NOT EXISTS work_days (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_date DATE NOT NULL UNIQUE,
                is_working BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Часові слоти
        await db.execute("""
            CREATE TABLE IF NOT EXISTS time_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_day_id INTEGER NOT NULL,
                slot_time TIME NOT NULL,
                is_available BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (work_day_id) REFERENCES work_days(id) ON DELETE CASCADE,
                UNIQUE(work_day_id, slot_time)
            )
        """)

        # Бронювання
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                time_slot_id INTEGER NOT NULL,
                client_name TEXT,
                client_phone TEXT,
                status TEXT NOT NULL DEFAULT 'active' CHECK (
                    status IN ('active', 'cancelled', 'cancelled_by_user', 'completed')
                ),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cancelled_at TIMESTAMP,
                FOREIGN KEY (time_slot_id) REFERENCES time_slots(id) ON DELETE CASCADE
            )
        """)

        await _ensure_bookings_schema(db)

        # Нагадування
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                reminder_type TEXT NOT NULL CHECK (reminder_type IN ('24h', '2h', 'custom')),
                scheduled_at TIMESTAMP NOT NULL,
                remind_at TIMESTAMP,
                job_id TEXT,
                status TEXT DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'sent', 'cancelled')),
                sent_at TIMESTAMP,
                cancelled_at TIMESTAMP,
                is_sent BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
            )
        """)
        await _ensure_reminders_schema(db)

        # Пости з розкладом
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schedule_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_date DATE NOT NULL UNIQUE,
                channel_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP
            )
        """)

        # Прості налаштування ключ-значення (контент, посилання тощо)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Індекси для продуктивності
        await db.execute("CREATE INDEX IF NOT EXISTS idx_time_slots_day ON time_slots(work_day_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bookings_slot ON bookings(time_slot_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_reminders_booking ON reminders(booking_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_reminders_scheduled ON reminders(scheduled_at, is_sent)")
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_reminders_status_remind_at ON reminders(status, remind_at)"
        )
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_reminder_booking_type "
            "ON reminders(booking_id, reminder_type)"
        )

        # Partial unique index: 1 активне бронювання на часовий слот
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_booking_per_slot
            ON bookings(time_slot_id)
            WHERE status = 'active'
        """)

        # Partial unique index: 1 активне бронювання у користувача (за потреби)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_booking_per_user
            ON bookings(user_id)
            WHERE status = 'active'
        """)

        await db.commit()
