import os
from pathlib import Path
from dotenv import load_dotenv

# 1. Загрузка переменных окружения (из файла .env, который лежит в корне проекта visabot)
# Структура папок:
# visabot/
# ├── .env
# ├── leads.db
# ├── backend/
# │   └── visa_portal/
# │       └── settings.py
# └── frontend/
#     └── dist/

# BASE_DIR = .../visabot/backend
BASE_DIR = Path(__file__).resolve().parent.parent

# PROJECT_ROOT = .../visabot (Корень всего проекта)
PROJECT_ROOT = BASE_DIR.parent

# Загружаем .env из корня проекта
load_dotenv(PROJECT_ROOT / ".env")

# =========================================================
#  ОСНОВНЫЕ НАСТРОЙКИ
# =========================================================

# Секретный ключ берем из .env, иначе используем dev-ключ (только для локалки)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-secret-key-change-me-unsafe")

# DEBUG=True только если в .env написано DEBUG=True
DEBUG = os.getenv("DEBUG", "False") == "True"

# Разрешенные хосты. В продакшене здесь будет 'ваш-ник.pythonanywhere.com'
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")


# =========================================================
#  ПРИЛОЖЕНИЯ И MIDDLEWARE
# =========================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    
    # Сторонние
    "rest_framework",
    "corsheaders",
    
    # Наши приложения
    "crm",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware", # CORS должен быть высоко
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "visa_portal.urls"

# =========================================================
#  ШАБЛОНЫ (REACT INTEGRATION)
# =========================================================

# Путь к собранному фронтенду: visabot/frontend/dist
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Добавляем путь к dist, чтобы Django видел index.html от React
        "DIRS": [FRONTEND_DIST],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "visa_portal.wsgi.application"
ASGI_APPLICATION = "visa_portal.asgi.application"


# =========================================================
#  БАЗА ДАННЫХ (SHARED WITH BOT)
# =========================================================

# Пытаемся взять путь из .env, иначе строим относительно корня
# Это гарантирует, что и Django, и Бот смотрят в ОДИН файл.
LEADS_DB_PATH = os.getenv(
    "LEADS_DB_PATH",
    str(PROJECT_ROOT / "leads.db")
)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": LEADS_DB_PATH,
        # Увеличиваем таймаут ожидания для SQLite, чтобы избежать блокировок
        "OPTIONS": {
            "timeout": 20,
        }
    }
}


# =========================================================
#  МЕЖДУНАРОДНЫЕ НАСТРОЙКИ
# =========================================================

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = False  # False, т.к. в SQLite у нас TEXT поля без таймзон (совместимость с ботом)


# =========================================================
#  СТАТИКА (STATIC FILES)
# =========================================================

STATIC_URL = "/static/"

# Куда collectstatic будет собирать файлы (для продакшена)
STATIC_ROOT = BASE_DIR / "staticfiles"

# Где искать статику (включая ассеты React)
STATICFILES_DIRS = [
    # Если в frontend/dist/assets лежат JS/CSS, Django найдет их
    # и сможет отдать через runserver. 
    # На PythonAnywhere мы настроим алиас /assets/ -> frontend/dist/assets
    FRONTEND_DIST / "assets", 
]


# =========================================================
#  DRF & CORS
# =========================================================

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
}

# Разрешаем запросы с локального фронтенда (для разработки)
# В продакшене (когда фронт отдается с того же домена) CORS не нужен, но оставим для надежности.
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Если нужно передавать куки/авторизацию
CORS_ALLOW_CREDENTIALS = True

# Разрешить все заголовки
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]