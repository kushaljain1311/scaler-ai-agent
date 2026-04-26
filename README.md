# Scaler AI BDA Agent

AI-powered sales agent for Scaler's BDA team. Generates personalised pre-call WhatsApp nudges for BDAs and post-call PDF overviews for leads.

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Backend | Python FastAPI |
| AI | OpenAI GPT-4o + Whisper |
| WhatsApp | Twilio WhatsApp Sandbox |
| PDF | WeasyPrint |

---

## Setup

### 1. Clone / navigate to project

```bash
cd scaler-ai-agent
```

### 2. Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate
# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Fill in `backend/.env`:

```
OPENAI_API_KEY=        # https://platform.openai.com/api-keys
TWILIO_ACCOUNT_SID=    # https://console.twilio.com → Account Info
TWILIO_AUTH_TOKEN=     # https://console.twilio.com → Account Info
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
BACKEND_URL=http://localhost:8000
```

**WeasyPrint on Windows** also requires GTK. Download and install from:
https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases

Start backend:

```bash
uvicorn main:app --reload
```

### 3. Frontend

```bash
cd frontend
npm install
```

Fill in `frontend/.env.local` (already set to localhost:8000).

Start frontend:

```bash
npm run dev
```

---

## Twilio WhatsApp Sandbox setup

1. Go to https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn
2. Note the sandbox number: **+1 415 523 8886** and the join keyword shown
3. From the BDA's WhatsApp, send: `join <keyword>` to **+14155238886**
4. From the lead's WhatsApp (for PDF send), do the same
5. You'll get a confirmation reply — the number is now opted in

---

## Verify everything works

```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status":"ok","model":"gpt-4o","timestamp":"..."}

# Frontend
open http://localhost:3000
```

### Manual test checklist

- [ ] Health endpoint returns `{"status": "ok"}`
- [ ] Frontend loads at localhost:3000
- [ ] BDA phone validation rejects numbers without `+`
- [ ] Persona quick-load fills all fields correctly
- [ ] Audio toggle shows drag-and-drop zone
- [ ] Run Agent button disabled when fields are empty
- [ ] Progress steps animate correctly during run
- [ ] Nudge sent panel shows green with full nudge text
- [ ] PDF preview shows headline, sections, verified badges
- [ ] Edit mode makes all PDF fields editable inline
- [ ] Download PDF button downloads a valid PDF
- [ ] Approve & Send disabled without lead phone, tooltip visible
- [ ] Skip button resets to input screen
- [ ] Backend-down error shows helpful message

---

## Project structure

```
scaler-ai-agent/
├── frontend/
│   ├── app/
│   │   ├── page.tsx        # Full UI (single client component)
│   │   ├── layout.tsx
│   │   └── globals.css
│   ├── .env.local
│   └── package.json
│
├── backend/
│   ├── main.py             # FastAPI routes
│   ├── prompts.py          # All OpenAI prompts
│   ├── pdf_generator.py    # WeasyPrint HTML→PDF
│   ├── whatsapp.py         # Twilio send functions
│   ├── static/             # Served PDFs (auto-created)
│   ├── requirements.txt
│   └── .env
│
└── README.md
```
