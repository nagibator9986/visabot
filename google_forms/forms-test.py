from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------------- CONFIG ----------------
SCOPES = [
    "https://www.googleapis.com/auth/forms.body",
    "https://www.googleapis.com/auth/drive"
]
SERVICE_ACCOUNT_FILE = "credentials.json"

# ---------------- TEST ----------------
def main():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )

    service = build("forms", "v1", credentials=creds)

    try:
        # Пробуем создать тестовую форму
        form = service.forms().create(
            body={"info": {"title": "TEST FORM"}}
        ).execute()

        print("✅ Форма успешно создана!")
        print("Form ID:", form.get("formId"))
        print("Responder URI:", form.get("responderUri"))

    except HttpError as e:
        print("❌ Ошибка при создании формы:")
        print("Status:", e.resp.status)
        print("Content:", e.content.decode())

if __name__ == "__main__":
    main()
