const C='horarios-familia-2026-27-v35';
const CORE=['./?v=35','index.html?v=35','manifest.webmanifest?v=35','icon.svg'];

self.addEventListener('install',event=>{
  self.skipWaiting();
  event.waitUntil(caches.open(C).then(cache=>cache.addAll(CORE)));
});

self.addEventListener('activate',event=>{
  event.waitUntil((async()=>{
    await caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==C).map(k=>caches.delete(k))));
    await self.clients.claim();
    const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
    await Promise.all(windows.map(w=>w.navigate(w.url).catch(()=>null)));
  })());
});

self.addEventListener('fetch',event=>{
  const req=event.request;
  const url=new URL(req.url);

  // HTML/navegação e informação diária: rede primeiro para evitar versões antigas.
  if(req.mode==='navigate' || url.pathname.endsWith('/index.html') || url.pathname.endsWith('/daily-info.json') || url.pathname.endsWith('/calendar-info.json')){
    event.respondWith(
      fetch(req,{cache:'no-store'})
        .then(res=>{
          const copy=res.clone();
          caches.open(C).then(cache=>cache.put(req,copy));
          return res;
        })
        .catch(()=>caches.match(req).then(r=>r||caches.match('index.html')))
    );
    return;
  }

  // Restantes recursos: cache com atualização em segundo plano.
  event.respondWith(
    caches.match(req).then(cached=>{
      const network=fetch(req).then(res=>{
        const copy=res.clone();
        caches.open(C).then(cache=>cache.put(req,copy));
        return res;
      }).catch(()=>cached);
      return cached||network;
    })
  );
});
