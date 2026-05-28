"""
Investment Intelligence Hub — All-in-One
รัน Agents 1-6 ค้นข้อมูล → CEO สรุป → ส่ง Email → บันทึก Drive
Railway Cron: 0 14 * * *  (21:00 Bangkok = 14:00 UTC)
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
from googleapiclient.http import MediaInMemoryUpload

# ─── CONFIG ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
RESEND_API_KEY    = os.environ.get("RESEND_API_KEY", "")
EMAIL_RECIPIENT   = os.environ.get("EMAIL_RECIPIENT", "")
GDRIVE_FOLDER_ID  = os.environ.get("GDRIVE_FOLDER_ID", "")
GDRIVE_TOKEN_JSON = os.environ.get("GDRIVE_TOKEN_JSON", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

GLOBAL_RULES = """
GLOBAL RULES:
- Focus: S&P500 และ Bitcoin
- แยกข้อเท็จจริงจากความเห็น
- ระบุ Confidence Score (1-10)
- ระบุ Risk Score (1-10)
- แยก Short-term / Mid-term / Long-term
- คำนึงถึง: Fed, ดอกเบี้ย, Inflation, GDP, Geopolitics, Earnings, ETF flows
"""

AGENTS = {
    "news": {
        "emoji": "📰", "name": "Agent 1 — News Researcher",
        "system": f"คุณคือนักข่าวการเงินระดับโลก ค้นหาข่าวที่กระทบ S&P500 และ Bitcoin\n{GLOBAL_RULES}",
        "prompt": "รายงานข่าวสำคัญ 3-5 ข่าวที่กระทบ S&P500 และ Bitcoin มากที่สุดวันนี้ พร้อม Bullish/Bearish factors และ Confidence Score"
    },
    "broker": {
        "emoji": "📊", "name": "Agent 2 — Broker",
        "system": f"คุณคือนักกลยุทธ์ตลาดระดับสถาบัน วิเคราะห์ Fund Flow และ Sentiment\n{GLOBAL_RULES}",
        "prompt": "วิเคราะห์ S&P500, Nasdaq, Bitcoin, Ethereum, Gold, Oil, Bonds, USD — Sector Rotation, Institutional Flow, Risk-On/Off พร้อม Confidence Score"
    },
    "technical": {
        "emoji": "📈", "name": "Agent 3 — Technical",
        "system": f"คุณคือ Technical Analyst ระดับสถาบัน วิเคราะห์กราฟ S&P500 และ Bitcoin\n{GLOBAL_RULES}",
        "prompt": "วิเคราะห์ Technical ของ S&P500 และ Bitcoin: Support/Resistance, RSI, MACD, EMA, Trend Direction, สรุป BUY/SELL/NEUTRAL พร้อม Confidence Score"
    },
    "macro": {
        "emoji": "🌐", "name": "Agent 4 — Macro",
        "system": f"คุณคือนักกลยุทธ์เศรษฐกิจมหภาค ประเมินสภาพเศรษฐกิจโลก\n{GLOBAL_RULES}",
        "prompt": "ประเมิน Economic Cycle, Bubble Risk, Recession Probability, Liquidity, เปรียบกับ 2008/COVID พร้อม Confidence Score"
    },
    "portfolio": {
        "emoji": "💰", "name": "Agent 5 — Portfolio",
        "system": f"คุณคือผู้จัดการพอร์ตมืออาชีพ จัดสรร S&P500/Bitcoin/Gold/Bonds/Cash\n{GLOBAL_RULES}",
        "prompt": "แนะนำ Portfolio Allocation แยก Conservative/Moderate/Aggressive, Risk Level, Rebalancing, Buy/Hold/Sell พร้อม Confidence Score"
    },
    "council": {
        "emoji": "🧠", "name": "Agent 6 — Elite Council",
        "system": f"คุณจำลองแนวคิด Buffett, Musk, Bezos, Jensen Huang วิเคราะห์เชิงกลยุทธ์\n{GLOBAL_RULES}\nห้ามเห็นด้วยกับ Agent อื่นอย่างไม่มีเหตุผล",
        "prompt": "วิเคราะห์ Strategic Insights, Opportunities, Risks, Contrarian Perspectives, What Smart Money May Be Doing พร้อม Confidence Score"
    },
}

AGENT_META = {k: {"emoji": v["emoji"], "name": v["name"]} for k, v in AGENTS.items()}

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

# ─── RUN AGENT ────────────────────────────────────────────────────────────────
def run_agent(key: str) -> str:
    a = AGENTS[key]
    print(f"[{a['emoji']}] Running {a['name']}...")
    try:
        res = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            system=a["system"],
            messages=[{"role": "user", "content": a["prompt"] + f"\nวันที่: {datetime.datetime.utcnow().strftime('%d/%m/%Y')} UTC"}]
        )
        text = res.content[0].text
        print(f"[{a['emoji']}] Done ✓ ({len(text)} chars)")
        return text
    except Exception as e:
        print(f"[{a['emoji']}] ERROR: {e}")
        return f"[Error: {e}]"

# ─── CEO ──────────────────────────────────────────────────────────────────────
def call_ceo(agent_reports: dict) -> str:
    print("[🎯] CEO (Agent 7) synthesizing...")
    sections = ""
    for key, report in agent_reports.items():
        m = AGENT_META.get(key, {"emoji": "•", "name": key})
        short = report[:400] if len(report) > 400 else report
        sections += f"\n{m['emoji']} {m['name']}: {short}\n"

    bkk = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    bkk_date = bkk.strftime("%d %B %Y")

    prompt = f"""สรุป Morning Briefing ภาษาไทย ไม่เกิน 1 หน้า A4 จากรายงาน:{sections}

## 🎯 Morning Briefing — {bkk_date}
### 📌 สรุปภาพรวม (2 ประโยค)
### 🔑 Bullish 🟢 (2 ข้อ) / Bearish 🔴 (2 ข้อ) / จับตา 🟡 (1 ข้อ)
### 💼 แนะนำพอร์ต (ตาราง Conservative/Moderate/Aggressive)
### ✅ Action Plan (3 ข้อ)
### 🎯 Final Decision: BUY/HOLD/SELL + Risk Score + Confidence
*ข้อมูลเพื่อการศึกษา ไม่ใช่คำแนะนำการลงทุน*"""

    try:
        res = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system="คุณคือ CEO สรุปรายงานการลงทุนเป็นภาษาไทย กระชับ ไม่เกิน 1 หน้า A4",
            messages=[{"role": "user", "content": prompt}]
        )
        text = res.content[0].text
        print(f"[🎯] CEO done ✓ ({len(text)} chars)")
        return text
    except Exception as e:
        print(f"[🎯] CEO ERROR: {e}")
        return f"[CEO Error: {e}]"

# ─── EMAIL ────────────────────────────────────────────────────────────────────
def md_to_html(text: str) -> str:
    text = re.sub(r"^### (.+)$", r"<h3 style='color:#1e3a5f;margin:14px 0 6px;font-size:14px'>\1</h3>", text, flags=re.M)
    text = re.sub(r"^## (.+)$", r"<h2 style='color:#1e3a5f;margin:16px 0 8px;font-size:16px'>\1</h2>", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = text.replace("\n", "<br>")
    return text

def send_email(subject: str, ceo_report: str, gdrive_url: str):
    if not RESEND_API_KEY or not EMAIL_RECIPIENT:
        print("[Email] Skipped — no RESEND_API_KEY or EMAIL_RECIPIENT")
        return
    bkk = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    date_str = bkk.strftime("%d/%m/%Y")
    ceo_html = md_to_html(ceo_report)
    drive_btn = f'<br><a href="{gdrive_url}" style="background:#0f9d58;color:white;padding:8px 18px;border-radius:6px;text-decoration:none;font-size:13px">📁 รายงานฉบับเต็ม</a>' if gdrive_url else ""

    html = f"""<div style="font-family:Arial;max-width:640px;margin:0 auto;font-size:13px;color:#111;line-height:1.6">
<div style="background:#1e3a5f;color:white;padding:16px 20px;border-radius:8px">
<div style="font-size:18px;font-weight:bold">🏦 Investment Intelligence Hub</div>
<div style="font-size:12px;opacity:0.85;margin-top:4px">📅 {date_str} | 🎯 S&P500 + Bitcoin</div>
</div>
<div style="padding:16px">{ceo_html}</div>
{drive_btn}
<div style="font-size:11px;color:#9ca3af;margin-top:12px;border-top:1px solid #e5e7eb;padding-top:10px">
⚠️ เพื่อการศึกษาเท่านั้น ไม่ใช่คำแนะนำการลงทุน</div></div>"""

    try:
        payload = json.dumps({
            "from": "Investment Hub <onboarding@resend.dev>",
            "to": [EMAIL_RECIPIENT],
            "subject": subject,
            "html": html,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            print(f"[Email] Sent ✓ id={result.get('id', '?')}")
    except Exception as e:
        print(f"[Email] ERROR: {e}")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    bkk = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    print(f"\n{'='*55}")
    print(f"🏦 Investment Hub — {bkk.strftime('%Y-%m-%d %H:%M')} Bangkok")
    print(f"{'='*55}")

    # Step 1: Run all agents
    print("\n📡 Phase 1: Agent Research...")
    reports = {}
    for key in AGENTS:
        reports[key] = run_agent(key)
        time.sleep(2)

    # Step 2: Save agent cache to Drive
    date_str = bkk.strftime("%Y-%m-%d")
    cache_payload = json.dumps({"research_date": datetime.datetime.utcnow().isoformat(), "reports": reports}, ensure_ascii=False, indent=2)
    save_to_gdrive(cache_payload, f"agent_cache_{date_str}.json")

    # Step 3: CEO synthesizes
    print("\n👑 Phase 2: CEO Briefing...")
    ceo_report = call_ceo(reports)

    # Step 4: Save briefing to Drive
    full_doc = f"# Investment Briefing — {date_str}\n\n{ceo_report}\n\n{'='*50}\n# Agent Reports\n"
    for key, report in reports.items():
        m = AGENT_META.get(key, {"emoji": "•", "name": key})
        full_doc += f"\n## {m['emoji']} {m['name']}\n{report}\n"
    gdrive_url = save_to_gdrive(full_doc, f"Briefing_{date_str}.txt")

    # Step 5: Send email
    print("\n📧 Phase 3: Email...")
    bkk_date_th = bkk.strftime("%d/%m/%Y")
    send_email(f"📊 Investment Briefing {bkk_date_th} | S&P500 + Bitcoin", ceo_report, gdrive_url)

    print(f"\n✅ All done!")

if __name__ == "__main__":
    main()
    sys.exit(0)
