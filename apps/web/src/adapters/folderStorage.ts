import type { PersistedWorkspace } from "../domain/types";

const DB_NAME = "researchAgent.fs";
const DB_STORE = "handles";
const HANDLE_KEY = "workspace-directory";
const WORKSPACE_FILE = "workspace.json";
const META_FILE = "storage.json";

export interface FolderStorageStatus {
  supported: boolean;
  active: boolean;
  folderName: string;
  lastSavedAt: string | null;
  needsPermission: boolean;
  error: string;
}

type Listener = (status: FolderStorageStatus) => void;

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

async function idbGet(): Promise<FileSystemDirectoryHandle | null> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, "readonly");
    const request = tx.objectStore(DB_STORE).get(HANDLE_KEY);
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

async function idbSet(handle: FileSystemDirectoryHandle): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, "readwrite");
    tx.objectStore(DB_STORE).put(handle, HANDLE_KEY);
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

async function idbDelete(): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(DB_STORE, "readwrite");
    tx.objectStore(DB_STORE).delete(HANDLE_KEY);
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

async function permissionState(
  handle: FileSystemDirectoryHandle,
  request: boolean
): Promise<boolean> {
  const options = { mode: "readwrite" as const };
  if (handle.queryPermission) {
    const state = await handle.queryPermission(options);
    if (state === "granted") return true;
    if (!request) return false;
  }
  if (!request) return true;
  if (handle.requestPermission) {
    return (await handle.requestPermission(options)) === "granted";
  }
  return true;
}

async function writeJson(
  handle: FileSystemDirectoryHandle,
  name: string,
  value: unknown
): Promise<void> {
  const file = await handle.getFileHandle(name, { create: true });
  const writable = await file.createWritable();
  await writable.write(JSON.stringify(value, null, 2));
  await writable.close();
}

async function writeSnapshot(
  handle: FileSystemDirectoryHandle,
  snapshot: PersistedWorkspace
): Promise<string> {
  await writeJson(handle, WORKSPACE_FILE, snapshot);
  const savedAt = new Date().toISOString();
  await writeJson(handle, META_FILE, {
    app: "Research Agent",
    schema_version: snapshot.version,
    file: WORKSPACE_FILE,
    saved_at: savedAt,
    note: "Local workspace snapshot; no API keys are written here."
  });
  return savedAt;
}

async function readSnapshot(
  handle: FileSystemDirectoryHandle
): Promise<PersistedWorkspace | null> {
  try {
    const fileHandle = await handle.getFileHandle(WORKSPACE_FILE);
    const text = await (await fileHandle.getFile()).text();
    return JSON.parse(text) as PersistedWorkspace;
  } catch (error) {
    if (error instanceof DOMException && error.name === "NotFoundError") return null;
    throw error;
  }
}

class FolderStorageController {
  status: FolderStorageStatus = {
    supported: typeof window !== "undefined" && typeof window.showDirectoryPicker === "function",
    active: false,
    folderName: "",
    lastSavedAt: null,
    needsPermission: false,
    error: ""
  };

  private handle: FileSystemDirectoryHandle | null = null;
  private lastSnapshot: PersistedWorkspace | null = null;
  private timer: number | null = null;
  private listeners = new Set<Listener>();
  private initPromise: Promise<PersistedWorkspace | null> | null = null;

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(patch: Partial<FolderStorageStatus> = {}): void {
    this.status = { ...this.status, ...patch };
    for (const listener of this.listeners) listener(this.status);
  }

  prime(snapshot: PersistedWorkspace): void {
    this.lastSnapshot = snapshot;
  }

  async init(): Promise<PersistedWorkspace | null> {
    if (this.initPromise) return this.initPromise;
    this.initPromise = this._init();
    return this.initPromise;
  }

  private async _init(): Promise<PersistedWorkspace | null> {
    if (!this.status.supported) {
      this.emit({ supported: false });
      return null;
    }
    try {
      const handle = await idbGet();
      if (!handle) return null;
      this.handle = handle;
      this.emit({ folderName: handle.name, needsPermission: true });
      if (!(await permissionState(handle, false))) {
        this.emit({ needsPermission: true });
        return null;
      }
      this.emit({ active: true, needsPermission: false, error: "" });
      try {
        return await readSnapshot(handle);
      } catch {
        this.emit({ error: "无法读取所选文件夹中的 workspace.json" });
        return null;
      }
    } catch {
      this.emit({ error: "无法恢复文件夹句柄；请重新选择目录" });
      return null;
    }
  }

  async choose(): Promise<string | null> {
    const picker = window.showDirectoryPicker;
    if (!picker) throw new Error("当前浏览器不支持文件夹存储");
    const handle = await picker({
      id: "research-agent-storage",
      mode: "readwrite",
      startIn: "documents"
    });
    if (!(await permissionState(handle, true))) throw new Error("未获得文件夹读写权限");
    this.handle = handle;
    this.emit({ active: true, folderName: handle.name, needsPermission: false, error: "" });
    await idbSet(handle);
    return this.saveNow();
  }

  async restore(): Promise<PersistedWorkspace | null> {
    const handle = this.handle ?? (await idbGet());
    if (!handle) throw new Error("尚未选择文件夹");
    if (!(await permissionState(handle, true))) throw new Error("未获得文件夹读写权限");
    this.handle = handle;
    const snapshot = await readSnapshot(handle);
    this.emit({ active: true, folderName: handle.name, needsPermission: false, error: "" });
    return snapshot;
  }

  async saveNow(): Promise<string | null> {
    if (!this.handle || !this.status.active) return null;
    if (!this.lastSnapshot) return null;
    try {
      if (!(await permissionState(this.handle, false))) {
        this.emit({ needsPermission: true, error: "文件夹权限已失效；请重新连接" });
        return null;
      }
      const savedAt = await writeSnapshot(this.handle, this.lastSnapshot);
      this.emit({ lastSavedAt: savedAt, error: "" });
      return savedAt;
    } catch {
      this.emit({ error: "写入本地文件夹失败；请检查权限" });
      return null;
    }
  }

  async disconnect(): Promise<void> {
    if (this.timer !== null) {
      window.clearTimeout(this.timer);
      this.timer = null;
    }
    this.handle = null;
    try {
      await idbDelete();
    } catch {
      /* the on-disk file is never deleted by disconnect */
    }
    this.emit({
      active: false,
      folderName: "",
      lastSavedAt: null,
      needsPermission: false,
      error: ""
    });
  }

  queue(snapshot: PersistedWorkspace): void {
    this.lastSnapshot = snapshot;
    if (!this.status.active || !this.handle) return;
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => {
      this.timer = null;
      void this.saveNow();
    }, 700);
  }
}

export const folderStorage = new FolderStorageController();
export const folderStorageFileName = WORKSPACE_FILE;
