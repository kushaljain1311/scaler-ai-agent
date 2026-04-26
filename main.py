import asyncio
import base64
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from fastapi.responses import FileResponse

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI, RateLimitError
from pydantic import BaseModel
from twilio.base.exceptions import TwilioRestException

import pdf_generator
import prompts
import whatsapp

load_dotenv()

app = FastAPI(title="Scaler AI BDA Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# ── Pydantic models ────────────────────────────────────────────────────────────

class LeadProfile(BaseModel):
    name: str
    role: str
    company: str
    yoe: int
    intent: str
    education: str | None = None
    salary: str | None = None


class NudgeRequest(BaseModel):
    lead: LeadProfile
    transcript: str
    bda_phone: str


class GeneratePDFRequest(BaseModel):
    lead: LeadProfile
    transcript: str


class SendToLeadRequest(BaseModel):
    lead: LeadProfile
    pdf_content: dict
    whatsapp_message: str
    lead_phone: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _clean_json(raw: str) -> str:
    """Strip markdown fences and extract the outermost JSON object or array."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()
    # Find first { or [ and last } or ]
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            return raw[start:end + 1]
    return raw


async def _chat(system: str, user: str, max_retries: int = 2) -> str:
    """Call GPT-4o with automatic retry on rate limit and timeout."""
    for attempt in range(max_retries + 1):
        try:
            response = await openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                timeout=60.0,
            )
            return response.choices[0].message.content or ""
        except RateLimitError:
            if attempt < max_retries:
                wait = 60 * (attempt + 1)
                print(f"Rate limit hit, waiting {wait}s (attempt {attempt + 1})")
                await asyncio.sleep(wait)
                continue
            raise RuntimeError("OpenAI rate limit hit — wait 60 seconds and try again")
        except httpx.TimeoutException:
            if attempt < max_retries:
                print(f"Timeout on attempt {attempt + 1}, retrying...")
                continue
            raise RuntimeError("OpenAI request timed out — try again")
        except Exception as e:
            if attempt < max_retries:
                await asyncio.sleep(2)
                continue
            raise RuntimeError(f"OpenAI error: {e}")


def _parse_prompt_parts(combined: str) -> tuple[str, str]:
    parts = combined.split("\nUSER:", 1)
    system = parts[0].replace("SYSTEM:", "", 1).strip()
    user = parts[1].strip() if len(parts) > 1 else ""
    return system, user


def _handle_twilio_error(e: TwilioRestException) -> str:
    msg = str(e)
    code = str(getattr(e, 'code', '') or '')
    if "not opted in" in msg.lower() or code in ("60410", "63016", "21408"):
        return "WhatsApp number not opted into Twilio sandbox. Send 'join <your-keyword>' to +14155238886 from that WhatsApp first."
    if code == "21211":
        return "Invalid phone number format. Use international format: +919876543210"
    if code == "20003":
        return "Twilio credentials invalid. Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in .env"
    return f"WhatsApp send failed: {getattr(e, 'msg', msg)}"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "model": "gpt-4o", "timestamp": datetime.now(timezone.utc).isoformat()}

# Serve the main frontend page
@app.get("/")
async def serve_spa():
    return FileResponse(STATIC_DIR / "index.html")

# Catch-all route to handle Next.js client-side routing
@app.get("/{rest_of_path:path}")
async def catch_all(rest_of_path: str):
    file_path = STATIC_DIR / rest_of_path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/nudge")
async def nudge(req: NudgeRequest):
    if not req.transcript.strip():
        return {"error": "Transcript cannot be empty"}

    lead_dict = req.lead.model_dump()

    try:
        combined = prompts.nudge_prompt(lead_dict, req.transcript)
        system, user = _parse_prompt_parts(combined)
        message = await _chat(system, user)
    except RuntimeError as e:
        return {"error": str(e)}

    try:
        whatsapp.send_text(req.bda_phone, message)
    except TwilioRestException as e:
        return {"error": _handle_twilio_error(e)}
    except RuntimeError as e:
        return {"error": str(e)}

    return {"nudge": message, "sent": True}


@app.post("/generate-pdf")
async def generate_pdf_route(req: GeneratePDFRequest):
    lead_dict = req.lead.model_dump()

    # Step 1: Extract questions
    combined_q = prompts.extract_questions_prompt(req.transcript)
    system_q, user_q = _parse_prompt_parts(combined_q)

    try:
        raw_q = await _chat(system_q, user_q)
    except RuntimeError as e:
        return {"error": str(e)}

    try:
        questions = json.loads(_clean_json(raw_q))
    except json.JSONDecodeError:
        try:
            raw_q2 = await _chat(
                system_q,
                user_q + "\n\nCRITICAL: Return ONLY a raw JSON array. No markdown. No explanation. Start with [ and end with ].",
            )
            questions = json.loads(_clean_json(raw_q2))
        except (json.JSONDecodeError, RuntimeError):
            questions = [{"question": "General program inquiry", "context": "Lead wanted overview", "urgency": "medium", "direct_quote": ""}]

    if not questions:
        questions = [{"question": "General program inquiry", "context": "Lead wanted overview", "urgency": "medium", "direct_quote": ""}]

    # Step 2: Generate PDF content
    combined_p = prompts.pdf_prompt(lead_dict, questions, req.transcript)
    system_p, user_p = _parse_prompt_parts(combined_p)

    try:
        raw_p = await _chat(system_p, user_p)
    except RuntimeError as e:
        return {"error": str(e)}

    try:
        pdf_content = json.loads(_clean_json(raw_p))
    except json.JSONDecodeError:
        try:
            raw_p2 = await _chat(
                system_p,
                user_p + "\n\nCRITICAL: Return ONLY raw JSON. No markdown fences. Start with { and end with }.",
            )
            pdf_content = json.loads(_clean_json(raw_p2))
        except (json.JSONDecodeError, RuntimeError):
            return {"error": "PDF generation failed — AI returned unparseable response", "raw": raw_p}

    # Warn if section count mismatches (non-fatal)
    sections = pdf_content.get("sections", [])
    if len(sections) != len(questions):
        print(f"WARNING: Expected {len(questions)} sections, got {len(sections)}")

    # Step 3: Render PDF
    try:
        pdf_bytes = pdf_generator.generate_pdf(lead_dict, pdf_content)
    except Exception as e:
        return {"error": f"PDF rendering failed: {e}"}

    pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    return {"questions": questions, "pdf_content": pdf_content, "pdf_base64": pdf_b64}


@app.post("/send-to-lead")
async def send_to_lead(req: SendToLeadRequest):
    lead_dict = req.lead.model_dump()
    backend_url = os.getenv("BACKEND_URL", "http://localhost:8000")

    try:
        pdf_bytes = pdf_generator.generate_pdf(lead_dict, req.pdf_content)
    except Exception as e:
        return {"error": f"PDF rendering failed: {e}"}

    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", lead_dict.get("name", "lead"))
    filename = f"{safe_name}_scaler_overview.pdf"

    try:
        result = whatsapp.send_pdf(
            to=req.lead_phone,
            message=req.whatsapp_message,
            pdf_bytes=pdf_bytes,
            filename=filename,
            base_url=backend_url,
        )
    except TwilioRestException as e:
        return {"error": _handle_twilio_error(e)}
    except RuntimeError as e:
        return {"error": str(e)}

    return {"sent": True, **result}


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    content_type = audio.content_type or ""
    if not content_type.startswith("audio/"):
        return {"error": f"Invalid file type '{content_type}'. Please upload an audio file (mp3, wav, m4a, mp4)."}

    contents = await audio.read()

    if len(contents) > 25 * 1024 * 1024:
        return {"error": "Audio file too large — max 25MB for Whisper"}

    suffix = Path(audio.filename or "audio.mp3").suffix or ".mp3"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(contents)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as f:
            result = await openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=(audio.filename or "audio.mp3", f),
            )
        return {"transcript": result.text}
    except Exception as e:
        return {"error": f"Transcription failed: {e}"}
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
