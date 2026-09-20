const BUILD=113;
const C='horarios-familia-2026-27-v'+BUILD;
const CORE=['./?v='+BUILD,'index.html?v='+BUILD,'manifest.webmanifest?v='+BUILD,'favicon-64.png?v='+BUILD,'icon-192.png?v='+BUILD,'icon-512.png?v='+BUILD,'icon-maskable-512.png?v='+BUILD,'apple-touch-icon.png?v='+BUILD,'version.json?v='+BUILD,'sports-info.js?v='+BUILD];
const NETWORK_FIRST_PATHS=new Set([
  '/index.html','/manifest.webmanifest','/daily-info.json','/calendar-info.json',
  '/sports-info.json','/sports-info.js','/history-info.json','/version.json'
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
  event.waitUntil((async()=>{
    await caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==C).map(k=>caches.delete(k))));
    await self.clients.claim();
    const clients=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    for(const client of clients)client.postMessage({type:'BUILD_ACTIVATED',build:BUILD});
  })());
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
