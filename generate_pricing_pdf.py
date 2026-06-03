from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas

WIDTH, HEIGHT = A4

DARK_BG     = colors.HexColor("#0A0E1A")
CARD_BG     = colors.HexColor("#111827")
ACCENT_BLUE = colors.HexColor("#3B82F6")
ACCENT_GOLD = colors.HexColor("#F59E0B")
TEXT_WHITE  = colors.white
TEXT_GRAY   = colors.HexColor("#9CA3AF")
TEXT_LIGHT  = colors.HexColor("#E5E7EB")
GREEN       = colors.HexColor("#10B981")
PURPLE      = colors.HexColor("#8B5CF6")
DIVIDER     = colors.HexColor("#1F2937")

OUTPUT = r"E:\NST Anty Android\MailNexus_Pro_Pricing.pdf"


def bg(c):
    c.setFillColor(DARK_BG)
    c.rect(0, 0, WIDTH, HEIGHT, fill=1, stroke=0)


def top_bar(c, col):
    c.setFillColor(col)
    c.rect(0, HEIGHT - 6, WIDTH, 6, fill=1, stroke=0)


def rrect(c, x, y, w, h, r, fill, stroke=None, sw=1):
    c.setFillColor(fill)
    c.setStrokeColor(stroke if stroke else fill)
    c.setLineWidth(sw)
    c.roundRect(x, y, w, h, r, fill=1, stroke=1 if stroke else 0)


def badge(c, x, y, text, bg_col, fg=colors.white):
    c.setFont("Helvetica-Bold", 7)
    tw = c.stringWidth(text, "Helvetica-Bold", 7)
    pad = 6
    bw = tw + pad * 2
    rrect(c, x, y, bw, 14, 4, bg_col)
    c.setFillColor(fg)
    c.drawString(x + pad, y + 3.5, text)
    return bw


def checkmark(c, x, y):
    c.setFillColor(GREEN)
    c.circle(x + 5, y + 5, 5, fill=1, stroke=0)
    c.setStrokeColor(colors.white)
    c.setLineWidth(1.3)
    c.line(x + 2.5, y + 5, x + 4.5, y + 3)
    c.line(x + 4.5, y + 3, x + 8, y + 8)


def footer(c, page=1):
    c.setFillColor(colors.HexColor("#0D1220"))
    c.rect(0, 0, WIDTH, 48, fill=1, stroke=0)
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.8)
    c.line(0, 48, WIDTH, 48)

    c.setFillColor(ACCENT_BLUE)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(WIDTH / 2, 30, "contact@mailnexuspro.com  |  Limited Licenses Available")

    c.setFillColor(TEXT_GRAY)
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(WIDTH / 2, 14,
        "MailNexus Pro  •  Exclusive Automation Tool  •  No Competitors In Market  •  Prices in USD")

    c.setFillColor(TEXT_GRAY)
    c.setFont("Helvetica", 7)
    c.drawRightString(WIDTH - 20, 6, f"Page {page}")


# ═══════════════════════════════════════════════════════════════
# PAGE 1 — PRICING CARDS
# ═══════════════════════════════════════════════════════════════
def page1(c):
    bg(c)
    top_bar(c, ACCENT_BLUE)

    # Header
    c.setFillColor(TEXT_WHITE)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(WIDTH / 2, HEIGHT - 72, "MailNexus Pro")

    c.setFillColor(ACCENT_BLUE)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawCentredString(WIDTH / 2, HEIGHT - 91,
        "Enterprise Gmail & GMB Automation Platform")

    c.setFillColor(TEXT_GRAY)
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(WIDTH / 2, HEIGHT - 107,
        "Automate bulk Gmail accounts, 2FA, Google Maps reviews & appeals — no competitor in market")

    c.setStrokeColor(DIVIDER)
    c.setLineWidth(1)
    c.line(40, HEIGHT - 118, WIDTH - 40, HEIGHT - 118)

    # Section label
    c.setFillColor(TEXT_WHITE)
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(WIDTH / 2, HEIGHT - 145, "Choose Your Plan")

    c.setFillColor(TEXT_GRAY)
    c.setFont("Helvetica", 8.5)
    c.drawCentredString(WIDTH / 2, HEIGHT - 161,
        "Simple, transparent pricing — pay once or subscribe")

    # ── CARDS ──
    card_w = 228
    gap    = 20
    card_h = 332
    left_x = (WIDTH - (card_w * 2 + gap)) / 2
    right_x = left_x + card_w + gap
    card_y  = (HEIGHT - 161 - 20 - card_h)   # sits just below subtitle

    def draw_card(cx, accent, btext, btitle, subtitle, plans, features, glow=False):
        # glow
        if glow:
            c.setStrokeColor(ACCENT_GOLD)
            c.setLineWidth(2.2)
            c.roundRect(cx - 2, card_y - 2, card_w + 4, card_h + 4, 14, fill=0, stroke=1)

        # shadow
        rrect(c, cx + 3, card_y - 3, card_w, card_h, 12, colors.HexColor("#060A12"))
        # body
        rrect(c, cx, card_y, card_w, card_h, 12, CARD_BG,
              colors.HexColor("#374151") if glow else DIVIDER, 1)
        # top accent
        c.setFillColor(accent)
        c.roundRect(cx, card_y + card_h - 6, card_w, 6, 3, fill=1, stroke=0)

        # badges
        badge(c, cx + 14, card_y + card_h - 37, btext, accent,
              DARK_BG if accent == ACCENT_GOLD else TEXT_WHITE)
        if glow:
            badge(c, cx + 14 + c.stringWidth(btext, "Helvetica-Bold", 7) + 16,
                  card_y + card_h - 37, "MOST POPULAR", PURPLE)

        # title
        c.setFillColor(TEXT_WHITE)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(cx + 14, card_y + card_h - 58, btitle)

        c.setFillColor(TEXT_GRAY)
        c.setFont("Helvetica", 8)
        c.drawString(cx + 14, card_y + card_h - 73, subtitle)

        # divider
        c.setStrokeColor(DIVIDER)
        c.setLineWidth(0.8)
        c.line(cx + 14, card_y + card_h - 82, cx + card_w - 14, card_y + card_h - 82)

        # pricing
        ry = card_y + card_h - 98
        for label, price, suffix, col, best in plans:
            if best:
                rrect(c, cx + 10, ry - 7, card_w - 20, 36, 6, colors.HexColor("#0C2318"))
                badge(c, cx + card_w - 82, ry + 15, "BEST VALUE", GREEN)

            c.setFillColor(TEXT_LIGHT)
            c.setFont("Helvetica", 9)
            c.drawString(cx + 20, ry + 8, label)

            c.setFillColor(col)
            c.setFont("Helvetica-Bold", 18)
            pw = c.stringWidth(price, "Helvetica-Bold", 18)
            c.drawString(cx + 95, ry + 5, price)

            c.setFillColor(TEXT_GRAY)
            c.setFont("Helvetica", 7)
            c.drawString(cx + 95 + pw + 3, ry + 9, suffix)
            ry -= 44

        # divider
        c.setStrokeColor(DIVIDER)
        c.setLineWidth(0.8)
        c.line(cx + 14, ry + 30, cx + card_w - 14, ry + 30)

        # features
        fy = ry + 18
        for feat in features:
            checkmark(c, cx + 16, fy - 2)
            c.setFillColor(TEXT_LIGHT)
            c.setFont("Helvetica", 8)
            c.drawString(cx + 31, fy + 2, feat)
            fy -= 18

    draw_card(
        left_x, ACCENT_BLUE, "SINGLE USER", "Individual", "1 PC License  •  Full Features",
        [
            ("30 Days",  "$99",    "/month",   ACCENT_BLUE, False),
            ("1 Year",   "$499",   "/year",    GREEN,        True),
            ("Lifetime", "$999",   "one-time", ACCENT_GOLD, False),
        ],
        [
            "10 simultaneous accounts",
            "Full Gmail automation",
            "GMB review posting",
            "2FA & recovery setup",
            "Anti-detection engine",
            "1 PC activation",
        ],
        glow=False
    )

    draw_card(
        right_x, ACCENT_GOLD, "AGENCY", "Agency", "Up to 10 PCs  •  Priority Support",
        [
            ("30 Days",  "$249",   "/month",   ACCENT_GOLD, False),
            ("1 Year",   "$1,499", "/year",    GREEN,        True),
            ("Lifetime", "$2,499", "one-time", PURPLE,      False),
        ],
        [
            "Unlimited simultaneous accounts",
            "Full Gmail automation",
            "GMB review & appeal automation",
            "Bulk 2FA & recovery setup",
            "Advanced anti-detection engine",
            "10 PC activations + team seats",
        ],
        glow=True
    )

    # note below cards
    note_y = card_y - 18
    c.setFillColor(TEXT_GRAY)
    c.setFont("Helvetica", 7.5)
    c.drawCentredString(WIDTH / 2, note_y,
        "All plans include lifetime updates during subscription  •  See page 2 for full feature comparison")

    footer(c, page=1)


# ═══════════════════════════════════════════════════════════════
# PAGE 2 — COMPARISON TABLE
# ═══════════════════════════════════════════════════════════════
def page2(c):
    bg(c)
    top_bar(c, ACCENT_GOLD)

    # heading
    c.setFillColor(TEXT_WHITE)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(WIDTH / 2, HEIGHT - 60, "Full Feature Comparison")

    c.setFillColor(TEXT_GRAY)
    c.setFont("Helvetica", 9)
    c.drawCentredString(WIDTH / 2, HEIGHT - 78,
        "Everything you get with each plan")

    c.setStrokeColor(DIVIDER)
    c.setLineWidth(1)
    c.line(40, HEIGHT - 90, WIDTH - 40, HEIGHT - 90)

    # table data
    headers = ["Feature", "Single User", "Agency"]
    rows = [
        ["PC Activations",          "1 PC",          "Up to 10 PCs"],
        ["Simultaneous Accounts",   "10 accounts",   "Unlimited"],
        ["Gmail Automation",        "YES",            "YES"],
        ["Bulk Password Changes",   "YES",            "YES"],
        ["2FA & Recovery Setup",    "YES",            "YES"],
        ["GMB Review Posting",      "YES",            "YES"],
        ["Account Appeals",         "YES",            "YES"],
        ["Anti-Detection Engine",   "Standard",       "Advanced"],
        ["Priority Support",        "Standard",       "24/7 Priority"],
        ["Team Management",         "—",              "YES"],
        ["White-Label Reports",     "—",              "YES"],
        ["Dedicated Account Mgr",   "—",              "YES"],
        ["30-Day Price",            "$99",            "$249"],
        ["1-Year Price",            "$499",           "$1,499"],
        ["Lifetime Price",          "$999",           "$2,499"],
    ]

    col_w = [210, 140, 140]
    tbl_x = (WIDTH - sum(col_w)) / 2
    row_h = 27
    tbl_top = HEIGHT - 108

    # header row
    rrect(c, tbl_x, tbl_top - row_h, sum(col_w), row_h, 6, ACCENT_BLUE)
    x = tbl_x
    for i, h in enumerate(headers):
        c.setFillColor(TEXT_WHITE)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(x + col_w[i] / 2, tbl_top - row_h + 9, h)
        x += col_w[i]

    # data rows
    for ri, row in enumerate(rows):
        ry = tbl_top - row_h * (ri + 2)
        fill = colors.HexColor("#111827") if ri % 2 == 0 else colors.HexColor("#0F1623")
        c.setFillColor(fill)
        c.rect(tbl_x, ry, sum(col_w), row_h, fill=1, stroke=0)

        # separator line
        c.setStrokeColor(DIVIDER)
        c.setLineWidth(0.4)
        c.line(tbl_x, ry, tbl_x + sum(col_w), ry)

        x = tbl_x
        for ci, cell in enumerate(row):
            is_price = cell.startswith("$")
            is_yes   = cell == "YES"
            is_dash  = cell == "—"

            if ci == 0:
                fg = TEXT_GRAY;  font = "Helvetica";      size = 8.5
            elif is_yes:
                fg = GREEN;      font = "Helvetica-Bold"; size = 9
            elif is_dash:
                fg = TEXT_GRAY;  font = "Helvetica";      size = 10
            elif is_price:
                fg = ACCENT_GOLD if ci == 2 else ACCENT_BLUE
                font = "Helvetica-Bold"; size = 9.5
            elif cell in ("Advanced", "24/7 Priority"):
                fg = ACCENT_GOLD; font = "Helvetica-Bold"; size = 8.5
            else:
                fg = TEXT_LIGHT; font = "Helvetica";      size = 8.5

            c.setFillColor(fg)
            c.setFont(font, size)
            c.drawCentredString(x + col_w[ci] / 2, ry + 9, cell)
            x += col_w[ci]

    # outer border
    total_rows = len(rows) + 1
    tbl_bot = tbl_top - row_h * total_rows
    c.setStrokeColor(colors.HexColor("#374151"))
    c.setLineWidth(1)
    c.roundRect(tbl_x, tbl_bot, sum(col_w), row_h * total_rows, 6, fill=0, stroke=1)

    # col dividers
    c.setStrokeColor(DIVIDER)
    c.setLineWidth(0.6)
    x = tbl_x + col_w[0]
    c.line(x, tbl_bot, x, tbl_top)
    x += col_w[1]
    c.line(x, tbl_bot, x, tbl_top)

    # early bird callout
    eb_y = tbl_bot - 36
    rrect(c, tbl_x, eb_y, sum(col_w), 28, 6, colors.HexColor("#0D2B1A"),
          GREEN, 1)
    c.setFillColor(GREEN)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(WIDTH / 2, eb_y + 16,
        "EARLY BIRD OFFER — First 20 Lifetime licenses at special price. Limited time only!")
    c.setFillColor(TEXT_LIGHT)
    c.setFont("Helvetica", 8)
    c.drawCentredString(WIDTH / 2, eb_y + 5,
        "Single User Lifetime: $799  |  Agency Lifetime: $1,999  — contact us to claim")

    footer(c, page=2)


def make_pdf():
    c = canvas.Canvas(OUTPUT, pagesize=A4)
    c.setTitle("MailNexus Pro — Pricing")

    page1(c)
    c.showPage()
    page2(c)

    c.save()
    print(f"Saved: {OUTPUT}")


if __name__ == "__main__":
    make_pdf()
