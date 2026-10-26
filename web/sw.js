// Offline support: network first so updates show up, cache as the fallback.
const CACHE = "tremorsense-v3";
const ASSETS = [
  "./", "index.html", "styles.css", "icon.svg", "manifest.webmanifest", "model/model.json", "model/model_gy61.json",
  "js/app.js", "js/engine.js", "js/dsp.js", "js/model.js", "js/conformal.js", "js/phase.js",
  "js/medcurve.js", "js/sensor.js", "js/simulator.js", "js/haptics.js", "js/store.js", "js/charts.js", "js/serial.js",
  "js/testcases.js",
];

self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS))));
self.addEventListener("activate", (e) =>
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))));
self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
        return res;
      })
      .catch(() => caches.match(e.request)),
  );
});
