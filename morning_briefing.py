"""
Morning Briefing Job — CEO (Agent 7) สรุป + Email + Save Drive แล้ว exit
Railway Cron: 0 0 * * *  (07:00 Bangkok = 00:00 UTC)
Email: ภาษาไทย ความยาวไม่เกิน 1 หน้า A4
"""
import anthropic
import json
import datetime
import os
import sys
import re
import time
import base64
import io
import urllib.request
import urllib.error
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload, MediaIoBaseDownload

# ─── CONFIG ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
RESEND_API_KEY    = os.environ["RESEND_API_KEY"]
EMAIL_RECIPIENT   = os.environ["EMAIL_RECIPIENT"]
GDRIVE_FOLDER_ID  = os.environ.get("GDRIVE_FOLDER_ID", "")
GDRIVE_TOKEN_JSON = os.environ.get("GDRIVE_TOKEN_JSON", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

AGENT_META = {
    "news":      {"emoji": "📰", "name": "Agent 1 — News Researcher"},
    "broker":    {"emoji": "📊", "name": "Agent 2 — Broker"},
    "technical": {"emoji": "📈", "name": "Agent 3 — Technical"},
    "macro":     {"emoji": "🌐", "name": "Agent 4 — Macro"},
    "portfolio": {"emoji": "💰", "name": "Agent 5 — Portfolio"},
    "council":   {"emoji": "🧠", "name": "Agent 6 — Elite Council"},
}

# ─── GOOGLE DRIVE ─────────────────────────────────────────────────────────────
GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_gdrive_service():
    if not GDRIVE_TOKEN_JSON:
        return None
    try:
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

# ─── CEO AGENT 7 ──────────────────────────────────────────────────────────────
CEO_SYSTEM = """คุณคือ CEO และ Final Decision Maker ของทีมวิเคราะห์การลงทุนระดับสถาบัน
คุณได้รับรายงานจาก 6 ผู้เชี่ยวชาญ และต้องสังเคราะห์เป็น Morning Briefing ภาษาไทย
ที่มีความยาวพอดี 1 หน้า A4 (ประมาณ 400-500 คำ)
คุณต้องเป็นกลาง ใช้ความน่าจะเป็น ไม่รับประกันผลลัพธ์
อธิบายเหตุผลให้ชัดเจนเสมอ"""

def call_ceo(agent_reports: dict) -> str:
    print("[🎯] CEO (Agent 7) synthesizing all reports...")
    sections = ""
    for key, report in agent_reports.items():
        m = AGENT_META.get(key, {"emoji": "•", "name": key})
        # ตัดให้เหลือแค่ 800 chars ต่อ agent เพื่อประหยัด memory
        short = report[:800] + "..." if len(report) > 800 else report
        sections += f"\n\n{'─'*40}\n{m['emoji']} {m['name']}\n{'─'*40}\n{short}"

    bkk = (datetime.datetime.utcnow() + datetime.timedelta(hours=7))
    bkk_date = bkk.strftime("%d %B %Y")

    prompt = f"""คุณได้รับรายงานจาก 6 ผู้เชี่ยวชาญ:{sections}

---
กรุณาสร้าง CEO Morning Briefing ภาษาไทย ความยาวไม่เกิน 1 หน้า A4
ใช้รูปแบบนี้ (กระชับ ตรงประเด็น):

## 🎯 Morning Briefing — {bkk_date}

### 📌 สรุปภาพรวม
(2-3 ประโยค สถานการณ์ S&P500 และ Bitcoin วันนี้)

### 🔑 สัญญาณสำคัญ
🟢 Bullish: (2 ข้อสั้น)
🔴 Bearish: (2 ข้อสั้น)
🟡 จับตา: (1 ข้อ)

### 📊 แนวโน้มตลาด
| | S&P500 | Bitcoin |
|---|---|---|
| Short-term | | |
| Mid-term | | |
| Trend | | |

### 💼 แนะนำพอร์ต
| | Conservative | Moderate | Aggressive |
|---|---|---|---|
| S&P500 | | | |
| Bitcoin | | | |
| Gold | | | |
| Cash | | | |

### ✅ Action Plan (3 ข้อ)
1.
2.
3.

### ⚠️ ความเสี่ยงหลัก
(1-2 ข้อที่ต้องระวังที่สุด)

### 🎯 Final Decision
**BUY / HOLD / SELL** — (เหตุผล 1 ประโยค)
Risk Score: X/10 | Confidence: X/10

---
*ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน*"""

    try:
        res = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=CEO_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )
        text = res.content[0].text
        print(f"[🎯] CEO report done ✓ ({len(text)} chars)")
        return text
    except Exception as e:
        print(f"[🎯] CEO ERROR: {e}")
        return f"[CEO Error: {e}]"

# ─── EMAIL ────────────────────────────────────────────────────────────────────
def md_to_html(text: str) -> str:
    text = re.sub(r"^### (.+)$", r"<h3 style='color:#1e3a5f;margin:14px 0 6px;font-size:14px'>\1</h3>", text, flags=re.M)
    text = re.sub(r"^## (.+)$",  r"<h2 style='color:#1e3a5f;margin:16px 0 8px;font-size:16px'>\1</h2>", text, flags=re.M)
    text = re.sub(r"^\| (.+) \|$", lambda m: "<tr>" + "".join(
        f"<td style='padding:5px 10px;border:1px solid #e5e7eb;font-size:12px'>{c.strip()}</td>"
        for c in m.group(1).split("|")) + "</tr>", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"^[-•] (.+)$", r"<li style='margin:3px 0'>\1</li>", text, flags=re.M)
    text = re.sub(r"(<li.*</li>\n?)+", r"<ul style='margin:6px 0 6px 18px;padding:0'>\g<0></ul>", text)
    text = re.sub(r"\n\n", "<br>", text)
    text = re.sub(r"\n", "<br>", text)
    return text

def build_email(ceo_report: str, gdrive_url: str) -> tuple[str, str]:
    bkk   = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    date_str = bkk.strftime("%d/%m/%Y")
    time_str = bkk.strftime("%H:%M")
    ceo_html = md_to_html(ceo_report)

    drive_btn = ""
    if gdrive_url:
        drive_btn = f"""<div style="margin:16px 0">
          <a href="{gdrive_url}" style="background:#0f9d58;color:white;padding:8px 18px;
          border-radius:6px;text-decoration:none;font-size:13px;font-weight:bold">
            📁 ดูรายงานฉบับเต็มใน Google Drive
          </a></div>"""

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body{{font-family:Arial,'Sarabun',sans-serif;max-width:640px;margin:0 auto;
       padding:16px;color:#111;line-height:1.6;font-size:13px}}
  table{{border-collapse:collapse;width:100%;margin:8px 0}}
  td{{padding:5px 10px;border:1px solid #e5e7eb;font-size:12px}}
  tr:first-child td{{background:#dbeafe;font-weight:bold;font-size:12px}}
</style></head><body>
  <div style="background:#1e3a5f;color:white;padding:16px 20px;border-radius:8px;margin-bottom:16px">
    <div style="font-size:18px;font-weight:bold">🏦 Investment Intelligence Hub</div>
    <div style="font-size:12px;opacity:0.85;margin-top:4px">
      📅 {date_str} &nbsp;|&nbsp; 🕖 {time_str} Bangkok &nbsp;|&nbsp;
      🎯 Focus: S&P500 + Bitcoin
    </div>
  </div>
  <div style="background:white;border:1px solid #e5e7eb;border-radius:8px;padding:16px">
    {ceo_html}
  </div>
  {drive_btn}
  <div style="font-size:11px;color:#9ca3af;margin-top:12px;border-top:1px solid #e5e7eb;padding-top:10px">
    สร้างโดย Investment Intelligence Hub • 7-Agent AI System<br>
    ⚠️ เพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน
  </div>
</body></html>"""

    plain = f"Investment Intelligence Hub — {date_str}\n\n{ceo_report}"
    return html, plain

def send_email(subject: str, html: str, plain: str):
    try:
        payload = json.dumps({
            "from": "Investment Hub <onboarding@resend.dev>",
            "to": [EMAIL_RECIPIENT],
            "subject": subject,
            "html": html,
            "text": plain,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            print(f"[Email] Sent via Resend ✓ id={result.get('id', '?')}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"[Email] Resend ERROR {e.code}: {body}")
        raise
    except Exception as e:
        print(f"[Email] ERROR: {e}")
        raise

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*55}")
    print(f"☀️  Morning Briefing — {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")
    print(f"{'='*55}")

    # Load cache
    date_str = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    cache = load_cache_from_drive(date_str)
    if not cache:
        local = Path("cache_latest.json")
        if local.exists():
            cache = json.loads(local.read_text(encoding="utf-8"))
            print("[Cache] Loaded from local file ✓")
        else:
            print("[!] No cache — running quick research...")
            import evening_research as er
            er.main()
            cache = json.loads(Path("cache_latest.json").read_text(encoding="utf-8"))

    agent_reports = cache.get("reports", {})
    print(f"[Cache] Agents loaded: {list(agent_reports.keys())}")

    # CEO synthesizes
    ceo_report = call_ceo(agent_reports)

    # Build full document for Drive
    bkk_date = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d")
    full_doc  = f"# Investment Morning Briefing — {bkk_date}\n\n{ceo_report}\n\n"
    full_doc += "=" * 50 + "\n# Agent Reports\n\n"
    for key, report in agent_reports.items():
        m = AGENT_META.get(key, {"emoji": "•", "name": key})
        full_doc += f"\n## {m['emoji']} {m['name']}\n{report}\n"

    gdrive_url = save_to_gdrive(full_doc, f"Briefing_{bkk_date}.txt")

    # Send email
    bkk_date_th = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%d/%m/%Y")
    html, plain = build_email(ceo_report, gdrive_url)
    send_email(
        subject=f"📊 Investment Briefing {bkk_date_th} | S&P500 + Bitcoin",
        html=html,
        plain=plain,
    )

    print(f"\n✅ Morning Briefing complete!")
    if gdrive_url:
        print(f"   Drive: {gdrive_url}")

if __name__ == "__main__":
    main()
    sys.exit(0)
