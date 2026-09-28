"""Mirror cleanup: drop legacy fault-case tables (memory replacement)."""

version = 3
name = "drop_fault_cases"


def upgrade(cursor) -> None:  # noqa: ANN001
    cursor.execute("DROP TABLE IF EXISTS fault_case_feedback")
    cursor.execute("DROP TABLE IF EXISTS fault_case")
