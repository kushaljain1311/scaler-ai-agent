import json
import os
import re
import tempfile
from pathlib import Path

import httpx
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client as TwilioClient

import pdf_generator
import prompts

load_dotenv()

st.set_page_config(
    page_title="Scaler BDA Agent",
    layout="wide",
)


# ── Secrets helper (works locally via .env AND on Streamlit Cloud) ────────────

def _env(key: str) -> str | None:
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key)


_openai = OpenAI(api_key=_env("OPENAI_API_KEY"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = raw.strip()
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = raw.find(start_char)
        end = raw.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            return raw[start:end + 1]
    return raw


def _chat(system: str, user: str) -> str:
    response = _openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        timeout=120.0,
    )
    return response.choices[0].message.content or ""


def _parse_prompt_parts(combined: str) -> tuple[str, str]:
    parts = combined.split("\nUSER:", 1)
    system = parts[0].replace("SYSTEM:", "", 1).strip()
    user = parts[1].strip() if len(parts) > 1 else ""
    return system, user


def _handle_twilio_error(e: TwilioRestException) -> str:
    msg = str(e)
    code = str(getattr(e, "code", "") or "")
    if "not opted in" in msg.lower() or code in ("60410", "63016", "21408"):
        return "Number not opted into Twilio sandbox. Send 'join <keyword>' to +14155238886 on WhatsApp first."
    if code == "21211":
        return "Invalid phone number. Use international format: +919876543210"
    if code == "20003":
        return "Twilio credentials invalid. Check TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN."
    return f"WhatsApp send failed: {getattr(e, 'msg', msg)}"


def _normalise_wa(number: str) -> str:
    cleaned = re.sub(r"[\s\-()]", "", number)
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return f"whatsapp:{cleaned}"


def _send_text_wa(to: str, message: str):
    client = TwilioClient(_env("TWILIO_ACCOUNT_SID"), _env("TWILIO_AUTH_TOKEN"))
    client.messages.create(
        from_=_env("TWILIO_WHATSAPP_FROM") or "whatsapp:+14155238886",
        to=_normalise_wa(to),
        body=message,
    )


def _upload_pdf(pdf_bytes: bytes, filename: str) -> str:
    """Upload PDF to 0x0.st and return a public URL."""
    r = httpx.post(
        "https://0x0.st",
        files={"file": (filename, pdf_bytes, "application/pdf")},
        timeout=30.0,
    )
    st.write(f"Upload HTTP status: {r.status_code}")
    st.write(f"Upload response: {r.text[:300]}")
    if r.status_code != 200:
        raise RuntimeError(f"PDF upload failed: HTTP {r.status_code} — {r.text[:200]}")
    return r.text.strip()


def _send_pdf_via_twilio(to: str, pdf_url: str, message: str) -> str:
    client = TwilioClient(_env("TWILIO_ACCOUNT_SID"), _env("TWILIO_AUTH_TOKEN"))
    msg = client.messages.create(
        from_=_env("TWILIO_WHATSAPP_FROM") or "whatsapp:+14155238886",
        to=_normalise_wa(to),
        body=message,
        media_url=[pdf_url],
    )
    return msg.sid


# ── Session state init ────────────────────────────────────────────────────────

for _k in ["transcript", "from_audio", "nudge", "pdf_content", "pdf_bytes"]:
    if _k not in st.session_state:
        st.session_state[_k] = None


# ── Sidebar — Lead Profile ────────────────────────────────────────────────────

PRESETS = {
    "Rohan (4 YoE, TCS)":      dict(name="Rohan Mehta",  role="Software Engineer", company="TCS",    yoe=4, intent="career_switch", edu="B.Tech CS", sal="8 LPA"),
    "Karthik (9 YoE, Google)": dict(name="Karthik Nair", role="Senior SDE",        company="Google", yoe=9, intent="upskill",      edu="M.Tech",    sal="45 LPA"),
    "Meera (Fresher)":         dict(name="Meera Sharma", role="Fresher",           company="—",      yoe=0, intent="job_search",   edu="B.Com",     sal=""),
}

with st.sidebar:
    st.title("Lead Profile")
    preset = st.selectbox("Quick preset", ["—"] + list(PRESETS.keys()))
    p = PRESETS.get(preset, dict(name="", role="", company="", yoe=2, intent="career_switch", edu="", sal=""))

    name      = st.text_input("Name *",               value=p["name"])
    role      = st.text_input("Current Role *",        value=p["role"])
    company   = st.text_input("Company *",             value=p["company"])
    yoe       = st.number_input("Years of Experience", min_value=0, max_value=40, value=p["yoe"])
    intent    = st.selectbox(
        "Intent",
        ["career_switch", "upskill", "promotion", "job_search"],
        index=["career_switch", "upskill", "promotion", "job_search"].index(p["intent"]),
    )
    education = st.text_input("Education (optional)",  value=p["edu"])
    salary    = st.text_input("Salary (optional)",     value=p["sal"])

    st.divider()
    st.subheader("WhatsApp Numbers")
    bda_phone  = st.text_input("Your number (BDA)",  placeholder="+919876543210")
    lead_phone = st.text_input("Lead's number",      placeholder="+919876543210")

lead = {
    "name":      name,
    "role":      role,
    "company":   company,
    "yoe":       int(yoe),
    "intent":    intent,
    "education": education or None,
    "salary":    salary or None,
}


# ── Main ──────────────────────────────────────────────────────────────────────

st.title("Scaler BDA Agent")

# ── Transcript ────────────────────────────────────────────────────────────────

st.subheader("Call Transcript")
tab_paste, tab_audio = st.tabs(["Paste Transcript", "Upload Audio"])

with tab_paste:
    typed = st.text_area(
        "Transcript",
        value=st.session_state.transcript or "",
        height=200,
        placeholder="Paste the call transcript here...",
        label_visibility="collapsed",
    )
    if typed != (st.session_state.transcript or ""):
        st.session_state.transcript = typed or None
        st.session_state.from_audio = False

with tab_audio:
    audio_file = st.file_uploader(
        "Upload audio",
        type=["mp3", "wav", "m4a", "mp4", "ogg", "webm"],
        label_visibility="collapsed",
    )
    if audio_file and st.button("Transcribe with Whisper", type="primary"):
        with st.spinner("Transcribing..."):
            try:
                suffix = Path(audio_file.name).suffix or ".mp3"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(audio_file.read())
                    tmp_path = tmp.name
                with open(tmp_path, "rb") as f:
                    result = _openai.audio.transcriptions.create(
                        model="whisper-1",
                        file=(audio_file.name, f),
                    )
                os.unlink(tmp_path)
                st.session_state.transcript = result.text
                st.session_state.from_audio = True
                st.rerun()
            except Exception as e:
                st.error(f"Transcription failed: {e}")

if st.session_state.transcript:
    icon = "🎙" if st.session_state.from_audio else "📝"
    label = "Transcribed from audio" if st.session_state.from_audio else "Transcript"
    with st.expander(f"{icon} {label}", expanded=True):
        st.write(st.session_state.transcript)

st.divider()

# ── Nudge + PDF columns ───────────────────────────────────────────────────────

col_nudge, col_pdf = st.columns(2)

# ── Nudge ─────────────────────────────────────────────────────────────────────

with col_nudge:
    st.subheader("BDA Strategy Nudge")

    if st.button("Generate Nudge", type="primary", use_container_width=True):
        if not st.session_state.transcript:
            st.error("Add a transcript first.")
        elif not name.strip():
            st.error("Fill in the lead profile.")
        else:
            with st.spinner("Generating strategy brief..."):
                try:
                    combined = prompts.nudge_prompt(lead, st.session_state.transcript)
                    sys_, usr = _parse_prompt_parts(combined)
                    st.session_state.nudge = _chat(sys_, usr)
                except Exception as e:
                    st.error(str(e))

    if st.session_state.nudge:
        st.markdown(st.session_state.nudge)

        if bda_phone.strip():
            if st.button("Send to My WhatsApp", use_container_width=True):
                with st.spinner("Sending..."):
                    try:
                        _send_text_wa(bda_phone, st.session_state.nudge)
                        st.success("Sent to your WhatsApp!")
                    except TwilioRestException as e:
                        st.error(_handle_twilio_error(e))
                    except Exception as e:
                        st.error(str(e))
        else:
            st.caption("Enter your WhatsApp number in the sidebar to send the nudge.")

# ── PDF ───────────────────────────────────────────────────────────────────────

with col_pdf:
    st.subheader("PDF for Lead")

    if st.button("Generate PDF", type="primary", use_container_width=True):
        if not st.session_state.transcript:
            st.error("Add a transcript first.")
        elif not name.strip():
            st.error("Fill in the lead profile.")
        else:
            try:
                with st.spinner("Step 1 / 3 — Extracting questions from transcript..."):
                    cq = prompts.extract_questions_prompt(st.session_state.transcript)
                    sq, uq = _parse_prompt_parts(cq)
                    raw_q = _chat(sq, uq)
                    try:
                        questions = json.loads(_clean_json(raw_q))
                    except json.JSONDecodeError:
                        questions = [{"question": "General program inquiry", "context": "", "urgency": "medium", "direct_quote": ""}]

                with st.spinner("Step 2 / 3 — Building conversion document..."):
                    cp = prompts.pdf_prompt(lead, questions, st.session_state.transcript)
                    sp, up = _parse_prompt_parts(cp)
                    raw_p = _chat(sp, up)
                    try:
                        pdf_content = json.loads(_clean_json(raw_p))
                    except json.JSONDecodeError:
                        st.error("AI returned an unparseable response — try again.")
                        st.stop()

                with st.spinner("Step 3 / 3 — Rendering PDF..."):
                    pdf_bytes = pdf_generator.generate_pdf(lead, pdf_content)
                    st.session_state.pdf_content = pdf_content
                    st.session_state.pdf_bytes = pdf_bytes

                st.success("PDF ready!")

            except Exception as e:
                st.error(str(e))

    if st.session_state.pdf_bytes:
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name or "lead")
        filename = f"{safe_name}_scaler_overview.pdf"

        st.download_button(
            label="Download PDF",
            data=st.session_state.pdf_bytes,
            file_name=filename,
            mime="application/pdf",
            use_container_width=True,
        )

        if lead_phone.strip():
            if st.button("Send PDF to Lead's WhatsApp", use_container_width=True):
                msg = f"Hi {name}! Here's your personalized Scaler overview based on our conversation today."
                try:
                    with st.spinner("Step 1/2 — Uploading PDF to get public URL..."):
                        pdf_url = _upload_pdf(st.session_state.pdf_bytes, filename)
                    st.info(f"PDF uploaded. Public URL: {pdf_url}")

                    with st.spinner("Step 2/2 — Sending via Twilio WhatsApp..."):
                        sid = _send_pdf_via_twilio(lead_phone, pdf_url, msg)
                    st.success(f"Sent! Twilio SID: {sid}")
                except TwilioRestException as e:
                    st.error(_handle_twilio_error(e))
                    st.exception(e)
                except Exception as e:
                    st.error(str(e))
                    st.exception(e)
        else:
            st.caption("Enter the lead's WhatsApp number in the sidebar to send the PDF.")

        if st.session_state.pdf_content:
            with st.expander("Preview PDF Content"):
                pc = st.session_state.pdf_content
                st.markdown(f"### {pc.get('headline', '')}")
                st.write(pc.get("opening", ""))

                if pc.get("questions_recap"):
                    st.markdown("**From the conversation:**")
                    for q in pc["questions_recap"]:
                        st.markdown(f"- {q}")

                for s in pc.get("sections", []):
                    with st.container(border=True):
                        st.markdown(f"**{s.get('title', '')}**")
                        if s.get("acknowledgement"):
                            st.markdown(f"*\"{s['acknowledgement']}\"*")
                        st.write(s.get("body", ""))
                        roi = s.get("roi_reasoning")
                        if roi and str(roi).strip().lower() not in ("null", "none", ""):
                            st.success(f"Why this matters: {roi}")
                        ev = s.get("evidence")
                        if ev and str(ev).strip().lower() not in ("null", "none", ""):
                            st.info(f"Verified: {ev}")

                cur = pc.get("curriculum_section", {})
                if cur.get("items"):
                    st.markdown(f"**{cur.get('title', 'What You Will Build')}**")
                    for item in cur["items"]:
                        st.markdown(f"- {item}")

                closing = pc.get("closing", {})
                if isinstance(closing, dict):
                    st.markdown("**Your Next Step**")
                    st.write(closing.get("reframe", ""))
                    st.write(closing.get("low_risk", ""))
                    st.markdown(f"**→ {closing.get('action', '')}**")
