"""Tiny MLP heads for activity, severity and tremor type, and their JSON export.

The exported JSON is what the phone/watch app runs (`web/js/model.js`). The
forward pass is plain dense layers with ReLU and softmax, so it also maps
directly onto a microcontroller or a watch runtime.
"""
from __future__ import annotations

import json

import numpy as np
from sklearn.neural_network import MLPClassifier

from .dsp import FEATURE_NAMES

INPUT_NAMES = FEATURE_NAMES + ["placement_watch"]


class Scaler:
    def __init__(self, mean, std):
        self.mean = np.asarray(mean, float)
        self.std = np.asarray(std, float)

    @classmethod
    def fit(cls, x):
        std = x.std(0)
        # A constant input (e.g. gyro features on an accelerometer-only sensor)
        # gets unit scale, so tiny float differences at run time stay tiny.
        return cls(x.mean(0), np.where(std < 1e-6, 1.0, std + 1e-9))

    def __call__(self, x):
        return (x - self.mean) / self.std


class Head:
    """A dense ReLU network with a softmax output."""

    def __init__(self, weights, biases, classes):
        self.W = [np.asarray(w, float) for w in weights]
        self.b = [np.asarray(b, float) for b in biases]
        self.classes = list(classes)

    @classmethod
    def train(cls, x, y, classes, hidden=(32, 16), seed=0):
        clf = MLPClassifier(hidden_layer_sizes=hidden, activation="relu", alpha=1e-3,
                            max_iter=600, early_stopping=True, n_iter_no_change=25,
                            random_state=seed)
        clf.fit(x, y)
        W, b = list(clf.coefs_), list(clf.intercepts_)
        if len(clf.classes_) == 2:  # sklearn uses one logistic output for 2 classes
            W[-1] = np.hstack([-W[-1], W[-1]]) / 2.0
            b[-1] = np.hstack([-b[-1], b[-1]]) / 2.0
        assert list(clf.classes_) == list(range(len(classes))), clf.classes_
        return cls(W, b, classes)

    def proba(self, x):
        h = np.atleast_2d(x)
        for i, (w, b) in enumerate(zip(self.W, self.b)):
            h = h @ w + b
            if i < len(self.W) - 1:
                h = np.maximum(h, 0.0)
        h = h - h.max(1, keepdims=True)
        e = np.exp(h)
        return e / e.sum(1, keepdims=True)

    def n_params(self):
        return int(sum(w.size + b.size for w, b in zip(self.W, self.b)))

    def to_json(self):
        return {"classes": self.classes,
                "layers": [{"W": w.round(6).tolist(), "b": b.round(6).tolist()} for w, b in zip(self.W, self.b)]}

    @classmethod
    def from_json(cls, d):
        return cls([l["W"] for l in d["layers"]], [l["b"] for l in d["layers"]], d["classes"])


def save_bundle(path, scaler, heads: dict, conformal: dict, meta: dict):
    bundle = {
        "version": 1,
        "inputs": INPUT_NAMES,
        "scaler": {"mean": scaler.mean.round(8).tolist(), "std": scaler.std.round(8).tolist()},
        "heads": {k: h.to_json() for k, h in heads.items()},
        "conformal": conformal,
        "meta": meta,
    }
    with open(path, "w") as f:
        json.dump(bundle, f, separators=(",", ":"))
    return bundle


def load_bundle(path):
    with open(path) as f:
        d = json.load(f)
    scaler = Scaler(d["scaler"]["mean"], d["scaler"]["std"])
    heads = {k: Head.from_json(v) for k, v in d["heads"].items()}
    return scaler, heads, d
