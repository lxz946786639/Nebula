const CACHE_VERSION = "v1.1.0";
const CORE_CACHE = `nebula-core-${CACHE_VERSION}`;
const RUNTIME_CACHE = `nebula-runtime-${CACHE_VERSION}`;
const INDEX_URL = "/index.html";

const CORE_ASSETS = [
  "/",
  INDEX_URL,
  "/offline.html",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/maskable-192.png",
  "/icons/maskable-512.png",
  "/icons/apple-touch-icon.png",
];

function isSameOrigin(requestUrl) {
  return requestUrl.origin === self.location.origin;
}

function isBackendRequest(requestUrl) {
  return requestUrl.pathname === "/api" || requestUrl.pathname.startsWith("/api/") || requestUrl.pathname === "/health";
}

function isStaticAsset(requestUrl) {
  return (
    requestUrl.pathname.startsWith("/assets/") ||
    requestUrl.pathname.startsWith("/icons/") ||
    requestUrl.pathname === "/manifest.webmanifest" ||
    requestUrl.pathname === "/offline.html"
  );
}

function extractStaticAssetUrls(html) {
  const urls = new Set();
  for (const match of html.matchAll(/(?:href|src)=["']([^"']+)["']/g)) {
    const url = new URL(match[1], self.location.origin);
    if (isSameOrigin(url) && isStaticAsset(url)) {
      urls.add(`${url.pathname}${url.search}`);
    }
  }
  return [...urls];
}

async function precacheCoreAssets() {
  const cache = await caches.open(CORE_CACHE);
  await cache.addAll(CORE_ASSETS);

  const indexResponse = await fetch(INDEX_URL, { cache: "reload" });
  if (!indexResponse.ok) return;

  await cache.put(INDEX_URL, indexResponse.clone());
  await cache.put("/", indexResponse.clone());
  const indexHtml = await indexResponse.text();
  const staticAssets = extractStaticAssetUrls(indexHtml);
  if (staticAssets.length > 0) {
    await cache.addAll(staticAssets);
  }
}

self.addEventListener("install", (event) => {
  event.waitUntil(precacheCoreAssets().then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => ![CORE_CACHE, RUNTIME_CACHE].includes(key)).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const requestUrl = new URL(request.url);
  if (!isSameOrigin(requestUrl) || isBackendRequest(requestUrl)) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(async () => {
          return (await caches.match(request)) || (await caches.match(INDEX_URL)) || caches.match("/offline.html");
        }),
    );
    return;
  }

  if (isStaticAsset(requestUrl)) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        if (cachedResponse) return cachedResponse;
        return fetch(request).then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        });
      }),
    );
  }
});
