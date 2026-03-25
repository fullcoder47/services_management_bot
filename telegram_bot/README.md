# Telegram Bot Template

Clean Telegram bot starter built with:

- `aiogram 3`
- `SQLAlchemy async`
- `SQLite`

## Features

- Clean, scalable project structure
- `/start` command
- Auto user registration
- First registered user becomes `super_admin`
- Async database access with SQLAlchemy

## Project Structure

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

## Setup

1. Create a virtual environment and activate it.
2. Install dependencies:

```bash
pip install -e .
```

3. Copy `.env.example` to `.env` and set your bot token.
4. Run the bot:

```bash
python main.py
```

The SQLite database file is created automatically as `app.db`.
