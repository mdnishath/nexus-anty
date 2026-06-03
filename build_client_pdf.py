"""Generate MailNexus Pro client-facing feature PDF."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, KeepTogether
)

OUTPUT = r"E:\NST Anty Android\MailNexus_Pro_Client_Overview.pdf"

# ---------------- Colors ----------------
BRAND = colors.HexColor("#0078D4")
BRAND_DARK = colors.HexColor("#005A9E")
ACCENT = colors.HexColor("#F59E0B")
TEXT = colors.HexColor("#1F2937")
MUTED = colors.HexColor("#6B7280")
BG_LIGHT = colors.HexColor("#F3F4F6")
BG_HEADER = colors.HexColor("#0078D4")
BG_ROW_ALT = colors.HexColor("#F9FAFB")
SUCCESS = colors.HexColor("#10B981")

# ---------------- Styles ----------------
styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    "TitleBig", parent=styles["Title"],
    fontSize=32, leading=38, textColor=BRAND_DARK,
    alignment=TA_CENTER, spaceAfter=6, fontName="Helvetica-Bold",
)
subtitle_style = ParagraphStyle(
    "Subtitle", parent=styles["Normal"],
    fontSize=14, leading=18, textColor=MUTED,
    alignment=TA_CENTER, spaceAfter=24, fontName="Helvetica",
)
h1 = ParagraphStyle(
    "H1", parent=styles["Heading1"],
    fontSize=20, leading=24, textColor=BRAND_DARK,
    spaceBefore=10, spaceAfter=12, fontName="Helvetica-Bold",
)
h2 = ParagraphStyle(
    "H2", parent=styles["Heading2"],
    fontSize=15, leading=19, textColor=BRAND,
    spaceBefore=14, spaceAfter=8, fontName="Helvetica-Bold",
)
h3 = ParagraphStyle(
    "H3", parent=styles["Heading3"],
    fontSize=12, leading=15, textColor=TEXT,
    spaceBefore=8, spaceAfter=4, fontName="Helvetica-Bold",
)
body = ParagraphStyle(
    "Body", parent=styles["Normal"],
    fontSize=10.5, leading=15, textColor=TEXT,
    alignment=TA_JUSTIFY, spaceAfter=6, fontName="Helvetica",
)
pitch = ParagraphStyle(
    "Pitch", parent=styles["Normal"],
    fontSize=13, leading=20, textColor=BRAND_DARK,
    alignment=TA_CENTER, spaceAfter=10,
    fontName="Helvetica-Oblique",
)
small_center = ParagraphStyle(
    "SmallCenter", parent=styles["Normal"],
    fontSize=9, leading=12, textColor=MUTED,
    alignment=TA_CENTER, fontName="Helvetica",
)
cell_head = ParagraphStyle(
    "CellHead", parent=styles["Normal"],
    fontSize=10, leading=13, textColor=colors.white,
    fontName="Helvetica-Bold", alignment=TA_LEFT,
)
cell = ParagraphStyle(
    "Cell", parent=styles["Normal"],
    fontSize=10, leading=13, textColor=TEXT,
    fontName="Helvetica", alignment=TA_LEFT,
)
cell_bold = ParagraphStyle(
    "CellBold", parent=styles["Normal"],
    fontSize=10, leading=13, textColor=BRAND_DARK,
    fontName="Helvetica-Bold", alignment=TA_LEFT,
)

# ---------------- Helpers ----------------
def feature_table(rows, col_widths=(5.5*cm, 11.5*cm), header=("Feature", "Client Benefit")):
    data = [[Paragraph(header[0], cell_head), Paragraph(header[1], cell_head)]]
    for f, b in rows:
        data.append([Paragraph(f, cell_bold), Paragraph(b, cell)])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BG_HEADER),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
    ])
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.add("BACKGROUND", (0, i), (-1, i), BG_ROW_ALT)
    t.setStyle(style)
    return t

def numbers_table(rows):
    data = [[Paragraph("Scenario", cell_head),
             Paragraph("Manual", cell_head),
             Paragraph("With MailNexus Pro", cell_head)]]
    for a, b, c in rows:
        data.append([Paragraph(a, cell_bold), Paragraph(b, cell), Paragraph(c, cell)])
    t = Table(data, colWidths=(6*cm, 5.5*cm, 5.5*cm), repeatRows=1)
    style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BG_HEADER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
    ])
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.add("BACKGROUND", (0, i), (-1, i), BG_ROW_ALT)
    t.setStyle(style)
    return t

def divider():
    t = Table([[""]], colWidths=(17*cm,), rowHeights=(0.06*cm,))
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRAND)]))
    return t

# ---------------- Page templates ----------------
def header_footer(canvas, doc):
    canvas.saveState()
    # Footer line
    canvas.setStrokeColor(colors.HexColor("#E5E7EB"))
    canvas.setLineWidth(0.4)
    canvas.line(2*cm, 1.6*cm, A4[0] - 2*cm, 1.6*cm)
    # Footer text
    canvas.setFont("Helvetica", 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(2*cm, 1.1*cm, "MailNexus Pro v1.0.0  |  Enterprise Gmail & Google Maps Automation")
    canvas.drawRightString(A4[0] - 2*cm, 1.1*cm, f"Page {doc.page}")
    canvas.restoreState()

# ---------------- Build story ----------------
story = []

# ===== COVER =====
story.append(Spacer(1, 4*cm))
story.append(Paragraph("MailNexus Pro", title_style))
story.append(Paragraph("Enterprise Gmail Account &amp; Google Maps Automation Platform", subtitle_style))

story.append(Spacer(1, 1.5*cm))
story.append(divider())
story.append(Spacer(1, 0.8*cm))

story.append(Paragraph(
    "<i>&ldquo;Process 100 Gmail accounts in 2-4 hours instead of 2 weeks. "
    "Every account gets its own IP and browser identity so Google can&rsquo;t detect automation.&rdquo;</i>",
    pitch
))

story.append(Spacer(1, 4*cm))
story.append(Paragraph("Client Overview &amp; Feature Brief", subtitle_style))
story.append(Paragraph("Prepared for client review", small_center))
story.append(PageBreak())

# ===== OVERVIEW =====
story.append(Paragraph("What is MailNexus Pro?", h1))
story.append(Paragraph(
    "MailNexus Pro is a professional Windows desktop application that automates bulk Gmail account "
    "management at scale. It can run <b>up to 10 accounts in parallel</b>, each with its own proxy IP "
    "and unique browser fingerprint, so Google sees them as 10 different real users &mdash; not bots.",
    body
))
story.append(Paragraph(
    "Built on Electron + Python + Playwright, the platform handles everything from password rotation "
    "and 2FA setup to Google Maps review posting and account appeal management &mdash; all from a single "
    "dashboard with live monitoring and Excel-based reporting.",
    body
))

story.append(Paragraph("Who is it for?", h2))
who_data = [
    ["•", Paragraph("<b>Digital marketing agencies</b> managing dozens to hundreds of client Gmail accounts.", cell)],
    ["•", Paragraph("<b>Google Maps / GMB reputation management</b> services posting and managing reviews at scale.", cell)],
    ["•", Paragraph("<b>Account security teams</b> performing bulk credential rotation and 2FA rollouts.", cell)],
    ["•", Paragraph("<b>Businesses</b> automating the full Google account lifecycle &mdash; create, secure, maintain, appeal.", cell)],
]
who_table = Table(who_data, colWidths=(0.6*cm, 16.4*cm))
who_table.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))
story.append(who_table)

story.append(Spacer(1, 0.4*cm))
story.append(Paragraph("The Bottom Line", h2))
story.append(Paragraph(
    "<b>One operator with MailNexus Pro can do the work of 20 people doing it manually.</b> "
    "It eliminates the repetitive clicking, login challenges, and verification steps that make "
    "Gmail management painful &mdash; turning days of work into hours.",
    body
))

story.append(PageBreak())

# ===== THE 4 WORKFLOWS =====
story.append(Paragraph("The 4 Core Workflows", h1))
story.append(Paragraph(
    "MailNexus Pro is organized into four independent workflows. Each one can be run on its own or "
    "chained together for a complete account lifecycle pipeline.",
    body
))

# Step 1
story.append(Paragraph("1. Account Cleanup &amp; Language Setup", h2))
story.append(Paragraph(
    "Before any other operation runs, this step normalizes all accounts so they behave uniformly &mdash; "
    "no broken automation from mixed languages or lingering &ldquo;suspicious activity&rdquo; warnings.",
    body
))
story.append(feature_table([
    ("Set Language to English",
     "All accounts behave uniformly. Eliminates automation breakage caused by foreign-language Google UI."),
    ("Clear Suspicious Activity",
     "Removes Google&rsquo;s &ldquo;we noticed unusual activity&rdquo; warnings that would otherwise block further actions."),
    ("Safe Browsing On / Off",
     "Centralized control over each account&rsquo;s security posture across the whole batch."),
]))

# Step 2
story.append(Spacer(1, 0.4*cm))
story.append(Paragraph("2. Full Security Suite &mdash; 14 Operations", h2))
story.append(Paragraph(
    "Complete account hardening or credential rotation. Add, update, or remove every Google security "
    "setting across hundreds of accounts in one run.",
    body
))
story.append(feature_table([
    ("Change Password",
     "Bulk rotate passwords for security compliance or after a handover."),
    ("Recovery Phone &mdash; Add / Remove",
     "Manage recovery contacts at scale with one Excel sheet."),
    ("Recovery Email &mdash; Add / Remove",
     "Same for backup recovery emails."),
    ("Authenticator (2FA) &mdash; Generate / Remove",
     "Roll out app-based 2FA in bulk. The new TOTP secret is saved back to Excel automatically."),
    ("Backup Codes &mdash; Generate / Remove",
     "Auto-generates 10 backup codes per account, written into 10 dedicated Excel columns."),
    ("2FA Phone &mdash; Add / Remove",
     "SMS-based 2FA management."),
    ("Remove All Devices",
     "Force-logout from every device an account is signed into. Critical for handed-over or stolen accounts."),
    ("Change Account Name",
     "Bulk rename accounts (first + last name) &mdash; useful for rebranding or impersonation cleanup."),
    ("Security Checkup",
     "Runs Google&rsquo;s own security audit on every account."),
]))

story.append(Spacer(1, 0.3*cm))
story.append(Paragraph(
    "<b>Why this matters:</b> Manually, full security hardening is ~10 minutes per account. "
    "100 accounts &asymp; 16+ hours. With MailNexus Pro: under 2 hours.",
    body
))

story.append(PageBreak())

# Step 3 - the big one
story.append(Paragraph("3. Google Maps Review Management", h2))
story.append(Paragraph(
    "The marquee feature for reputation-management and GMB agencies. Post, verify, and clean up "
    "Google Maps reviews at scale &mdash; with proof-of-delivery share links for every published review.",
    body
))
story.append(feature_table([
    ("Write Reviews (R3)",
     "Post star ratings (1-5) with custom review text on any Google Maps listing."),
    ("Smart Status Verification",
     "After posting, the bot polls up to 5 times to confirm the review actually went LIVE &mdash; not stuck in &ldquo;pending&rdquo;."),
    ("Auto-Delete Stuck Reviews",
     "If a review fails to publish, the bot cleans it up automatically so the account stays in good standing."),
    ("Share Link Extraction",
     "Every successfully posted review&rsquo;s public URL is captured in Excel &mdash; proof of delivery for your client."),
    ("Delete All Reviews (R1)",
     "Wipe an account&rsquo;s entire review history in one click."),
    ("Delete Draft Reviews (R2)",
     "Remove only the pending / unpublished reviews, leaving live ones intact."),
    ("Profile Lock On / Off (R4 / R5)",
     "Hide or unhide the account&rsquo;s public Maps contribution profile."),
    ("Multi-language Support",
     "Reviews can be posted in English, French, German, Spanish, or Italian."),
]))

story.append(Spacer(1, 0.3*cm))
story.append(Paragraph(
    "<b>Why this matters:</b> A reputation agency posting 500 reviews/month manually would need a "
    "full-time employee. MailNexus Pro automates the whole pipeline and hands back a share-link "
    "report you can give directly to the client as proof.",
    body
))

# Step 4
story.append(Spacer(1, 0.4*cm))
story.append(Paragraph("4. Account Appeal Management", h2))
story.append(Paragraph(
    "For suspended or flagged accounts. Submit and track appeals across an entire portfolio at once.",
    body
))
story.append(feature_table([
    ("Submit Appeal (A1)",
     "File appeals in bulk for suspended accounts using custom messages from Excel."),
    ("Delete Refused Appeals (A2)",
     "Clean up rejected appeals so you can re-submit with a fresh message."),
    ("Live Status Check (A3)",
     "Poll current appeal status across all accounts in one batch run."),
]))

story.append(PageBreak())

# ===== ANTI-DETECTION =====
story.append(Paragraph("Anti-Detection &mdash; Why Google Doesn&rsquo;t Catch It", h1))
story.append(Paragraph(
    "Bulk Gmail automation lives or dies on whether Google&rsquo;s anti-bot systems catch you. "
    "MailNexus Pro ships with a multi-layer stealth system designed for long-running production "
    "workloads on real client accounts.",
    body
))
story.append(feature_table([
    ("Per-Worker Browser Fingerprint",
     "Each parallel worker gets a unique OS, Chrome version, and User-Agent. Google sees 10 different &ldquo;people&rdquo;, not 10 copies of the same bot."),
    ("SOCKS5 Proxy Bridge",
     "Each account routes through a separate IP. Full support for authenticated residential SOCKS5 proxies (which Playwright doesn&rsquo;t support natively)."),
    ("Auto Timezone Matching",
     "The browser&rsquo;s timezone is auto-detected from the proxy&rsquo;s geographic IP location &mdash; so a US proxy doesn&rsquo;t look like it&rsquo;s running from Asia."),
    ("Stealth Chromium Flags",
     "Disables the standard automation signals Google checks for (<i>navigator.webdriver</i>, AutomationControlled, etc.)."),
    ("Isolated Chrome Profiles",
     "Every worker has its own persistent browser profile. Cookies, cache, and sessions never leak between accounts."),
    ("Accept-Language Header Sync",
     "HTTP headers match the target locale &mdash; consistent with the proxy region and account language."),
], col_widths=(5.5*cm, 11.5*cm)))

story.append(Spacer(1, 0.4*cm))
story.append(Paragraph(
    "<b>Client benefit:</b> Accounts don&rsquo;t get flagged or banned for &ldquo;suspicious activity&rdquo; "
    "&mdash; which is the #1 way bulk-management tools normally burn out client accounts.",
    body
))

story.append(PageBreak())

# ===== LOGIN INTELLIGENCE =====
story.append(Paragraph("Smart Login System", h1))
story.append(Paragraph(
    "Google throws a different login challenge almost every time. MailNexus Pro detects and resolves "
    "each one automatically &mdash; without operator intervention.",
    body
))
story.append(feature_table([
    ("Email + Password", "Standard credential entry, retried on flaky network."),
    ("2FA Codes (TOTP)", "Codes generated on-the-fly from the secret stored in Excel using pyotp."),
    ("Backup Codes", "Pulled from the per-account backup code columns in Excel."),
    ("Recovery Email Confirm", "Auto-confirms the displayed recovery email from Excel."),
    ("Recovery Phone Confirm", "Same for recovery phone numbers."),
    ("Account Creation Year", "Reads the value from Excel and submits it."),
    ("Forced Password Change", "Accepts the new password prompt and writes the new password back to Excel."),
    ("CAPTCHA / Block Screens", "Detects the block, logs the account safely, and moves on to the next one."),
], header=("Login Screen", "How the Bot Handles It")))

story.append(Spacer(1, 0.4*cm))
story.append(Paragraph(
    "<b>Client benefit:</b> Operators don&rsquo;t babysit logins. The bot handles every Google "
    "challenge screen &mdash; and when something genuinely cannot be solved (like a hard CAPTCHA), "
    "it logs the account and continues rather than crashing the whole batch.",
    body
))

story.append(PageBreak())

# ===== DASHBOARD =====
story.append(Paragraph("Real-Time Dashboard &amp; Reporting", h1))
story.append(Paragraph(
    "Operators get total visibility into every running job. Clients get clean Excel reports.",
    body
))
story.append(feature_table([
    ("Live Statistics",
     "Counters update in real time: Total / Success / Failed / Pending."),
    ("Progress Bar",
     "Percentage-based progress across the whole batch."),
    ("Current Account Indicator",
     "Shows exactly which account is being processed right now."),
    ("Live Terminal Log",
     "Real-time log streaming via Server-Sent Events &mdash; every action is visible as it happens."),
    ("Auto-Generated Reports",
     "After a run, three Excel files are produced: success report, failed report, and a summary report."),
    ("Excel In, Excel Out",
     "No databases, no special software. Clients can read, edit, and hand off the file to anyone."),
]))

story.append(Spacer(1, 0.4*cm))
story.append(Paragraph(
    "<b>Client benefit:</b> Total transparency. They see what worked, what didn&rsquo;t, and exactly "
    "why &mdash; with a clean audit trail in a single Excel file they already know how to use.",
    body
))

story.append(PageBreak())

# ===== EXCEL =====
story.append(Paragraph("Excel-Based Input &amp; Output", h1))
story.append(Paragraph(
    "Everything MailNexus Pro does is driven by a single Excel file with 40+ columns. The bot reads "
    "credentials and instructions from it &mdash; and writes results, new passwords, new 2FA secrets, "
    "backup codes, review share links, and appeal status straight back into the same file.",
    body
))
story.append(feature_table([
    ("Single Source of Truth",
     "One <i>.xlsx</i> file covers every operation across all 4 workflows."),
    ("Per-Account Operations",
     "Each row tells the bot which operations to run for that account (e.g. <i>1,2a,3a,7,8</i>)."),
    ("Auto-Populated Outputs",
     "Status, Operations Done, Error Message, new 2FA Secret, Backup Codes, Review Share Links, Appeal Status &mdash; all written back automatically."),
    ("Thread-Safe Writes",
     "Multiple workers can safely write to the same Excel file at the same time without corruption."),
    ("Auditable &amp; Portable",
     "No database lock-in. Hand the file to a teammate, attach it to an email, archive it &mdash; it&rsquo;s self-contained."),
]))

story.append(PageBreak())

# ===== PERFORMANCE =====
story.append(Paragraph("Performance &mdash; The Real Numbers", h1))
story.append(Paragraph(
    "Concrete time savings for typical workloads. Numbers assume residential proxies and the "
    "default 10-worker configuration on a 4-core / 8GB workstation.",
    body
))
story.append(Spacer(1, 0.3*cm))
story.append(numbers_table([
    ("Single account &mdash; full security run", "10-15 minutes", "2-5 minutes"),
    ("100 accounts &mdash; security hardening", "~25 hours of labor", "~2-4 hours, 1 operator"),
    ("500 Google Maps reviews / month", "1 full-time employee", "~3 evening sessions"),
    ("Bulk appeal submission (50 accounts)", "1 full working day", "~30-40 minutes"),
    ("Password rotation (200 accounts)", "~30 hours", "~3 hours"),
]))

story.append(Spacer(1, 0.6*cm))
story.append(Paragraph("System Requirements", h2))
sys_data = [
    [Paragraph("Component", cell_head),
     Paragraph("Minimum", cell_head),
     Paragraph("Recommended", cell_head)],
    [Paragraph("Operating System", cell_bold), Paragraph("Windows 10", cell), Paragraph("Windows 11", cell)],
    [Paragraph("CPU", cell_bold), Paragraph("2 cores", cell), Paragraph("4+ cores", cell)],
    [Paragraph("RAM", cell_bold), Paragraph("4 GB", cell), Paragraph("8+ GB (for 10 workers)", cell)],
    [Paragraph("Disk", cell_bold), Paragraph("500 MB free", cell), Paragraph("1 GB free", cell)],
    [Paragraph("Internet", cell_bold), Paragraph("Required", cell), Paragraph("Residential proxies recommended", cell)],
]
sys_t = Table(sys_data, colWidths=(5*cm, 5*cm, 7*cm), repeatRows=1)
sys_t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), BG_HEADER),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5E7EB")),
    ("BACKGROUND", (0, 2), (-1, 2), BG_ROW_ALT),
    ("BACKGROUND", (0, 4), (-1, 4), BG_ROW_ALT),
]))
story.append(sys_t)

story.append(PageBreak())

# ===== PITCH =====
story.append(Paragraph("The Bottom-Line Pitch", h1))
story.append(Spacer(1, 0.6*cm))
story.append(Paragraph(
    "<i>&ldquo;Process 100 Gmail accounts in 2-4 hours instead of 2 weeks. Every account gets its own "
    "IP and browser identity so Google can&rsquo;t detect automation. Whether it&rsquo;s security "
    "hardening, posting Google Maps reviews with verified share links, or filing appeals for "
    "suspended accounts &mdash; MailNexus Pro does it in parallel, logs everything, and hands you "
    "back an Excel report you can give to your client.&rdquo;</i>",
    pitch
))

story.append(Spacer(1, 1*cm))
story.append(divider())
story.append(Spacer(1, 0.6*cm))

story.append(Paragraph("Why Clients Win", h2))
story.append(feature_table([
    ("10x Throughput", "Up to 10 accounts processed in parallel &mdash; one operator does the work of a team."),
    ("Zero Babysitting", "Smart login system handles every Google challenge screen automatically."),
    ("Proof of Delivery", "Every Google Maps review comes back with a public share link in Excel."),
    ("Audit Trail", "Auto-generated success / failed / summary Excel reports for every run."),
    ("Account Safety", "Multi-layer anti-detection keeps accounts out of Google&rsquo;s flag systems."),
    ("Plug &amp; Play", "Single Windows installer. No database setup, no command line. Excel in, Excel out."),
]))

story.append(Spacer(1, 0.8*cm))
story.append(divider())
story.append(Spacer(1, 0.6*cm))

story.append(Paragraph("Contact", h2))
contact_data = [
    [Paragraph("Developer", cell_bold), Paragraph("Nishath Khandakar", cell)],
    [Paragraph("Email", cell_bold), Paragraph("nishatbd3388@gmail.com", cell)],
    [Paragraph("Product", cell_bold), Paragraph("MailNexus Pro v1.0.0", cell)],
    [Paragraph("Platform", cell_bold), Paragraph("Windows 10 / 11 Desktop Application", cell)],
]
ct = Table(contact_data, colWidths=(4*cm, 13*cm))
ct.setStyle(TableStyle([
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 6),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ("BACKGROUND", (0, 0), (0, -1), BG_LIGHT),
]))
story.append(ct)

story.append(Spacer(1, 1.5*cm))
story.append(Paragraph(
    "MailNexus Pro is designed for authorized use only on accounts you own or have explicit "
    "written permission to manage. Always use residential proxies and reasonable operation "
    "speeds for production workloads.",
    small_center
))

# ---------------- Build ----------------
doc = SimpleDocTemplate(
    OUTPUT, pagesize=A4,
    leftMargin=2*cm, rightMargin=2*cm,
    topMargin=1.8*cm, bottomMargin=2*cm,
    title="MailNexus Pro - Client Overview",
    author="Nishath Khandakar",
)
doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
print(f"OK: {OUTPUT}")
