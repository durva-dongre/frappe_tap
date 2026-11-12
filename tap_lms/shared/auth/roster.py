from __future__ import annotations

from shared.db_retry import run_sql_all, run_sql_one


def _phone_variants(phone: str) -> list[str]:
    phone = str(phone or "").strip()
    if len(phone) == 10 and phone.isdigit():
        return [f"91{phone}", phone]
    if len(phone) == 12 and phone.startswith("91") and phone[2:].isdigit():
        return [phone, phone[2:]]
    return [phone] if phone else []


def get_students_for_phone(phone: str) -> list[dict]:
    variants = _phone_variants(phone)
    if not variants:
        return []
    placeholders = ", ".join(["%s"] * len(variants))
    return run_sql_all(
        f"""
        SELECT name, name1, grade
          FROM "tabStudent"
         WHERE phone IN ({placeholders})
         ORDER BY creation ASC
        """,
        tuple(variants),
    )


def student_belongs_to_phone(student_id: str, phone: str) -> bool:
    variants = _phone_variants(phone)
    if not variants:
        return False
    placeholders = ", ".join(["%s"] * len(variants))
    row = run_sql_one(
        f"""SELECT 1 FROM "tabStudent" WHERE name = %s AND phone IN ({placeholders}) LIMIT 1""",
        tuple([student_id] + variants),
    )
    return row is not None