import os.path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

# The ID and range of a sample spreadsheet.
## The sheet is private and contains questions to be loaded and asked during the onboarding process.
SAMPLE_SPREADSHEET_ID = "1thatsasecretsheetM"
SAMPLE_RANGE_NAME = "questions!A1:Z"
SERVICE_ACCOUNT_FILE = './google_sheet_credentials.json'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets'] # Or 'https://www.googleapis.com/auth/spreadsheets.readonly' for read-only


def read_sheet_retrieve_questions() -> dict:
    """
    Reads questions from the Google Sheet for the onboarding process.

    Only returns questions whose `is_active` column indicates that the
    question is active. Rows where `is_active` is empty or evaluates to
    a falsy value (anything other than 'true', '1', 'yes', or 'y'
    case-insensitively) are filtered out.

    Returns:
        dict: {"status": "success", "values": list[list[str]]} on success
              {"status": "error", "error_message": str} on failure.
    """
    creds = None
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )

        service = build("sheets", "v4", credentials=creds)

        # Call the Sheets API
        sheet = service.spreadsheets()
        result = (
            sheet.values()
            .get(spreadsheetId=SAMPLE_SPREADSHEET_ID, range=SAMPLE_RANGE_NAME)
            .execute()
        )
        values = result.get("values", [])

        if not values:
            return {"status": "error", "error_message": "No data found."}

        # Identify the 'is_active' column index
        headers = [h.strip().lower() for h in values[0]]
        if "is_active" not in headers:
            return {
                "status": "error",
                "error_message": "'is_active' column not found in sheet.",
            }

        active_idx = headers.index("is_active")

        truthy_set = {"true", "1", "yes", "y"}

        # Keep only active rows
        active_rows = [
            row
            for row in values[1:]
            if len(row) > active_idx
            and str(row[active_idx]).strip().lower() in truthy_set
        ]

        # Identify ordering column
        priority_idx = headers.index("question_order_priority") if "question_order_priority" in headers else None

        if priority_idx is not None:
            def _priority_val(row):
                try:
                    return int(row[priority_idx])
                except (ValueError, IndexError):
                    # Treat missing/invalid values as very low priority (last)
                    return float("inf")

            # Python sort is stable, so equal priorities retain sheet order
            active_rows.sort(key=_priority_val)

        filtered_values = [values[0]] + active_rows

        return {"status": "success", "values": filtered_values}

    except HttpError as err:
        return {"status": "error", "error_message": str(err)}
    except Exception as exc:  # Optional generic fallback
        return {"status": "error", "error_message": f"Unexpected error: {exc}"}
