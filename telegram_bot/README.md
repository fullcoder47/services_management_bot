# Telegram Attendance Bot - Phase 1

Bu bosqichda multi-company attendance bot uchun clean architecture asosidagi foundation tayyorlangan.

## Implement qilingan qismlar

- `app/` ichida clean architecture skeleti
- Pydantic Settings asosidagi konfiguratsiya
- PostgreSQL uchun async SQLAlchemy setup
- Alembic'ga tayyor metadata va naming convention
- `User` modeli va `Role` / `Language` enumlari
- Localization helper va 3 til: `uz`, `ru`, `en`
- `/start` oqimi, til tanlash va `SUPER_ADMIN` bootstrap logikasi
- Super admin paneli uchun bazaviy reply keyboard va placeholder handlerlar

## Localization qanday ishlaydi

- Foydalanuvchiga ko'rinadigan matnlar `t(lang, uz=..., ru=..., en=...)` helper orqali olinadi.
- Birinchi `/start` da userda til bo'lmasa, inline keyboard bilan til tanlanadi.
- Tanlangan til `users.language` maydoniga saqlanadi.
- Keyingi `/start` da til qayta so'ralmaydi.

## O'rnatish

1. Virtual environment yarating va faollashtiring.
2. Dependency o'rnating:

```bash
pip install -e .
```

3. `.env.example` dan `.env` yarating va qiymatlarni to'ldiring.
4. PostgreSQL bazasini tayyorlang.

## Ishga tushirish

```bash
python -m app.main
```

Yoki:

```bash
attendance-bot
```

## Environment variables

```env
BOT_TOKEN=your_bot_token_here
DB_URL=postgresql+asyncpg://postgres:password@localhost:5432/attendance_bot
SUPER_ADMIN_TELEGRAM_IDS=123456789,987654321
```

## Eslatma

- Hozircha faqat foundation va super admin bootstrap implement qilingan.
- `company CRUD`, `employees`, `attendance`, `shifts`, `reports`, `geolocation`, `video note` hali kiritilmagan.
- Startup vaqtida `users` jadvali avtomatik yaratiladi.
