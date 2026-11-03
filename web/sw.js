// Minimal service worker, so FINN can be installed to a phone's home screen.
// Pages and data always load from the network, so the app is never stale.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

// Push: show a notification when the server sends one, even when the app is closed.
self.addEventListener("push", (event) => {
  const data = event.data ? event.data.json() : { title: "FINN", body: "New filing", url: "/" };
  event.waitUntil(self.registration.showNotification(data.title, { body: data.body, data: { url: data.url } }));
});
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(clients.openWindow((event.notification.data && event.notification.data.url) || "/"));
});
