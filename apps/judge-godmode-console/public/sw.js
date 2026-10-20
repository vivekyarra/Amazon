/* DONE/IRL companion service worker: shows Web Push alerts and opens the authenticated app. */
self.addEventListener("push", (event) => {
  let data = { title: "DONE/IRL", body: "Open DONE/IRL to review.", url: "/" };
  try {
    data = { ...data, ...event.data.json() };
  } catch (_) {
    /* keep generic copy */
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      tag: data.tag,
      silent: Boolean(data.silent),
      data: { url: data.url },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin);
  if (url.origin !== self.location.origin) return;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) {
          client.navigate(url.href);
          return client.focus();
        }
      }
      return self.clients.openWindow(url.href);
    }),
  );
});
