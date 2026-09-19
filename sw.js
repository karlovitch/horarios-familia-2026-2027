const BUILD=75;
const C='horarios-familia-2026-27-v'+BUILD;
const CORE=['./?v='+BUILD,'index.html?v='+BUILD,'manifest.webmanifest?v='+BUILD,'icon.svg'];
const NETWORK_FIRST_PATHS=new Set([
  '/index.html','/manifest.webmanifest','/daily-info.json','/calendar-info.json',
  '/sports-info.json','/history-info.json'
]);

function canonicalCacheKey(url){
  return new Request(url.origin+url.pathname);
}
function isNetworkFirstPath(path){
  for(const suffix of NETWORK_FIRST_PATHS)if(path.endsWith(suffix))return true;
  return false;
}
const OFFLINE_INDEX=new Request(new URL('index.html',self.registration.scope).href);

self.addEventListener('install',event=>{
  self.skipWaiting();
  event.waitUntil(caches.open(C).then(cache=>cache.addAll(CORE)));
});

self.addEventListener('activate',event=>{
  event.waitUntil(
    Promise.all([
      caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==C).map(k=>caches.delete(k)))),
      self.clients.claim()
    ])
  );
});

self.addEventListener('fetch',event=>{
  const req=event.request;
  if(req.method!=='GET')return;
  const url=new URL(req.url);

  // Não interfere com recursos externos (ex.: Passo-a-Rezar).
  if(url.origin!==self.location.origin)return;

  const path=url.pathname;
  const isNavigation=req.mode==='navigate';
  const networkFirst=isNavigation||isNetworkFirstPath(path);

  if(networkFirst){
    const key=canonicalCacheKey(url);
    event.respondWith(
      fetch(req,{cache:'no-store'})
        .then(res=>{
          if(res&&res.ok){
            const copy=res.clone();
            caches.open(C).then(cache=>cache.put(key,copy));
          }
          return res;
        })
        .catch(()=>caches.match(key,{ignoreSearch:true}).then(r=>r||caches.match(OFFLINE_INDEX,{ignoreSearch:true})))
    );
    return;
  }

  event.respondWith(
    caches.match(req).then(cached=>{
      const network=fetch(req).then(res=>{
        if(res&&res.ok){
          const copy=res.clone();
          caches.open(C).then(cache=>cache.put(req,copy));
        }
        return res;
      }).catch(()=>cached);
      return cached||network;
    })
  );
});

self.addEventListener('message',event=>{
  if(event.data&&event.data.type==='SKIP_WAITING')self.skipWaiting();
});
