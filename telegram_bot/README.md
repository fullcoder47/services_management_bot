# Telegram Bot Shabloni

Toza va kengaytirishga tayyor Telegram bot loyihasi:

- `aiogram 3`
- `SQLAlchemy async`
- `SQLite`

## Imkoniyatlar

- Toza va kengaytiriladigan loyiha tuzilmasi
- `/start` buyrug'i
- Foydalanuvchini avtomatik ro'yxatdan o'tkazish
- Birinchi foydalanuvchi `super_admin` bo'ladi
- SQLAlchemy orqali async ma'lumotlar bazasi ishlashi

## Loyiha Tuzilishi

```text
telegram_bot/
|-- bot/
|   |-- handlers/
|   |-- keyboards/
|   `-- middlewares/
|-- core/
|-- db/
|   `-- models/
|-- services/
|-- .env.example
|-- main.py
`-- pyproject.toml
```

## Ishga Tushirish

1. Virtual muhit yarating va uni faollashtiring.
2. Kerakli kutubxonalarni o'rnating:

```bash
pip install -e .
```

3. `.env.example` faylidan `.env` nusxa yarating va bot tokenini kiriting.
4. Botni ishga tushiring:

```bash
python main.py
```

SQLite bazasi avtomatik ravishda `app.db` fayli sifatida yaratiladi.
