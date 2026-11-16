var C='murga-v1',SHELL=['./','index.html','manifest.webmanifest','icon-192.png','icon-512.png'];
self.addEventListener('install',function(e){e.waitUntil(caches.open(C).then(function(c){return c.addAll(SHELL)}));self.skipWaiting()});
self.addEventListener('activate',function(e){e.waitUntil(caches.keys().then(function(k){return Promise.all(k.filter(function(x){return x!==C}).map(function(x){return caches.delete(x)}))}));self.clients.claim()});
self.addEventListener('fetch',function(e){
var u=new URL(e.request.url);if(e.request.method!=='GET'||u.origin!==location.origin)return;
if(u.pathname.endsWith('rates.json')){ // rates: network first, saved copy when offline
e.respondWith(fetch(e.request).then(function(r){var c=r.clone();caches.open(C).then(function(x){x.put(e.request,c)});return r}).catch(function(){return caches.match(e.request)}));return}
e.respondWith(caches.match(e.request).then(function(r){return r||fetch(e.request)}))});
