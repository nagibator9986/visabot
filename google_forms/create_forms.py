from __future__ import annotations

import os
import time
from typing import List, Dict, Any, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ----------------- CONFIG -----------------
SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/forms.responses.readonly",
]

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


# ----------------- AUTH -----------------
def get_forms_service():
    """
    Авторизация через OAuth (браузерное окно).
    Формы создаются/редактируются от имени пользователя.
    """
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

            with open(TOKEN_FILE, "w", encoding="utf-8") as token:
                token.write(creds.to_json())

    service = build("forms", "v1", credentials=creds)
    return service


# ------------ HELPERS FOR QUESTIONS ------------

def short_question(
    title: str,
    description: Optional[str] = None,
    required: bool = True,
) -> Dict[str, Any]:
    """
    Короткий текстовый вопрос (Short answer).
    ВАЖНО: Forms API не даёт включить numeric/email validation –
    поэтому жёстко прописываем правила в description.
    """
    item: Dict[str, Any] = {
        "title": title,
        "questionItem": {
            "question": {
                "required": required,
                "textQuestion": {}
            }
        }
    }
    if description:
        item["description"] = description
    return item


def paragraph_question(
    title: str,
    description: Optional[str] = None,
    required: bool = False,
) -> Dict[str, Any]:
    """Длинный ответ (Paragraph)."""
    item: Dict[str, Any] = {
        "title": title,
        "questionItem": {
            "question": {
                "required": required,
                "textQuestion": {"paragraph": True}
            }
        }
    }
    if description:
        item["description"] = description
    return item


def choice_question(
    title: str,
    options: List[str],
    description: Optional[str] = None,
    required: bool = True,
    shuffle: bool = False,
) -> Dict[str, Any]:
    """Вопрос с выбором одного варианта (Multiple choice)."""
    item: Dict[str, Any] = {
        "title": title,
        "questionItem": {
            "question": {
                "required": required,
                "choiceQuestion": {
                    "type": "RADIO",
                    "options": [{"value": opt} for opt in options],
                    "shuffle": shuffle,
                }
            }
        }
    }
    if description:
        item["description"] = description
    return item


def section_header(
    title: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Заголовок раздела (Section header) для Google Forms API v1."""
    item: Dict[str, Any] = {
        "title": title,
        # Для разделов в Forms API используется pageBreakItem
        "pageBreakItem": {}
    }
    if description:
        item["description"] = description
    return item




# ------------ FORM BLUEPRINT ------------

LATIN_HEADER = (
    "ВАЖНО: ВСЕ ОТВЕТЫ ЗАПОЛНЯЙТЕ ЛАТИНИЦЕЙ (английскими буквами).\n"
    "Не используйте кириллицу, русские/казахские буквы и спецсимволы, кроме явно указанных в примерах.\n\n"
)


def build_questionnaire_questions() -> List[Dict[str, Any]]:
    """
    Опросник по структуре из твоего списка:

    1. Личные данные
    2. Семейное положение (+ дети)
    3. Документы
    4. Проф. деятельность
    5. Цель поездки
    6. Дополнительно
    """
    q: List[Dict[str, Any]] = []

    # --- 1. Личные данные ---
    q.append(section_header(
        "1. Личные данные",
        "Заполните все поля внимательно. Все данные — латиницей."
    ))

    q.append(short_question(
        "Имя (Prénom)",
        "Имя латиницей, как в паспорте.\nПример: IVAN",
        True,
    ))

    q.append(short_question(
        "Фамилия (Nom)",
        "Фамилия латиницей, как в паспорте.\nПример: IVANOV",
        True,
    ))

    q.append(short_question(
        "Девичья фамилия (Nom de jeune fille)",
        "Если есть — укажите девичью фамилию латиницей.\n"
        "Если нет — оставьте пустым или напишите: NO",
        False,
    ))

    q.append(short_question(
        "Псевдоним (Pseudo)",
        "Если используете псевдоним — укажите его латиницей.\n"
        "Если нет — оставьте пустым.",
        False,
    ))

    q.append(short_question(
        "Дата рождения (Date de naissance)",
        "Формат: DD.MM.YYYY\nПример: 25.12.1990",
        True,
    ))

    q.append(short_question(
        "Место рождения (Lieu de naissance)",
        "Город / населённый пункт рождения латиницей.\nПример: ALMATY",
        True,
    ))

    q.append(short_question(
        "Страна рождения (Pays de naissance)",
        "Страна рождения латиницей.\nПример: KAZAKHSTAN",
        True,
    ))

    q.append(short_question(
        "Национальность (текущая)",
        "Текущая национальность латиницей.\nПример: KAZAKH",
        True,
    ))

    q.append(short_question(
        "Национальность (по происхождению)",
        "Если отличается от текущей — укажите.\n"
        "Если совпадает или не применимо — оставьте пустым или напишите: SAME",
        False,
    ))

    q.append(paragraph_question(
        "Адрес проживания",
        "Полный адрес латиницей: квартира, дом, улица, город, индекс, страна.\n"
        "Пример:\n"
        "APARTMENT 10, 15 ABAY AVE,\n"
        "ALMATY, KAZAKHSTAN, 050000",
        True,
    ))

    q.append(short_question(
        "Телефон",
        "Основной контактный номер.\n"
        "Только цифры и знак +, без пробелов, скобок и тире.\n"
        "Пример: +77011234567",
        True,
    ))
    q.append(short_question(
        "E-mail",
        "Основной e-mail для связи.\n"
        "Пример: ivan.ivanov@example.com",
        True,
    ))

    # --- 2. Семейное положение ---
    q.append(section_header(
        "2. Семейное положение",
        "Если не состоите в браке, поля о супруге можно оставить пустыми."
    ))

    # Можно сразу спросить статус
    q.append(choice_question(
        "Семейное положение",
        options=["SINGLE", "MARRIED", "DIVORCED", "WIDOWED"],
        description="Выберите вариант, который лучше всего описывает вашу ситуацию.",
        required=True,
    ))

    q.append(short_question(
        "Имя супруга/супруги",
        "Имя супруга/супруги латиницей.\n"
        "Если не в браке — оставьте пустым.",
        False,
    ))

    q.append(short_question(
        "Фамилия супруга/супруги",
        "Фамилия супруга/супруги латиницей.",
        False,
    ))

    q.append(short_question(
        "Дата рождения супруга/супруги",
        "Формат: DD.MM.YYYY.\nПример: 01.01.1990",
        False,
    ))

    q.append(short_question(
        "Страна рождения супруга/супруги",
        "Страна рождения супруга/супруги латиницей.\nПример: KAZAKHSTAN",
        False,
    ))

    q.append(short_question(
        "Национальность супруга/супруги",
        "Национальность супруга/супруги латиницей.\nПример: KAZAKH",
        False,
    ))

    # Дети
    q.append(section_header(
        "Дети (если есть)",
        "Заполните данные для каждого ребёнка. Если детей нет — оставьте пустым."
    ))

    for i in range(1, 4):
        child_prefix = f"Ребёнок {i}"
        q.append(short_question(
            f"{child_prefix}: Имя",
            "Имя ребёнка латиницей.\nПример: AIGERIM",
            False,
        ))
        q.append(short_question(
            f"{child_prefix}: Дата рождения",
            "Формат: DD.MM.YYYY.\nПример: 15.03.2015",
            False,
        ))
        q.append(short_question(
            f"{child_prefix}: Место рождения",
            "Город/место рождения ребёнка латиницей.\nПример: ALMATY",
            False,
        ))
        q.append(short_question(
            f"{child_prefix}: Национальность",
            "Национальность ребёнка латиницей.\nПример: KAZAKH",
            False,
        ))

    # --- 3. Документы ---
    q.append(section_header("3. Документы"))

    q.append(choice_question(
        "Тип документа",
        options=["PASSPORT", "TRAVEL DOCUMENT", "OTHER"],
        description="Выберите тип основного документа (паспорт/другое).",
        required=True,
    ))

    q.append(short_question(
        "Номер паспорта",
        "Номер документа латиницей и цифрами, без пробелов.\n"
        "Пример: N12345678",
        True,
    ))

    q.append(short_question(
        "Дата выдачи",
        "Дата выдачи документа в формате DD.MM.YYYY.\n"
        "Пример: 01.01.2020",
        True,
    ))

    q.append(short_question(
        "Срок действия",
        "Дата окончания действия документа в формате DD.MM.YYYY.\n"
        "Пример: 01.01.2030",
        True,
    ))

    q.append(short_question(
        "Кем выдан",
        "Орган, выдавший документ, латиницей.\n"
        "Пример: MINISTRY OF INTERNAL AFFAIRS",
        True,
    ))

    # --- 4. Профессиональная деятельность ---
    q.append(section_header("4. Профессиональная деятельность"))

    q.append(short_question(
        "Профессия",
        "Ваша профессия латиницей.\n"
        "Примеры: ACCOUNTANT / ENGINEER / MANAGER",
        True,
    ))

    q.append(short_question(
        "Работодатель",
        "Название работодателя латиницей.\n"
        "Пример: TOO \"ABC COMPANY\"",
        True,
    ))

    q.append(paragraph_question(
        "Адрес работодателя",
        "Полный адрес работодателя латиницей.\n"
        "Пример:\n"
        "OFFICE 5, 20 SATPAYEV ST,\n"
        "ALMATY, KAZAKHSTAN, 050000",
        True,
    ))

    q.append(short_question(
        "Телефон работодателя",
        "Телефон работодателя. Только цифры и +, без пробелов.\n"
        "Пример: +77273334455",
        True,
    ))

    # --- 5. Цель поездки ---
    q.append(section_header("5. Цель поездки"))

    q.append(short_question(
        "Конечный пункт назначения",
        "Город/населённый пункт конечного назначения латиницей.\n"
        "Пример: PARIS",
        True,
    ))

    q.append(paragraph_question(
        "Адрес пребывания",
        "Полный адрес места пребывания (отель, друзья и т.п.) латиницей.\n"
        "Пример:\n"
        "HOTEL ABC, 10 RUE DE LA PAIX,\n"
        "75002 PARIS, FRANCE",
        True,
    ))

    q.append(short_question(
        "Цель поездки (Motif de séjour)",
        "Кратко опишите цель поездки латиницей.\n"
        "Примеры: TOURISM / BUSINESS / VISIT FAMILY",
        True,
    ))

    q.append(short_question(
        "Дата въезда (планируемая)",
        "Планируемая дата въезда в формате DD.MM.YYYY.\n"
        "Пример: 10.07.2025",
        True,
    ))

    q.append(short_question(
        "Продолжительность пребывания",
        "Планируемая длительность пребывания в ДНЯХ. Только цифры.\n"
        "Пример: 14",
        True,
    ))

    # --- 6. Дополнительно ---
    q.append(section_header("6. Дополнительно"))

    q.append(short_question(
        "Количество предыдущих поездок",
        "Сколько раз вы ранее ездили в эту страну/зону.\n"
        "Только цифры. Примеры: 0 / 1 / 3",
        True,
    ))

    q.append(paragraph_question(
        "Даты последних въездов",
        "Укажите даты последних въездов в формате DD.MM.YYYY.\n"
        "Можно перечислить через запятую.\n"
        "Пример: 01.06.2022, 15.09.2023",
        False,
    ))

    q.append(paragraph_question(
        "Другие сведения",
        "Любая дополнительная информация, которая может быть важна для анкеты.\n"
        "Можно оставить пустым.",
        False,
    ))

    return q


# ------------ FORM CREATION ------------

def create_form(
    service,
    title: str,
    description: str,
    items: List[Dict[str, Any]],
) -> str:
    """
    Создаёт НОВУЮ форму.
    Возвращает formId.
    """
    form = None
    for attempt in range(3):
        try:
            form = service.forms().create(
                body={
                    "info": {
                        "title": title
                    }
                }
            ).execute()
            break
        except HttpError as e:
            if e.resp.status >= 500 and attempt < 2:
                print(f"[WARN] Forms.create 5xx (attempt {attempt + 1}/3), retry...")
                time.sleep(2 * (attempt + 1))
                continue
            print("HttpError on create:", e)
            raise

    if not form:
        raise RuntimeError("Не удалось создать форму через Forms API")

    form_id = form["formId"]

    # Собираем batchUpdate: описание + вопросы
    requests: List[Dict[str, Any]] = []

    if description:
        requests.append({
            "updateFormInfo": {
                "info": {
                    "title": title,
                    "description": description,
                },
                "updateMask": "title,description",
            }
        })

    for index, item in enumerate(items):
        requests.append({
            "createItem": {
                "item": item,
                "location": {"index": index}
            }
        })

    if requests:
        service.forms().batchUpdate(
            formId=form_id,
            body={"requests": requests}
        ).execute()

    updated_form = service.forms().get(formId=form_id).execute()
    responder_uri = updated_form.get("responderUri")
    print(f"[INFO] Создана форма '{title}', formId={form_id}")
    print(f"[INFO] Ссылка для ответов: {responder_uri}\n")

    return form_id

def replace_form_content(
    service,
    form_id: str,
    title: str,
    description: str,
    items: List[Dict[str, Any]],
) -> None:
    """
    Полностью пересобирает существующую форму:
    1) По одному удаляет все старые вопросы (deleteItem по index=0).
    2) Обновляет title/description.
    3) Создаёт новые вопросы по заданному списку.

    formId и ссылка на форму остаются теми же.
    """
    # 1) Удаляем все существующие вопросы по одному
    while True:
        form = service.forms().get(formId=form_id).execute()
        existing_items = form.get("items", [])
        if not existing_items:
            break

        # всегда удаляем элемент с index = 0
        service.forms().batchUpdate(
            formId=form_id,
            body={
                "requests": [
                    {
                        "deleteItem": {
                            "location": {
                                "index": 0
                            }
                        }
                    }
                ]
            },
        ).execute()

    print(f"[INFO] Все старые вопросы удалены (formId={form_id})")

    # 2) Обновляем заголовок и описание + создаём новые вопросы
    requests: List[Dict[str, Any]] = []

    # info
    requests.append({
        "updateFormInfo": {
            "info": {
                "title": title,
                "description": description,
            },
            "updateMask": "title,description",
        }
    })

    # items
    for index, item in enumerate(items):
        requests.append({
            "createItem": {
                "item": item,
                "location": {"index": index}
            }
        })

    service.forms().batchUpdate(
        formId=form_id,
        body={"requests": requests}
    ).execute()

    updated_form = service.forms().get(formId=form_id).execute()
    responder_uri = updated_form.get("responderUri")
    print(f"[INFO] Форма '{title}' обновлена (formId={form_id})")
    print(f"[INFO] Ссылка для ответов: {responder_uri}\n")


def sync_form(
    service,
    title: str,
    description: str,
    items: List[Dict[str, Any]],
    form_id: Optional[str] = None,
) -> str:
    """
    - если form_id не указан: создаёт новую форму и возвращает новый formId;
    - если form_id указан: полностью пересобирает существующую форму с этим id.
    """
    if form_id:
        replace_form_content(service, form_id, title, description, items)
        return form_id
    else:
        new_id = create_form(service, title, description, items)
        return new_id

# ------------ MAIN ------------

def main():
    service = get_forms_service()

    # Если форма уже существует и ты хочешь ЕЁ обновить — вставь сюда formId
    # (тот, который из URL /d/<formId>/edit)
    FORM_ID = "1QL8-TXhTlhbXitN1jJUY-mUsxczTqutPwXQQN5tcpZI"

    title = "Опросник для визового досье"
    base_description = (
        "Заполните, пожалуйста, все поля максимально внимательно.\n"
        "Данные будут использованы для подготовки визовой анкеты.\n"
        "При необходимости приложите копии документов отдельным письмом."
    )

    description = LATIN_HEADER + base_description.strip()
    items = build_questionnaire_questions()

    form_id = sync_form(service, title, description, items, form_id=FORM_ID or None)
    print("Опросник formId:", form_id)
    print("Сохрани этот formId для дальнейших обновлений.")



if __name__ == "__main__":
    main()
