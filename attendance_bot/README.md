# Attendance Bot - Phase 1

Bu loyiha multi-company Telegram attendance bot uchun clean architecture asosidagi birinchi foundation bosqichidir.

## Implement qilingan qismlar

- clean architecture skeleti
- Pydantic Settings asosidagi konfiguratsiya
- PostgreSQL uchun async SQLAlchemy setup
- Alembic'ga tayyor metadata va naming convention
- `User` modeli, `Role` va `Language` enumlari
- localization helper va `uz` / `ru` / `en` tillari
- `/start` oqimi, til tanlash va super admin bootstrap logikasi
- super admin paneli uchun bazaviy reply keyboard va placeholder handlerlar
- startup vaqtida config va DB xatolari uchun aniq error reporting

## Localization

- Barcha foydalanuvchi matnlari translation helper orqali olinadi
- `/start` bosilganda til saqlanmagan bo'lsa, avval til tanlanadi
- Tanlangan til `users.language` maydoniga saqlanadi
- Keyingi `/start` da til qayta so'ralmaydi

## O'rnatish

```bash
pip install -e .
```

`.env.example` dan `.env` yarating va qiymatlarni to'ldiring.

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

## Railway eslatmasi

- Agar botni lokal kompyuterdan ishga tushirsangiz, `*.railway.internal` host ishlamaydi
- Bunday hostlar Railway ichki tarmog'i uchun mo'ljallangan
- Lokal ishga tushirish uchun Railway public PostgreSQL hosti yoki local PostgreSQL ishlating
- Deploy uchun root `main.py`, `Procfile` va `railpack.json` qo'shilgan
- Railway start command sifatida `python -m app.main` ishlatiladi

## Eslatma

- Bu bosqichda hali `company CRUD`, `employees`, `attendance`, `shifts`, `reports`, `geolocation`, `video note` yo'q
- Startup vaqtida `users` jadvali avtomatik yaratiladi
