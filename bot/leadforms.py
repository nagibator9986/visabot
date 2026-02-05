# link_forms_to_leads.py
import os
from datetime import datetime

from dotenv import load_dotenv

import db
from models import AuditLog
from google_forms_sync import _map_visa_country_for_lead  # уже есть в файле

load_dotenv()

def main():
    conn = db.get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, visa_country, form_id, response_id, respondent_email
        FROM form_responses
        WHERE lead_id IS NULL
          AND respondent_email IS NOT NULL
        """
    )
    rows = cur.fetchall()
    print(f"Найдено form_responses без lead_id: {len(rows)}")

    for row in rows:
        fr_id = row["id"]
        email = (row["respondent_email"] or "").strip().lower()
        visa_country = row["visa_country"]
        response_id = row["response_id"]

        if not email:
            print(f"- form_response id={fr_id}: пустой email, пропускаем")
            continue

        cur_lead = conn.cursor()
        cur_lead.execute(
            """
            SELECT id, from_address, questionnaire_status, form_ack_sent
            FROM leads
            WHERE lower(trim(from_address)) = ?
            ORDER BY datetime(COALESCE(created_at, '1970-01-01')) DESC, id DESC
            LIMIT 1
            """,
            (email,),
        )
        lead_row = cur_lead.fetchone()
        if not lead_row:
            print(f"- form_response id={fr_id}: лид по email '{email}' не найден")
            continue

        lead_id = lead_row["id"]
        print(
            f"- form_response id={fr_id}: привязываем к lead_id={lead_id} "
            f"(from_address={lead_row['from_address']})"
        )

        # 1) обновляем form_responses.lead_id
        cur_update = conn.cursor()
        cur_update.execute(
            "UPDATE form_responses SET lead_id = ? WHERE id = ?",
            (lead_id, fr_id),
        )

        # 2) обновляем leads как в _mark_lead_questionnaire_filled
        visa_country_code = _map_visa_country_for_lead(visa_country)
        cur_update.execute(
            """
            UPDATE leads
            SET
                questionnaire_status = 'filled',
                questionnaire_response_id = COALESCE(questionnaire_response_id, ?),
                visa_country = COALESCE(visa_country, ?)
            WHERE id = ?
            """,
            (response_id, visa_country_code, lead_id),
        )
        conn.commit()

        AuditLog.log(
            lead_id=lead_id,
            event="questionnaire_filled",
            details=f"Form response linked retrospectively, response_id={response_id}",
        )

    conn.close()
    print("Готово.")

if __name__ == "__main__":
    main()
