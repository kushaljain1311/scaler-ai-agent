import io
from datetime import date
from xhtml2pdf import pisa


def get_accent_color(yoe: int) -> dict:
    if yoe == 0:
        # Fresher — warm orange
        return {"primary": "#E8521A", "light": "#FFF0EB", "dark": "#B33D10"}
    elif yoe <= 5:
        # Mid-level — blue
        return {"primary": "#1A56E8", "light": "#EBF0FF", "dark": "#1040B0"}
    else:
        # Senior — deep purple
        return {"primary": "#6B21A8", "light": "#F5EBFF", "dark": "#4A1570"}


def build_pdf_html(lead: dict, pdf_content: dict) -> str:
    accent = get_accent_color(lead.get("yoe", 0))
    name = lead.get("name", "").strip().title()
    today = date.today().strftime("%d %B %Y")

    # ── Questions recap bullets ───────────────────────────────────────────────
    questions_recap = pdf_content.get("questions_recap", [])
    recap_html = "\n".join(f"<li>{q}</li>" for q in questions_recap)

    # ── Deep answer sections ──────────────────────────────────────────────────
    sections_html = ""
    for s in pdf_content.get("sections", []):

        # Evidence — only render if real value
        ev = s.get("evidence")
        evidence_html = ""
        if ev and str(ev).strip().lower() not in ("null", "none", ""):
            evidence_html = f"""
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td class="evidence-cell">
                  <b>Verified:</b> {ev}
                </td>
              </tr>
            </table>"""

        # ROI reasoning — only render if real value
        roi = s.get("roi_reasoning")
        roi_html = ""
        if roi and str(roi).strip().lower() not in ("null", "none", ""):
            roi_html = f"""
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td class="roi-cell">
                  <b>Why this matters for you:</b> {roi}
                </td>
              </tr>
            </table>"""

        acknowledgement = s.get("acknowledgement", "")
        body = s.get("body", "")
        title = s.get("title", "")

        sections_html += f"""
        <table width="100%" cellpadding="0" cellspacing="0" class="section-card">
          <tr>
            <td class="section-inner">
              <p class="section-title">{title}</p>
              <p class="acknowledgement">&ldquo;{acknowledgement}&rdquo;</p>
              <p class="body-text">{body}</p>
              {roi_html}
              {evidence_html}
            </td>
          </tr>
        </table>
        <br/>"""

    # ── Curriculum section ────────────────────────────────────────────────────
    curriculum = pdf_content.get("curriculum_section", {})
    curriculum_items = "\n".join(
        f"<li>{item}</li>" for item in curriculum.get("items", [])
    )
    curriculum_title = curriculum.get("title", "What You Will Actually Build")
    honesty_note = curriculum.get("honesty_note", "")

    # ── Closing section ───────────────────────────────────────────────────────
    closing = pdf_content.get("closing", {})
    if isinstance(closing, str):
        closing_html = f"<p>{closing}</p>"
    else:
        reframe = closing.get("reframe", "")
        low_risk = closing.get("low_risk", "")
        action = closing.get("action", "")
        closing_html = f"""
        <p class="closing-text">{reframe}</p>
        <p class="closing-text">{low_risk}</p>
        <p class="action-line">--&gt; {action}</p>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8"/>
<style>

  /* ── Reset ── */
  * {{
    margin: 0;
    padding: 0;
  }}

  /* ── Base ── */
  body {{
    font-family: Helvetica, Arial, sans-serif;
    color: #1a1a1a;
    background: #ffffff;
    font-size: 12px;
    line-height: 1.7;
  }}

  /* ── Header ── */
  .header-table {{
    width: 100%;
    background-color: {accent['primary']};
    padding: 0;
    margin-bottom: 24px;
  }}
  .header-inner {{
    padding: 28px 36px;
  }}
  .header-brand {{
    font-size: 10px;
    color: #ffffff;
    opacity: 0.85;
    margin-bottom: 6px;
  }}
  .header-name {{
    font-size: 22px;
    font-weight: bold;
    color: #ffffff;
    margin-bottom: 4px;
  }}
  .header-date {{
    font-size: 10px;
    color: #ffffff;
  }}

  /* ── Content wrapper ── */
  .content {{
    padding: 0px 36px 36px 36px;
  }}

  /* ── Headline ── */
  .headline {{
    font-size: 17px;
    font-weight: bold;
    color: {accent['primary']};
    margin-bottom: 16px;
    line-height: 1.4;
  }}

  /* ── Opening block ── */
  .opening-table {{
    width: 100%;
    margin-bottom: 24px;
    background-color: {accent['light']};
    border-left: 4px solid {accent['primary']};
  }}
  .opening-inner {{
    padding: 14px 18px;
    font-size: 12px;
    line-height: 1.8;
    color: #1a1a1a;
  }}

  /* ── Recap box ── */
  .recap-table {{
    width: 100%;
    background-color: #f8f9fa;
    border: 1px solid #e9ecef;
    margin-bottom: 24px;
  }}
  .recap-inner {{
    padding: 16px 20px;
  }}
  .recap-label {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #666666;
    font-weight: bold;
    margin-bottom: 10px;
  }}
  .recap-inner ul {{
    padding-left: 18px;
    margin: 0;
  }}
  .recap-inner li {{
    margin-bottom: 5px;
    color: #333333;
    font-size: 12px;
  }}

  /* ── Section cards ── */
  .section-card {{
    width: 100%;
    border: 1px solid #e0e0e0;
    background-color: #ffffff;
  }}
  .section-inner {{
    padding: 18px 20px;
  }}
  .section-title {{
    font-size: 13px;
    font-weight: bold;
    color: {accent['primary']};
    margin-bottom: 8px;
  }}
  .acknowledgement {{
    font-style: italic;
    color: #555555;
    margin-bottom: 10px;
    font-size: 11.5px;
  }}
  .body-text {{
    color: #333333;
    margin-bottom: 10px;
    font-size: 12px;
  }}

  /* ── ROI cell ── */
  .roi-cell {{
    background-color: #f0fdf4;
    border-left: 3px solid #16a34a;
    padding: 8px 12px;
    color: #15803d;
    font-size: 11px;
    margin-bottom: 8px;
  }}

  /* ── Evidence cell ── */
  .evidence-cell {{
    background-color: {accent['light']};
    color: {accent['primary']};
    font-size: 11px;
    padding: 6px 10px;
    font-weight: bold;
  }}

  /* ── Curriculum box ── */
  .curriculum-table {{
    width: 100%;
    background-color: #1a1a1a;
    margin: 24px 0;
  }}
  .curriculum-inner {{
    padding: 20px;
  }}
  .curriculum-title {{
    font-size: 13px;
    font-weight: bold;
    color: #ffffff;
    margin-bottom: 12px;
  }}
  .curriculum-inner ul {{
    padding-left: 18px;
    margin: 0;
  }}
  .curriculum-inner li {{
    margin-bottom: 6px;
    color: #d1d5db;
    font-size: 12px;
  }}
  .honesty-note {{
    font-size: 10px;
    color: #9ca3af;
    margin-top: 10px;
    font-style: italic;
  }}

  /* ── Closing box ── */
  .closing-table {{
    width: 100%;
    background-color: {accent['light']};
    border: 2px solid {accent['primary']};
    margin-top: 24px;
  }}
  .closing-inner {{
    padding: 20px;
  }}
  .closing-title {{
    font-size: 13px;
    font-weight: bold;
    color: {accent['primary']};
    margin-bottom: 12px;
  }}
  .closing-text {{
    font-size: 12px;
    color: #333333;
    margin-bottom: 8px;
  }}
  .action-line {{
    font-weight: bold;
    font-size: 13px;
    color: {accent['primary']};
    margin-top: 12px;
  }}

  /* ── Footer ── */
  .footer {{
    margin-top: 32px;
    padding-top: 12px;
    border-top: 1px solid #e9ecef;
    font-size: 10px;
    color: #999999;
    text-align: center;
  }}

  /* ── Page break helper ── */
  .page-break {{
    page-break-before: always;
  }}

</style>
</head>
<body>

<!-- HEADER -->
<table class="header-table" cellpadding="0" cellspacing="0">
  <tr>
    <td class="header-inner">
      <p class="header-brand">Scaler Academy &middot; Prepared for {name}</p>
      <p class="header-name">{name}</p>
      <p class="header-date">{today}</p>
    </td>
  </tr>
</table>

<!-- MAIN CONTENT -->
<div class="content">

  <!-- Headline -->
  <p class="headline">{pdf_content.get('headline', '')}</p>

  <!-- Opening -->
  <table class="opening-table" cellpadding="0" cellspacing="0">
    <tr>
      <td class="opening-inner">{pdf_content.get('opening', '')}</td>
    </tr>
  </table>

  <!-- Questions recap -->
  <table class="recap-table" cellpadding="0" cellspacing="0">
    <tr>
      <td class="recap-inner">
        <p class="recap-label">From our conversation &mdash; what you wanted clarity on</p>
        <ul>{recap_html}</ul>
      </td>
    </tr>
  </table>

  <!-- Deep answer sections -->
  {sections_html}

  <!-- Curriculum box -->
  <table class="curriculum-table" cellpadding="0" cellspacing="0">
    <tr>
      <td class="curriculum-inner">
        <p class="curriculum-title">{curriculum_title}</p>
        <ul>{curriculum_items}</ul>
        <p class="honesty-note">{honesty_note}</p>
      </td>
    </tr>
  </table>

  <!-- Closing CTA -->
  <table class="closing-table" cellpadding="0" cellspacing="0">
    <tr>
      <td class="closing-inner">
        <p class="closing-title">Your Next Step</p>
        {closing_html}
      </td>
    </tr>
  </table>

  <!-- Footer -->
  <p class="footer">
    This document was prepared specifically for {name} &middot;
    Scaler Academy &middot; scaler.com
  </p>

</div>
</body>
</html>"""


def generate_pdf(lead: dict, pdf_content: dict) -> bytes:
    html_str = build_pdf_html(lead, pdf_content)
    buf = io.BytesIO()

    result = pisa.CreatePDF(html_str, dest=buf)

    if result.err:
        raise RuntimeError(f"PDF generation failed with {result.err} errors. Check HTML/CSS.")

    return buf.getvalue()