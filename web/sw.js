// Minimal service worker, so FINN can be installed to a phone's home screen.
// Pages and data always load from the network, so the app is never stale.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
