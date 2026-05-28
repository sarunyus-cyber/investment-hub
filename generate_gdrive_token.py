"""
รันสคริปต์นี้ครั้งเดียวบนเครื่องตัวเอง เพื่อสร้าง GDRIVE_TOKEN_JSON
ที่จะนำไปใส่เป็น Environment Variable บน Railway

วิธีใช้:
  1. วาง credentials.json ในโฟลเดอร์เดียวกัน
  2. python generate_gdrive_token.py
  3. copy output ไปใส่ GDRIVE_TOKEN_JSON ใน Railway
"""

import json, base64, pickle
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.send"
]

def main():
    creds = None
    token_file = Path("token.pickle")

    if token_file.exists():
        with open(token_file, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "wb") as f:
            pickle.dump(creds, f)

    # Build JSON token
    token_data = {
        "token":         creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri":     creds.token_uri,
        "client_id":     creds.client_id,
        "client_secret": creds.client_secret,
    }

    json_str    = json.dumps(token_data)
    b64_encoded = base64.b64encode(json_str.encode()).decode()

    print("\n" + "="*60)
    print("✅ Copy ค่าด้านล่างนี้ไปใส่ใน Railway Environment Variable")
    print("   Variable name: GDRIVE_TOKEN_JSON")
    print("="*60)
    print(b64_encoded)
    print("="*60)
    print("\nเสร็จแล้ว! นำค่าด้านบนไปใส่ใน Railway → Variables\n")

if __name__ == "__main__":
    main()
