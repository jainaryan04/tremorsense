// Runs the exported bundle (web/model/model.json): standardise, then dense
// ReLU layers and a softmax for each head. Mirrors ml/tremorsense/model.py.

export class Model {
  constructor(bundle) {
    this.bundle = bundle;
    this.mean = bundle.scaler.mean;
    this.std = bundle.scaler.std;
    this.heads = bundle.heads;
    this.conformal = bundle.conformal;
  }

  static async load(url = "model/model.json") {
    const res = await fetch(url);
    return new Model(await res.json());
  }

  scale(x) {
    return x.map((v, i) => (v - this.mean[i]) / this.std[i]);
  }

  proba(head, xs) {
    let h = xs;
    const layers = this.heads[head].layers;
    layers.forEach((layer, li) => {
      const out = layer.b.slice();
      for (let i = 0; i < h.length; i++) {
        const row = layer.W[i];
        const hi = h[i];
        if (hi === 0) continue;
        for (let j = 0; j < out.length; j++) out[j] += hi * row[j];
      }
      h = li < layers.length - 1 ? out.map((v) => Math.max(v, 0)) : out;
    });
    const m = Math.max(...h);
    const e = h.map((v) => Math.exp(v - m));
    const s = e.reduce((a, b) => a + b, 0);
    return e.map((v) => v / s);
  }

  // features: 19-vector from dsp.features; placementWatch: boolean
  predict(features, placementWatch) {
    const xs = this.scale([...features, placementWatch ? 1 : 0]);
    return {
      activity: this.proba("activity", xs),
      severity: this.proba("severity", xs),
      type: this.proba("type", xs),
    };
  }
}
