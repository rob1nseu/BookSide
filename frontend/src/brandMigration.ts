// Preserve the previous app's learning position/layout on this browser origin.
export function migrateBrandStorage(storage: Storage) {
  if (storage.getItem("bookside:brand-migrated")) return;
  for (const key of Object.keys(storage)) {
    if (!key.startsWith("learnest")) continue;
    const next = "bookside" + key.slice("learnest".length);
    if (storage.getItem(next) === null) storage.setItem(next, storage.getItem(key)!);
  }
  storage.setItem("bookside:brand-migrated", "1");
}
