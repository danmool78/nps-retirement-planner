// 서비스 워커: 재방문을 빠르게 하고(계산 엔진·패키지 캐시) 오프라인에서도 열리게 한다.
//
// - 버전이 URL 에 박힌 외부 파일(stlite·Pyodide·Pretendard·PyPI 휠)은 내용이 바뀌지 않으므로 캐시 우선.
// - 앱 코드(.py)·policy.json·index.html 은 항상 최신을 받도록 네트워크 우선, 실패하면(오프라인) 캐시.
// - 캐시 구조를 바꿀 때는 VERSION 을 올리면 예전 캐시는 activate 때 지워진다.
const VERSION = "v1";
const APP_CACHE = `app-${VERSION}`;   // 같은 출처(앱 코드·제도값·아이콘)
const LIB_CACHE = `lib-${VERSION}`;   // 외부 라이브러리·패키지(변하지 않는 파일)

const IMMUTABLE_HOSTS = ["cdn.jsdelivr.net", "files.pythonhosted.org"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(APP_CACHE)
      .then((c) => c.addAll(["./", "./index.html", "./manifest.webmanifest", "./icons/icon-192.png"]))
      .catch(() => {})  // 사전 캐시 실패해도 설치는 계속(첫 방문 실사용 중에 채워짐)
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== APP_CACHE && k !== LIB_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function cacheFirst(request) {
  const cache = await caches.open(LIB_CACHE);
  const hit = await cache.match(request);
  if (hit) return hit;
  const res = await fetch(request);
  if (res.ok) cache.put(request, res.clone()).catch(() => {});
  return res;
}

async function networkFirst(request, cacheName = APP_CACHE) {
  const cache = await caches.open(cacheName);
  try {
    const res = await fetch(request);
    // ?v=시각 으로 매번 다른 주소가 되므로, 저장은 쿼리를 뗀 주소로 한다(오프라인 대비 최신본 1개).
    if (res.ok) cache.put(stripQuery(request.url), res.clone()).catch(() => {});
    return res;
  } catch (err) {
    const hit = await cache.match(stripQuery(request.url));
    if (hit) return hit;
    throw err;
  }
}

function stripQuery(url) {
  const u = new URL(url);
  u.search = "";
  return u.toString();
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (url.origin === self.location.origin) {
    event.respondWith(networkFirst(req));
    return;
  }
  // PyPI 패키지 색인(JSON)은 바뀔 수 있으니 네트워크 우선, 오프라인이면 마지막 응답 사용.
  if (url.hostname === "pypi.org") {
    event.respondWith(networkFirst(req, LIB_CACHE));
    return;
  }
  // 버전이 고정된 외부 파일만 캐시 우선. 그 밖의 외부 요청은 손대지 않는다.
  const versioned = /@\d|\/v\d+\.\d+|\/packages\//.test(url.pathname);
  if (IMMUTABLE_HOSTS.includes(url.hostname) && versioned) {
    event.respondWith(cacheFirst(req));
  }
});
