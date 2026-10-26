"""Draws the complete circuit diagram of the prototype (black and white).
    python3 -m pip install schemdraw
    python3 hardware/docs/schematic.py
Writes docs/figures/mono/hw_schematic.png.
"""
import os

import schemdraw
import schemdraw.elements as elm

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.join(ROOT, "docs", "figures", "mono", "hw_schematic.png")

schemdraw.config(fontsize=11, lw=1.2, color="black")
P = elm.IcPin



def wire(d, a, b, x):
    """Orthogonal wire from a to b with its vertical run at x."""
    d.add(elm.Line().at(a).to((x, a[1])))
    d.add(elm.Line().at((x, a[1])).to((x, b[1])))
    d.add(elm.Line().at((x, b[1])).to(b))


def net(d, at, text, length=0.8, left=True):
    """Short wire ending in a net name (power rails are joined by name)."""
    end = (at[0] - length if left else at[0] + length, at[1])
    d.add(elm.Line().at(at).to(end))
    d.add(elm.Label().at(end).label(text, halign="right" if left else "left", fontsize=11))


def gnd(d, at, dx=0.0, dy=0.5):
    p = (at[0] + dx, at[1])
    if dx:
        d.add(elm.Line().at(at).to(p))
    d.add(elm.Line().at(p).to((p[0], p[1] - dy)))
    d.add(elm.Ground().at((p[0], p[1] - dy)).theta(0))


with schemdraw.Drawing(show=False) as d:
    uno = d.add(elm.Ic(
        pins=[P(name="5V", side="left", slot="7/7"), P(name="3.3V", side="left", slot="6/7"),
              P(name="A0", side="left", slot="4/7"), P(name="A1", side="left", slot="3/7"),
              P(name="A2", side="left", slot="2/7"), P(name="GND", side="left", slot="1/7"),
              P(name="D6", side="right", slot="11/11"),
              P(name="D12", side="right", slot="10/11"), P(name="D11", side="right", slot="9/11"),
              P(name="D5", side="right", slot="8/11"), P(name="D4", side="right", slot="7/11"),
              P(name="D3", side="right", slot="6/11"), P(name="D2", side="right", slot="5/11"),
              P(name="D8", side="right", slot="3/11"), P(name="D9", side="right", slot="1/11"),
              P(name="USB", side="top")],
        edgepadW=2.6, edgepadH=0.6, pinspacing=0.75, leadlen=0.4,
        label="Arduino Uno\n(ATmega328P,\n16 MHz)", lblsize=13))
    net(d, uno["5V"], "+5V")
    net(d, uno["3.3V"], "+3.3V")
    gnd(d, uno.GND, dx=-0.8)
    d.add(elm.Line().at(uno.USB).up(0.8))
    d.add(elm.Label().label("USB, 115,200 baud: power, and data to and from the web app", loc="top", fontsize=11))

    # ---- GY-61 accelerometer on the left
    gy = d.add(elm.Ic(
        pins=[P(name="VCC", side="right", slot="5/5"), P(name="X", side="right", slot="4/5"),
              P(name="Y", side="right", slot="3/5"), P(name="Z", side="right", slot="2/5"),
              P(name="GND", side="right", slot="1/5")],
        edgepadW=1.0, pinspacing=0.75, leadlen=0.4, label="GY-61\nADXL335\n±3 g", lblsize=11)
        .right().at((uno.A0[0] - 5.0, uno.A0[1])).anchor("X"))
    for g, u in (("X", "A0"), ("Y", "A1"), ("Z", "A2")):
        d.add(elm.Line().at(getattr(gy, g)).to(getattr(uno, u)))
    net(d, gy.VCC, "+5V", left=False)
    gnd(d, gy.GND, dx=0.8)

    # ---- JHD162A LCD on the right
    names = ["VSS", "VDD", "V0", "RS", "RW", "E", "D4", "D5", "D6", "D7", "A", "K"]
    nums = [1, 2, 3, 4, 5, 6, 11, 12, 13, 14, 15, 16]
    lcd = d.add(elm.Ic(
        pins=[P(name=n, pin=str(k), side="left", slot=f"{12 - i}/12") for i, (n, k) in enumerate(zip(names, nums))],
        edgepadW=2.4, pinspacing=0.6, leadlen=0.6, label="JHD162A\n16×2 LCD\n4-bit mode\n(pins 7–10\nnot used)", lblsize=11)
        .right().at((uno.D6[0] + 7.5, uno.D6[1] + 0.3)).anchor("pin3"))
    pin = {n: lcd.absanchors[f"pin{k}"] for n, k in zip(names, nums)}
    x0 = uno.D6[0]
    for k, (u, n) in enumerate([("D6", "V0"), ("D12", "RS"), ("D11", "E"), ("D5", "D4"), ("D4", "D5"), ("D3", "D6"), ("D2", "D7")]):
        wire(d, getattr(uno, u), pin[n], x0 + 1.2 + 0.5 * k)
    net(d, pin["VDD"], "+5V", length=1.2)
    for n in ("VSS", "RW"):
        net(d, pin[n], "GND", length=1.2)
    gnd(d, pin["K"], dx=-0.2, dy=0.3)
    r = d.add(elm.Resistor().at(pin["A"]).left(2.0).label("R1 220 Ω", loc="bottom"))
    d.add(elm.Label().at(r.end).label("+5V", halign="right", fontsize=11))

    # ---- Motor driver: low-side MOSFET switch with flyback diode
    gate = uno.D9
    q = d.add(elm.NFet(bulk=False).theta(180).flip().anchor("gate").at((gate[0] + 4.6, gate[1] - 3.6)))
    d.add(elm.Label().at((q.drain[0] + 0.3, q.drain[1] - 0.75)).label("Q1 IRF540", halign="left", fontsize=11))
    wire(d, gate, q.gate, gate[0] + 1.0)
    gnd(d, q.source, dy=0.4)
    d.add(elm.Line().at(q.drain).up(0.6))
    node = d.add(elm.Dot())
    m = d.add(elm.Motor().up().label("M1 coin motor\nR-0476, 3 V", loc="top", ofst=0.3))
    topn = d.add(elm.Dot())
    d.add(elm.Line().up(0.6))
    d.add(elm.Label().label("+3.3V", loc="top", fontsize=11))
    d.add(elm.Line().at(node.end).right(2.0))
    d.add(elm.Diode().up().toy(topn.end).label("D1 1N4007", loc="bottom", ofst=0.3))
    d.add(elm.Line().tox(topn.end))

    # ---- Piezo buzzer
    bz = uno.D8
    sp = d.add(elm.Speaker().right().anchor("in1").at((bz[0] + 1.8, bz[1])).label("BZ1 piezo", loc="top"))
    d.add(elm.Line().at(bz).to(sp.in1))
    net(d, sp.in2, "GND", length=0.3)

    d.save(OUT, dpi=220)
print("saved", OUT)
