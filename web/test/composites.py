"""Builds the labelled composite figures used in the IDF from the screenshots
taken by screenshots.mjs and the prototype photos in docs/photos.
    python3 web/test/composites.py
"""
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
SS = os.path.join(ROOT, "docs", "screenshots")
PH = os.path.join(ROOT, "docs", "photos")
FG = os.path.join(ROOT, "docs", "figures", "mono")
HW = os.path.join(ROOT, "hardware", "docs")
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
WHITE = (255, 255, 255)


def load(path):
    return Image.open(path).convert("RGB")


def width(im, w):
    return im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)


def label(im, text, pad=70):
    out = Image.new("RGB", (im.width, im.height + pad), WHITE)
    out.paste(im, (0, 0))
    d = ImageDraw.Draw(out)
    tw = d.textlength(text, font=FONT)
    d.text(((im.width - tw) / 2, im.height + 14), text, fill="black", font=FONT)
    return out


def grid(tiles, cols, gap=30):
    rows = [tiles[i:i + cols] for i in range(0, len(tiles), cols)]
    w = max(sum(t.width for t in r) + gap * (len(r) - 1) for r in rows)
    h = sum(max(t.height for t in r) for r in rows) + gap * (len(rows) - 1)
    out = Image.new("RGB", (w, h), WHITE)
    y = 0
    for r in rows:
        x = 0
        for t in r:
            out.paste(t, (x, y))
            x += t.width + gap
        y += max(t.height for t in r) + gap
    return out


def stack(images, gap=20):
    w = max(i.width for i in images)
    out = Image.new("RGB", (w, sum(i.height for i in images) + gap * (len(images) - 1)), WHITE)
    y = 0
    for i in images:
        out.paste(i, (0, y))
        y += i.height + gap
    return out


def phone(shot, dark=False):
    screen = width(load(shot).crop((0, 0, 1170, 1900)), 760)
    m = 28
    w, h = screen.width + 2 * m, screen.height + 2 * m + 40
    out = Image.new("RGB", (w + 40, h + 20), WHITE)
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((20, 10, 20 + w, 10 + h), radius=70, fill=(28, 30, 30))
    out.paste(screen, (20 + m, 10 + m + 40))
    d.rounded_rectangle((20 + w / 2 - 70, 26, 20 + w / 2 + 70, 44), radius=9, fill=(70, 72, 72))
    return out


def save(im, path):
    im.save(path, optimize=True)
    print("saved", os.path.relpath(path, ROOT), im.size)


s = lambda f: os.path.join(SS, f)

save(grid([label(phone(s("01_home.png")), "(a) Start screen"),
           label(phone(s("02_live_grade2.png")), "(b) Monitoring, grade 2"),
           label(phone(s("14_dark_live.png"), True), "(c) Dark mode, grade 3")], 3), s("composite_phones.png"))

cards = lambda pairs: grid([label(width(load(s(f)), 1100), t) for f, t in pairs], 2)
save(cards([("03_card_grade2_pd.png", "(a) Grade 2, Parkinsonian"), ("04_card_grade4_pd.png", "(b) Grade 4, Parkinsonian"),
            ("05_card_grade3_et.png", "(c) Grade 3, essential tremor"), ("06_card_grade0.png", "(d) No tremor")]),
     s("composite_grades.png"))
save(cards([("07_card_walking.png", "(a) Walking: cues paused"), ("08_card_vehicle.png", "(b) In a bus: cues paused"),
            ("09_card_using_hand.png", "(c) Using the hand: cues paused"), ("11_calibrating.png", "(d) Phase calibration in progress")]),
     s("composite_gating.png"))

case = lambda n: stack([width(load(s(f"{n}_card.png")), 1074), width(load(s(f"{n}_case.png")), 1074)])
save(grid([label(case("19_test_grade4"), "(a) Test 4: severe tremor, cue 4"),
           label(case("20_test_walking"), "(b) Test 6: walking, cues paused")], 2), s("composite_tests.png"))

# Wiring: the LCD on the left, sensor, motor driver and buzzer on the right.
lcd = load(os.path.join(HW, "step1_lcd.png"))
right = stack([load(os.path.join(HW, f)) for f in ("step2_accel.png", "step3_motor.png", "step4_buzzer.png")], gap=40)
right = right.resize((round(right.width * lcd.height / right.height), lcd.height), Image.LANCZOS)
save(grid([label(lcd, "(a) LCD"), label(right, "(b) Accelerometer, motor driver, buzzer")], 2, gap=60),
     os.path.join(FG, "hw_wiring.png"))

# Photos of the prototype, turned upright (the phone was held sideways).
if os.path.isdir(PH):
    p = lambda f: load(os.path.join(PH, f)).rotate(90, expand=True)
    setup = p("prototype_setup.jpg")
    save(width(setup, 2000),
         os.path.join(PH, "fig_prototype.png"))
    lcd_a, lcd_b = p("lcd_test5.jpg"), p("lcd_done.jpg")
    crop = lambda im: width(im.crop((int(im.width * 0.45), int(im.height * 0.04), int(im.width * 0.70), int(im.height * 0.30))), 1100)
    save(grid([label(crop(lcd_a), "(a) Test 5 running: T5 G2 8.0Hz / Cue 2 set 2"),
               label(crop(lcd_b), "(b) All cases done: 7/7 PASS")], 1), os.path.join(PH, "fig_lcd.png"))
