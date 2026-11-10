import type { WorkspaceFileEntry, WorkspaceFileScan } from "../domain/types";

const DB_NAME = "researchAgent.workspaceFiles";
const DB_STORE = "handles";
const MAX_ENTRIES = 500;
const MAX_DIRECTORIES = 120;
const IGNORED_DIRS = new Set([".git", "node_modules", "__pycache__", ".next", "dist", "build", ".venv", "venv"]);

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(DB_STORE)) {
        request.result.createObjectStore(DB_STORE);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function idbGet(workspaceId: string): Promise<FileSystemDirectoryHandle | null> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, "readonly");
    const request = tx.objectStore(DB_STORE).get(workspaceId);
    request.onsuccess = () => {
      db.close();
      resolve((request.result as FileSystemDirectoryHandle | undefined) ?? null);
    };
    request.onerror = () => {
      db.close();
      reject(request.error);
    };
  });
}

async function idbSet(workspaceId: string, handle: FileSystemDirectoryHandle): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, "readwrite");
    tx.objectStore(DB_STORE).put(handle, workspaceId);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

async function idbDelete(workspaceId: string): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, "readwrite");
    tx.objectStore(DB_STORE).delete(workspaceId);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

async function ensureReadPermission(handle: FileSystemDirectoryHandle): Promise<void> {
  if (!handle.queryPermission && !handle.requestPermission) return;
  const options = { mode: "read" as const };
  if (handle.queryPermission) {
    const state = await handle.queryPermission(options);
    if (state === "granted") return;
  }
  if (handle.requestPermission) {
    const state = await handle.requestPermission(options);
    if (state === "granted") return;
  }
  throw new Error("未获得文件夹读取权限；请重新选择文件夹");
}

function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index + 1).toLowerCase() : "";
}

async function scanHandle(handle: FileSystemDirectoryHandle): Promise<WorkspaceFileScan> {
  await ensureReadPermission(handle);
  const entries: WorkspaceFileEntry[] = [];
  const queue: Array<{ directory: FileSystemDirectoryHandle; prefix: string }> = [
    { directory: handle, prefix: "" }
  ];
  let bytes = 0;
  let visitedDirectories = 0;
  let truncated = false;
  while (queue.length) {
    const item = queue.shift();
    if (!item) break;
    visitedDirectories += 1;
    if (visitedDirectories > MAX_DIRECTORIES) {
      truncated = true;
      break;
    }
    const directory = item.directory as FileSystemDirectoryHandle & {
      values(): AsyncIterable<FileSystemFileHandle | FileSystemDirectoryHandle>;
    };
    for await (const entry of directory.values()) {
      if (entries.length >= MAX_ENTRIES) {
        truncated = true;
        break;
      }
      const path = `${item.prefix}${entry.name}`;
      if (entry.kind === "directory") {
        if (!IGNORED_DIRS.has(entry.name)) {
          queue.push({ directory: entry as FileSystemDirectoryHandle, prefix: `${path}/` });
        }
        continue;
      }
      try {
        const file = await (entry as FileSystemFileHandle).getFile();
        bytes += file.size;
        entries.push({
          path,
          name: entry.name,
          size: file.size,
          lastModified: file.lastModified,
          extension: extensionOf(entry.name),
          handle: entry as FileSystemFileHandle
        });
      } catch {
        // A single unreadable file should not hide the rest of the tree.
      }
    }
    if (truncated) break;
  }
  entries.sort((left, right) => left.path.localeCompare(right.path, "zh-CN"));
  return { name: handle.name, entries, bytes, truncated, source: "handle" };
}

function scanFiles(workspaceId: string, files: File[]): WorkspaceFileScan {
  const entries: WorkspaceFileEntry[] = [];
  let bytes = 0;
  let truncated = false;
  for (const file of files) {
    if (entries.length >= MAX_ENTRIES) {
      truncated = true;
      break;
    }
    const path = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
    bytes += file.size;
    entries.push({
      path,
      name: file.name,
      size: file.size,
      lastModified: file.lastModified,
      extension: extensionOf(file.name),
      file
    });
  }
  entries.sort((left, right) => left.path.localeCompare(right.path, "zh-CN"));
  const name = (entries[0]?.path.split("/")[0] || "本地文件夹").slice(0, 80);
  const result = { name, entries, bytes, truncated, source: "files" as const };
  fallbackCache.set(workspaceId, result);
  return result;
}

const fallbackCache = new Map<string, WorkspaceFileScan>();

export const workspaceFiles = {
  supported: typeof window !== "undefined" && typeof window.showDirectoryPicker === "function",

  async choose(workspaceId: string): Promise<WorkspaceFileScan> {
    if (!window.showDirectoryPicker) throw new Error("当前浏览器不支持文件夹读取；请使用 Chromium");
    const handle = await window.showDirectoryPicker({
      id: "research-agent-workspace-files",
      mode: "read",
      startIn: "documents"
    });
    const scan = await scanHandle(handle);
    fallbackCache.set(workspaceId, scan);
    try {
      await idbSet(workspaceId, handle);
    } catch {
      // Some browsers expose a handle that cannot be structured-cloned; keep
      // the scan for this session and let the user re-select next time.
    }
    return scan;
  },

  async restore(workspaceId: string): Promise<WorkspaceFileScan | null> {
    try {
      const handle = await idbGet(workspaceId);
      if (!handle) return fallbackCache.get(workspaceId) ?? null;
      return scanHandle(handle);
    } catch (caught) {
      if (fallbackCache.has(workspaceId)) return fallbackCache.get(workspaceId) ?? null;
      throw caught;
    }
  },

  async fromFiles(workspaceId: string, files: File[]): Promise<WorkspaceFileScan> {
    return scanFiles(workspaceId, files);
  },

  async read(entry: WorkspaceFileEntry): Promise<File> {
    if (entry.file) return entry.file;
    if (entry.handle) return entry.handle.getFile();
    throw new Error("文件句柄已失效；请重新扫描文件夹");
  },

  async forget(workspaceId: string): Promise<void> {
    fallbackCache.delete(workspaceId);
    await idbDelete(workspaceId);
  },

  fallback(workspaceId: string): WorkspaceFileScan | null {
    return fallbackCache.get(workspaceId) ?? null;
  }
};
