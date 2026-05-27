"""
Morning Briefing Job — CEO สรุป + Email + Save Drive แล้ว exit
Railway Cron: 0 0 * * *  (07:00 Bangkok = 00:00 UTC)
"""
import anthropic
import json
import datetime
import os
import sys
import smtplib
import re
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload
import io

# ─── CONFIG ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
EMAIL_SENDER      = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD    = os.environ["EMAIL_PASSWORD"]
EMAIL_RECIPIENT   = os.environ["EMAIL_RECIPIENT"]
GDRIVE_FOLDER_ID  = os.environ.get("GDRIVE_FOLDER_ID", "")
GDRIVE_TOKEN_JSON = os.environ.get("GDRIVE_TOKEN_JSON", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

AGENT_META = {
    "journalist":        {"emoji": "📰", "name": "Agent 1 — นักข่าว"},
    "broker":            {"emoji": "📊", "name": "Agent 2 — Broker"},
    "technical":         {"emoji": "📈", "name": "Agent 3 — Technical"},
    "economist":         {"emoji": "🌐", "name": "Agent 4 — Economist"},
    "financial_advisor": {"emoji": "💰", "name": "Agent 5 — Financial Advisor"},
}

# ─── GOOGLE DRIVE ────────────────────────────────────────────────────────────
GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_gdrive_service():
    if not GDRIVE_TOKEN_JSON:
        return None
    try:
        import base64
        token_data = json.loads(base64.b64decode(GDRIVE_TOKEN_JSON).decode())
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=GDRIVE_SCOPES,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"[Drive] Auth error: {e}")
        return None

def load_cache_from_drive(date_str: str) -> dict | None:
    """Load yesterday's agent cache from Drive."""
    service = get_gdrive_service()
    if not service:
        return None
    try:
        fname = f"agent_cache_{date_str}.json"
        q = f"name='{fname}'"
        if GDRIVE_FOLDER_ID:
            q += f" and '{GDRIVE_FOLDER_ID}' in parents"
        res = service.files().list(q=q, fields="files(id,name)").execute()
        files = res.get("files", [])
        if not files:
            print(f"[Drive] Cache file not found: {fname}")
            return None
        fid = files[0]["id"]
        req = service.files().get_media(fileId=fid)
        buf = io.BytesIO()
        dl = MediaIoBaseDownload(buf, req)
        done = False
        while not done:
            _, done = dl.next_chunk()
        data = json.loads(buf.getvalue().decode("utf-8"))
        print(f"[Drive] Loaded cache: {fname} ✓")
        return data
    except Exception as e:
        print(f"[Drive] Load error: {e}")
        return None

def save_to_gdrive(content: str, filename: str) -> str:
    service = get_gdrive_service()
    if not service:
        return ""
    try:
        meta = {"name": filename, "mimeType": "text/plain"}
        if GDRIVE_FOLDER_ID:
            meta["parents"] = [GDRIVE_FOLDER_ID]
        media = MediaInMemoryUpload(content.encode("utf-8"), mimetype="text/plain")
        f = service.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
        url = f.get("webViewLink", "")
        print(f"[Drive] Saved {filename} → {url}")
        return url
    except Exception as e:
        print(f"[Drive] Save error: {e}")
        return ""

# ─── CEO AGENT ───────────────────────────────────────────────────────────────
CEO_SYSTEM = """คุณคือ CEO และ CIO ของกองทุนการลงทุนระดับสูง มีประสบการณ์กว่า 20 ปี
คุณสังเคราะห์ข้อมูลจาก 5 ผู้เชี่ยวชาญและตัดสินใจลงทุนอย่างรอบด้าน
คุณเชี่ยวชาญการเชื่อมโยงข่าว + ตลาด + Technical + Macro + Portfolio"""

def call_ceo(agent_reports: dict) -> str:
    print("[👑] CEO synthesizing reports...")
    sections = ""
    for key, report in agent_reports.items():
        m = AGENT_META[key]
        sections += f"\n\n{'─'*50}\n{m['emoji']} {m['name']}\n{'─'*50}\n{report}"

    today = datetime.datetime.utcnow()
    bkk_date = (today + datetime.timedelta(hours=7)).strftime("%d %B %Y")

    prompt = f"""คุณได้รับรายงานจาก 5 ผู้เชี่ยวชาญ:{sections}

---
กรุณาสร้าง CEO Morning Briefing รูปแบบนี้:

## 🌅 Morning Briefing — {bkk_date}

### 📌 Executive Summary
(3-4 ประโยค สรุปภาพรวมสถานการณ์การลงทุนวันนี้)

### 🔑 Key Signals วันนี้
🟢 **Bullish Factors:**
- (3 ข้อ)

🔴 **Bearish Factors:**
- (3 ข้อ)

🟡 **Wildcards / จับตา:**
- (2 ข้อ)

### 📊 Market Outlook
| ตลาด | แนวโน้ม | ระดับความเสี่ยง |
|------|---------|----------------|
| US Markets | | |
| Asian Markets | | |
| SET Index | | |
| Gold / Oil | | |
| Bitcoin | | |

### 💼 Investment Strategy วันนี้

**Conservative (เน้นปลอดภัย):**
- แนะนำ allocation และ action

**Moderate (สมดุล):**
- แนะนำ allocation และ action

**Aggressive (รับความเสี่ยงสูง):**
- แนะนำ allocation และ action

### ✅ Action Items (5 ข้อ)
1.
2.
3.
4.
5.

### ⚠️ Risk Warning
(ความเสี่ยงหลัก 2-3 ข้อที่ต้องระวังวันนี้)

---
*รายงานนี้เป็นข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน*"""

    try:
        res = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3500,
            system=CEO_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )
        text = res.content[0].text
        print(f"[👑] CEO report done ✓ ({len(text)} chars)")
        return text
    except Exception as e:
        print(f"[👑] CEO ERROR: {e}")
        return f"[CEO Error: {e}]"

# ─── EMAIL ────────────────────────────────────────────────────────────────────
def md_to_html(text: str) -> str:
    """Convert simple markdown to HTML."""
    text = re.sub(r"^### (.+)$", r"<h3 style='color:#1e3a5f;margin:16px 0 8px'>\1</h3>", text, flags=re.M)
    text = re.sub(r"^## (.+)$",  r"<h2 style='color:#1e3a5f;margin:20px 0 10px'>\1</h2>", text, flags=re.M)
    text = re.sub(r"^\| (.+) \|$", lambda m: f"<tr>{''.join(f'<td style=padding:6px 10px;border:1px solid #e5e7eb>{c.strip()}</td>' for c in m.group(1).split('|'))}</tr>", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"^- (.+)$", r"<li>\1</li>", text, flags=re.M)
    text = re.sub(r"(<li>.*</li>\n?)+", r"<ul style='margin:6px 0 6px 20px'>\g<0></ul>", text)
    text = re.sub(r"\n\n", "<br><br>", text)
    text = re.sub(r"\n", "<br>", text)
    return text

def build_email(ceo_report: str, agent_reports: dict, gdrive_url: str) -> tuple[str, str]:
    today = datetime.datetime.utcnow()
    bkk = today + datetime.timedelta(hours=7)
    date_str  = bkk.strftime("%d/%m/%Y")
    time_str  = bkk.strftime("%H:%M")

    ceo_html = md_to_html(ceo_report)

    # Agent preview cards
    cards = ""
    for key, report in agent_reports.items():
        m = AGENT_META[key]
        preview = report[:350].replace("\n", "<br>") + "..."
        cards += f"""
        <div style="border-left:4px solid #3b82f6;background:#f0f9ff;padding:12px 16px;margin:8px 0;border-radius:0 8px 8px 0">
          <strong style="font-size:14px">{m['emoji']} {m['name']}</strong><br>
          <span style="font-size:13px;color:#374151;line-height:1.6">{preview}</span>
        </div>"""

    drive_btn = ""
    if gdrive_url:
        drive_btn = f"""<div style="margin:20px 0">
          <a href="{gdrive_url}" style="background:#0f9d58;color:white;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:bold">
            📁 ดูรายงานฉบับเต็มใน Google Drive
          </a></div>"""

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body{{font-family:Arial,'Sarabun',sans-serif;max-width:680px;margin:0 auto;padding:20px;color:#111;line-height:1.6}}
  table{{border-collapse:collapse;width:100%;margin:10px 0}}
  td{{padding:6px 10px;border:1px solid #e5e7eb;font-size:13px}}
  tr:first-child td{{background:#dbeafe;font-weight:bold}}
</style></head><body>
  <div style="background:#1e3a5f;color:white;padding:20px 24px;border-radius:10px;margin-bottom:20px">
    <h1 style="margin:0;font-size:22px">🏦 Investment Intelligence Hub</h1>
    <p style="margin:6px 0 0;opacity:0.85">📅 Morning Briefing — {date_str} &nbsp;|&nbsp; 🕖 {time_str} (Bangkok)</p>
  </div>
  <div style="background:white;border:1px solid #e5e7eb;border-radius:10px;padding:20px;margin-bottom:20px">
    <h2 style="color:#1e3a5f;margin-top:0">👑 CEO Summary</h2>
    {ceo_html}
  </div>
  <div style="margin-bottom:20px">
    <h2 style="color:#1e3a5f">📋 Agent Reports (Preview)</h2>
    {cards}
  </div>
  {drive_btn}
  <div style="font-size:11px;color:#9ca3af;margin-top:20px;border-top:1px solid #e5e7eb;padding-top:12px">
    สร้างโดย Investment Intelligence Hub • Multi-Agent AI System<br>
    ⚠️ รายงานนี้เป็นข้อมูลเพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน
  </div>
</body></html>"""

    plain = f"Investment Intelligence Hub — Morning Briefing {date_str}\n\n{ceo_report}"
    return html, plain

def send_email(subject: str, html: str, plain: str):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_SENDER
        msg["To"]      = EMAIL_RECIPIENT
        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html,  "html",  "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(EMAIL_SENDER, EMAIL_PASSWORD)
            srv.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        print(f"[Email] Sent to {EMAIL_RECIPIENT} ✓")
    except Exception as e:
        print(f"[Email] ERROR: {e}")
        raise

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"☀️  Morning Briefing — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*55}")

    # 1. Load agent cache — try Drive first, fallback to local
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    cache = load_cache_from_drive(date_str)
    if not cache:
        local = Path("cache_latest.json")
        if local.exists():
            cache = json.loads(local.read_text(encoding="utf-8"))
            print("[Cache] Loaded from local file ✓")
        else:
            print("[!] No cache found — running quick research...")
            # Import and run evening research inline
            import evening_research as er
            er.main()
            cache = json.loads(Path("cache_latest.json").read_text(encoding="utf-8"))

    agent_reports = cache.get("reports", {})
    print(f"[Cache] Agents loaded: {list(agent_reports.keys())}")

    # 2. CEO synthesizes
    ceo_report = call_ceo(agent_reports)

    # 3. Build full briefing document
    bkk_date   = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d")
    full_doc   = f"# Investment Morning Briefing — {bkk_date}\n\n"
    full_doc  += ceo_report + "\n\n" + "=" * 60 + "\n# Agent Reports\n\n"
    for key, report in agent_reports.items():
        m = AGENT_META[key]
        full_doc += f"\n## {m['emoji']} {m['name']}\n{report}\n"

    # 4. Save full briefing to Drive
    gdrive_url = save_to_gdrive(full_doc, f"Briefing_{bkk_date}.txt")

    # 5. Send email
    html, plain = build_email(ceo_report, agent_reports, gdrive_url)
    bkk_date_th = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%d/%m/%Y")
    send_email(
        subject=f"📊 Investment Briefing {bkk_date_th} — AI Morning Report",
        html=html,
        plain=plain,
    )

    print(f"\n✅ Morning Briefing complete!")
    if gdrive_url:
        print(f"   Drive: {gdrive_url}")

if __name__ == "__main__":
    main()
    sys.exit(0)   # must exit for Railway cron
