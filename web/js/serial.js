// The TremorSense Arduino (Uno + GY-61) over USB, through the Web Serial API
// (Chrome or Edge on a laptop). Protocol: hardware/tremorsense_uno/tremorsense_uno.ino.
//
// The Uno samples at exactly 50 Hz and sends raw ADC counts; this turns them
// into gravity-free m/s^2 for the engine. Commands go back for the motor,
// buzzer and LCD.

export const serialSupported = () => typeof navigator !== "undefined" && "serial" in navigator;

// GY-61 (ADXL335): ~0.33 V per g; Uno ADC: 5 V over 1023 counts.
export const MS2_PER_COUNT = 9.81 * (5.0 / 1023) / 0.33;
const FS = 50;
const GRAVITY_HZ = 0.3;

// Converts one line from the Uno. Exported for tests.
export function parseLine(line) {
  const p = line.trim().split(",");
  if (p[0] === "A" && p.length === 4) return { kind: "acc", counts: p.slice(1).map(Number) };
  if (p[0] === "G" && p.length === 6) {
    const [grade, hz100, cm100, moving, cue] = p.slice(1).map(Number);
    return { kind: "uno", grade, freqHz: hz100 / 100, dispCm: cm100 / 100, moving: moving === 1, cue };
  }
  if (p[0] === "H") return { kind: "hello", name: p[1], version: p[2] };
  // The standalone demo sketch (tremorsense_demo) doesn't take app commands.
  if (/^(TremorSense demo|=== Test|Result: |Motor check)/.test(line.trim())) return { kind: "demo" };
  return null;
}

// Counts -> gravity-free acceleration, tracking gravity with a slow low-pass
// (the same 0.3 Hz filter the phone path uses).
export class CountsToAcc {
  constructor() {
    this.g = null;
    this.a = 1 - Math.exp(-2 * Math.PI * GRAVITY_HZ / FS);
  }

  step(counts) {
    const ms2 = counts.map((c) => c * MS2_PER_COUNT);
    if (!this.g) this.g = ms2.slice();
    this.g = this.g.map((v, i) => v + this.a * (ms2[i] - v));
    return ms2.map((v, i) => v - this.g[i]);
  }
}

export class UnoSource {
  constructor(onSample, { onStatus, onUno } = {}) {
    this.onSample = onSample;
    this.onStatus = onStatus || (() => {});
    this.onUno = onUno || (() => {});
    this.port = null;
    this.writer = null;
    this.conv = new CountsToAcc();
    this.samples = 0;
    this.closed = false;
    this.demoSketch = false;
    this.waiters = [];
  }

  // Throws an Error with .reason "cancelled" (no port picked) or "busy"
  // (another program, usually the Arduino IDE's Serial Monitor, has it).
  async start() {
    try {
      this.port = await navigator.serial.requestPort();
    } catch (e) {
      throw Object.assign(new Error("No port picked"), { reason: "cancelled" });
    }
    try {
      await this.port.open({ baudRate: 115200 });
    } catch (e) {
      this.port = null;
      throw Object.assign(new Error(String(e && e.message)), { reason: "busy" });
    }
    const enc = new TextEncoderStream();
    this.writeDone = enc.readable.pipeTo(this.port.writable).catch(() => {});
    this.writer = enc.writable.getWriter();
    // The Uno resets when the port opens. Nothing is sent until it has
    // booted (its hello line, see ready()), so the bootloader never sees our
    // commands; after that the heartbeat keeps it in app mode.
    this.heartbeat = setInterval(() => { if (this.alive) this.send("M,1"); }, 2000);
    this.readLoop();
  }

  get alive() {
    return !!(this.hello || this.samples || this.result);
  }

  // Resolves to "ok" once the TremorSense firmware answers, "demo" if the
  // demo sketch is on the board instead, or "silent" after timeoutMs.
  ready(timeoutMs = 4000) {
    if (this.alive) return Promise.resolve("ok");
    return new Promise((resolve) => {
      const t = setTimeout(() => resolve(this.demoSketch ? "demo" : "silent"), timeoutMs);
      this.waiters.push(() => {
        clearTimeout(t);
        resolve("ok");
      });
    });
  }

  wake() {
    if (this.waiters.length) this.send("M,1");
    this.waiters.splice(0).forEach((f) => f());
  }

  async readLoop() {
    const dec = new TextDecoderStream();
    this.readDone = this.port.readable.pipeTo(dec.writable).catch(() => {});
    this.reader = dec.readable.getReader();
    let buf = "";
    try {
      while (!this.closed) {
        const { value, done } = await this.reader.read();
        if (done) break;
        buf += value;
        let i;
        while ((i = buf.indexOf("\n")) >= 0) {
          const msg = parseLine(buf.slice(0, i));
          buf = buf.slice(i + 1);
          if (!msg) continue;
          if (msg.kind === "acc") {
            this.samples++;
            this.wake();
            this.onSample({ acc: this.conv.step(msg.counts), gyro: [0, 0, 0] });
          } else if (msg.kind === "uno") {
            this.result = msg;   // standalone results: the firmware is running
            this.wake();
            this.onUno(msg);
          } else if (msg.kind === "hello") {
            this.hello = msg;
            this.wake();
          } else if (msg.kind === "demo") {
            this.demoSketch = true;
          }
        }
      }
    } catch (e) {
      if (!this.closed) this.onStatus("The Arduino was disconnected.");
    }
  }

  send(line) {
    if (this.writer) this.writer.write(line + "\n").catch(() => {});
  }

  pulse(duty, ms) {
    this.send(`P,${Math.round(duty)},${Math.round(ms)}`);
  }

  beep(hz, ms) {
    this.send(`B,${Math.round(hz)},${Math.round(ms)}`);
  }

  // LCD lines (16 characters; commas would split the command).
  lcdTop(text) {
    this.send(`T,${text.replace(/,/g, " ").slice(0, 16)}`);
  }

  lcd(text) {
    this.send(`L,${text.replace(/,/g, " ").slice(0, 16)}`);
  }

  async stop() {
    this.closed = true;
    clearInterval(this.heartbeat);
    try {
      this.send("M,0");
      if (this.writer) {
        await this.writer.close();
        await this.writeDone;
      }
      if (this.reader) {
        await this.reader.cancel();
        await this.readDone;
      }
      if (this.port) await this.port.close();
    } catch (e) {
      // Port already gone (unplugged): nothing to close.
    }
    this.port = null;
    this.writer = null;
  }
}
