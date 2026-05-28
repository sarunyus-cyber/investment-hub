"""
Investment Intelligence Hub — All-in-One
รัน Agents 1-6 ค้นข้อมูล → CEO สรุป → ส่ง Email via Gmail API → บันทึก Drive
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
import email.mime.text
import email.mime.multipart
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload

# ─── CONFIG ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
EMAIL_RECIPIENT   = os.environ.get("EMAIL_RECIPIENT", "")
EMAIL_SENDER      = os.environ.get("EMAIL_SENDER", "")
GDRIVE_FOLDER_ID  = os.environ.get("GDRIVE_FOLDER_ID", "")
GDRIVE_TOKEN_JSON = os.environ.get("GDRIVE_TOKEN_JSON", "")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

GLOBAL_RULES = """
GLOBAL RULES:
- Focus: S&P500 and Bitcoin
- Confidence Score (1-10) and Risk Score (1-10)
- Short-term / Mid-term / Long-term
- Consider: Fed, Interest rates, Inflation, GDP, Geopolitics, Earnings, ETF flows
"""

AGENTS = {
    "news": {
        "emoji": "\U0001f4f0", "name": "Agent 1 \u2014 News Researcher",
        "system": "You are a world-class financial journalist focused on S&P500 and Bitcoin.\n" + GLOBAL_RULES,
        "prompt": "Report top 3-5 news impacting S&P500 and Bitcoin today with Bullish/Bearish factors and Confidence Score"
    },
    "broker": {
        "emoji": "\U0001f4ca", "name": "Agent 2 \u2014 Broker",
        "system": "You are an institutional cross-market strategist analyzing Fund Flow and Sentiment.\n" + GLOBAL_RULES,
        "prompt": "Analyze S&P500, Nasdaq, Bitcoin, Ethereum, Gold, Oil, Bonds, USD \u2014 Sector Rotation, Institutional Flow, Risk-On/Off with Confidence Score"
    },
    "technical": {
        "emoji": "\U0001f4c8", "name": "Agent 3 \u2014 Technical",
        "system": "You are an elite technical analyst for S&P500 and Bitcoin.\n" + GLOBAL_RULES,
        "prompt": "Technical analysis of S&P500 and Bitcoin: Support/Resistance, RSI, MACD, EMA, Trend, BUY/SELL/NEUTRAL with Confidence Score"
    },
    "macro": {
        "emoji": "\U0001f310", "name": "Agent 4 \u2014 Macro",
        "system": "You are a world-class macroeconomic strategist.\n" + GLOBAL_RULES,
        "prompt": "Evaluate Economic Cycle, Bubble Risk, Recession Probability, Liquidity, compare to 2008/COVID with Confidence Score"
    },
    "portfolio": {
        "emoji": "\U0001f4b0", "name": "Agent 5 \u2014 Portfolio",
        "system": "You are a professional portfolio manager for S&P500/Bitcoin/Gold/Bonds/Cash.\n" + GLOBAL_RULES,
        "prompt": "Portfolio Allocation for Conservative/Moderate/Aggressive, Risk Level, Buy/Hold/Sell with Confidence Score"
    },
    "council": {
        "emoji": "\U0001f9e0", "name": "Agent 6 \u2014 Elite Council",
        "system": "You simulate Buffett, Musk, Bezos, Jensen Huang. Challenge weak assumptions.\n" + GLOBAL_RULES,
        "prompt": "Strategic Insights, Opportunities, Risks, Contrarian Perspectives, What Smart Money May Be Doing with Confidence Score"
    },
}

AGENT_META = {k: {"emoji": v["emoji"], "name": v["name"]} for k, v in AGENTS.items()}

# ─── GOOGLE SERVICES ──────────────────────────────────────────────────────────
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/gmail.send",
]

def get_google_creds():
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
            scopes=GOOGLE_SCOPES,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds
    except Exception as e:
        print(f"[Google] Auth error: {e}")
        return None

def get_gdrive_service():
    creds = get_google_creds()
    if not creds:
        return None
    return build("drive", "v3", credentials=creds)

def get_gmail_service():
    creds = get_google_creds()
    if not creds:
        return None
    return build("gmail", "v1", credentials=creds)

def save_to_gdrive(content, filename):
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
        print(f"[Drive] Saved {filename}")
        return url
    except Exception as e:
        print(f"[Drive] Save error: {e}")
        return ""

# ─── RUN AGENT ────────────────────────────────────────────────────────────────
def run_agent(key):
    a = AGENTS[key]
    print(f"[{a['emoji']}] Running {a['name']}...")
    try:
        res = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            system=a["system"],
            messages=[{"role": "user", "content": a["prompt"] + f"\nDate: {datetime.datetime.utcnow().strftime('%d/%m/%Y')} UTC"}]
        )
        text = res.content[0].text
        print(f"[{a['emoji']}] Done ({len(text)} chars)")
        return text
    except Exception as e:
        print(f"[{a['emoji']}] ERROR: {e}")
        return f"[Error: {e}]"

# ─── CEO ──────────────────────────────────────────────────────────────────────
def call_ceo(agent_reports):
    print("[CEO] Synthesizing...")
    sections = ""
    for key, report in agent_reports.items():
        m = AGENT_META.get(key, {"emoji": "-", "name": key})
        short = report[:400] if len(report) > 400 else report
        sections += f"\n{m['emoji']} {m['name']}: {short}\n"

    bkk = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    bkk_date = bkk.strftime("%d %B %Y")

    prompt = f"""Summarize as Thai-language Morning Briefing, max 1 A4 page, from reports:{sections}

Format:
## Morning Briefing {bkk_date}
### Summary (2 sentences)
### Bullish (2) / Bearish (2) / Watch (1)
### Portfolio (Conservative/Moderate/Aggressive table)
### Action Plan (3 items)
### Final Decision: BUY/HOLD/SELL + Risk + Confidence
Write in Thai. End with disclaimer."""

    try:
        res = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system="You are a CEO summarizing investment reports in Thai, concise, max 1 A4 page.",
            messages=[{"role": "user", "content": prompt}]
        )
        text = res.content[0].text
        print(f"[CEO] Done ({len(text)} chars)")
        return text
    except Exception as e:
        print(f"[CEO] ERROR: {e}")
        return f"[CEO Error: {e}]"

# ─── EMAIL via Gmail API ──────────────────────────────────────────────────────
def md_to_html(text):
    text = re.sub(r"^### (.+)$", r"<h3 style='color:#1e3a5f;margin:14px 0 6px;font-size:14px'>\1</h3>", text, flags=re.M)
    text = re.sub(r"^## (.+)$", r"<h2 style='color:#1e3a5f;margin:16px 0 8px;font-size:16px'>\1</h2>", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = text.replace("\n", "<br>")
    return text

def send_email(subject, ceo_report, gdrive_url):
    if not EMAIL_RECIPIENT:
        print("[Email] Skipped - no EMAIL_RECIPIENT")
        return

    gmail = get_gmail_service()
    if not gmail:
        print("[Email] Skipped - Gmail auth failed")
        return

    bkk = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    date_str = bkk.strftime("%d/%m/%Y")
    ceo_html = md_to_html(ceo_report)

    drive_link = ""
    if gdrive_url:
        drive_link = f'<br><a href="{gdrive_url}" style="background:#0f9d58;color:white;padding:8px 18px;border-radius:6px;text-decoration:none;font-size:13px">Full Report on Drive</a>'

    html_body = f"""<div style="font-family:Arial;max-width:640px;margin:0 auto;font-size:13px;color:#111;line-height:1.6">
<div style="background:#1e3a5f;color:white;padding:16px 20px;border-radius:8px">
<div style="font-size:18px;font-weight:bold">Investment Intelligence Hub</div>
<div style="font-size:12px;opacity:0.85;margin-top:4px">{date_str} | S&P500 + Bitcoin</div>
</div>
<div style="padding:16px">{ceo_html}</div>
{drive_link}
<div style="font-size:11px;color:#9ca3af;margin-top:12px;border-top:1px solid #e5e7eb;padding-top:10px">
For educational purposes only, not investment advice.</div></div>"""

    msg = email.mime.multipart.MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER or "me"
    msg["To"] = EMAIL_RECIPIENT
    msg.attach(email.mime.text.MIMEText(ceo_report, "plain", "utf-8"))
    msg.attach(email.mime.text.MIMEText(html_body, "html", "utf-8"))

    raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    try:
        gmail.users().messages().send(userId="me", body={"raw": raw_msg}).execute()
        print(f"[Email] Sent via Gmail API -> {EMAIL_RECIPIENT}")
    except Exception as e:
        print(f"[Email] Gmail ERROR: {e}")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    bkk = datetime.datetime.utcnow() + datetime.timedelta(hours=7)
    print(f"\n{'='*55}")
    print(f"Investment Hub - {bkk.strftime('%Y-%m-%d %H:%M')} Bangkok")
    print(f"{'='*55}")

    # Phase 1: Agents
    print("\nPhase 1: Agent Research...")
    reports = {}
    for key in AGENTS:
        reports[key] = run_agent(key)
        time.sleep(2)

    date_str = bkk.strftime("%Y-%m-%d")
    cache = json.dumps({"research_date": datetime.datetime.utcnow().isoformat(), "reports": reports}, ensure_ascii=False, indent=2)
    save_to_gdrive(cache, f"agent_cache_{date_str}.json")

    # Phase 2: CEO
    print("\nPhase 2: CEO Briefing...")
    ceo_report = call_ceo(reports)

    full_doc = f"# Investment Briefing - {date_str}\n\n{ceo_report}\n\n{'='*50}\n# Agent Reports\n"
    for key, report in reports.items():
        m = AGENT_META.get(key, {"emoji": "-", "name": key})
        full_doc += f"\n## {m['emoji']} {m['name']}\n{report}\n"
    gdrive_url = save_to_gdrive(full_doc, f"Briefing_{date_str}.txt")

    # Phase 3: Email
    print("\nPhase 3: Email...")
    send_email(f"Investment Briefing {bkk.strftime('%d/%m/%Y')} | S&P500 + Bitcoin", ceo_report, gdrive_url)

    print(f"\nAll done!")

if __name__ == "__main__":
    main()
    sys.exit(0)
