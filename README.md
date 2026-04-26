# Scaler AI BDA Agent

**Live app:** https://scaler-ai-agent-uewqnofpet9xvkgggzxqrf.streamlit.app/  
**Loom demo:** https://www.loom.com/share/07aaeaf09389491b80e3d0e8da8522a0

---

## What I built

An AI agent that supercharges two drop-off moments in Scaler's sales funnel. Before a call, it sends the BDA a scannable WhatsApp brief — not a script, but a strategy: who this person really is, what discovery questions to ask, which objections to expect (extracted only from the actual transcript, not invented), and one thing to avoid. After the call, it generates a 2–3 page personalised PDF that answers each question the lead actually asked, with ROI reasoning and verified Scaler facts — no hallucinated curriculum claims. The PDF is colour-coded by experience level (orange for freshers, blue for mid-level, purple for senior), routed through a BDA approval gate (Approve / Edit / Skip), and delivered to the lead's WhatsApp via Twilio. Both structured transcript and audio input (Whisper transcription) are supported. Built with FastAPI (Python backend) and Streamlit (frontend), deployed on Streamlit Cloud.

---

## One failure I found

When the lead's transcript is very short or vague — under 5 exchanges — the question extractor sometimes returns only 1 question where 2–3 were implied. The PDF then has a single section, which feels thin. Root cause: the extraction prompt relies on explicit phrasing; subtext doesn't reliably surface. Fix would be a second-pass inference prompt.

---

## Scale plan

At 100,000 leads/month the first thing that breaks is **PDF generation latency** — xhtml2pdf is synchronous and CPU-bound, so concurrent requests will queue and time out under load. Fix: move PDF generation to a task queue (Celery + Redis) with async workers, and cache identical persona-type outputs for ~1 hour. Second constraint is **Twilio WhatsApp throughput** — the sandbox has strict rate limits and production WhatsApp Business API requires Meta approval with a 3–7 day review cycle. Both are solvable but need lead time before scale.

---

## PDF delivery note

WhatsApp PDF delivery requires a **publicly accessible URL** for the media attachment. On the deployed Streamlit app, PDFs are hosted at:

```
https://[your-streamlit-url]/static/[filename].pdf
```

If the Twilio send fails during your review, the PDF download link is visible directly in the UI as a fallback — click to download, then forward manually. This is a hosting constraint, not a logic one.

---

## Stack

| Layer | Tool |
|---|---|
| Frontend | Streamlit |
| Backend | FastAPI (Python) |
| AI — text | OpenAI GPT-4o |
| AI — audio | OpenAI Whisper |
| PDF | xhtml2pdf |
| WhatsApp | Twilio Sandbox |
| Deploy | Streamlit Cloud |

---

## Running locally

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
streamlit run app.py
```

**Environment variables — create `backend/.env`:**
```
OPENAI_API_KEY=sk-...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
BACKEND_URL=http://localhost:8000
```

**Twilio sandbox opt-in:**  
Send `join <your-keyword>` from your WhatsApp to `+14155238886`.  
Both the BDA number and the lead test number must opt in before sending.

---

## Decisions made

- **Objections in nudge = transcript-only.** If the lead didn't say it, it's not listed. Invented objections make the BDA sound like they're reading a generic script.
- **PDF sections = questions asked, not questions we wish they'd asked.** One section per extracted question, no more.
- **Anti-hallucination by design.** All curriculum facts are grounded in a static verified knowledge base. If a fact isn't in the KB, the PDF says "confirm on scaler.com" rather than inventing.
- **Tone shifts by YoE.** Meera (0 YoE) gets courage and parent-friendly framing. Rohan (4 YoE) gets ROI math. Karthik (9 YoE) gets peer-level respect, no fluff.
