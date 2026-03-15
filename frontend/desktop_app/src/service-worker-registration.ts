async function cleanupServiceWorkersInDev() {
  const registrations = await navigator.serviceWorker.getRegistrations();
  await Promise.all(registrations.map((registration) => registration.unregister()));

  if ('caches' in window) {
    const keys = await caches.keys();
    await Promise.all(keys.map((key) => caches.delete(key)));
  }
}

// Service Worker 注册
export function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) {
    return;
  }

  window.addEventListener('load', () => {
    if (import.meta.env.DEV) {
      cleanupServiceWorkersInDev().then(() => {
        console.log('[PWA] Service Worker disabled and cleaned in development mode');
      }).catch((error) => {
        console.warn('[PWA] Failed to clean Service Worker in development mode:', error);
      });
      return;
    }

    navigator.serviceWorker.register('/sw.js')
      .then((registration) => {
        console.log('[PWA] Service Worker registered with scope:', registration.scope);

        // 检查更新
        registration.addEventListener('updatefound', () => {
          const newWorker = registration.installing;
          if (newWorker) {
            newWorker.addEventListener('statechange', () => {
              if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                console.log('[PWA] New content is available; please refresh.');
              }
            });
          }
        });
      })
      .catch((error) => {
        console.error('[PWA] Service Worker registration failed:', error);
      });
  });
}

// 请求 Service Worker 更新
export function updateServiceWorker() {
  if ('serviceWorker' in navigator && !import.meta.env.DEV) {
    navigator.serviceWorker.getRegistration().then((registration) => {
      if (registration) {
        registration.update().then(() => {
          console.log('[PWA] Service Worker updated');
        });
      }
    });
  }
}

// 检查应用是否已安装
export function isAppInstalled() {
  if ('serviceWorker' in navigator) {
    return navigator.serviceWorker.getRegistration().then((registration) => {
      if (registration && registration.active) {
        return true;
      }
      return false;
    });
  }
  return Promise.resolve(false);
}
