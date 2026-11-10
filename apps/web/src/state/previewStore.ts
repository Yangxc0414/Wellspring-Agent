import { create } from "zustand";

export interface PreviewFile {
  id: string;
  name: string;
  path: string;
  size: number;
  type: string;
  lastModified: number;
  file: File;
}

interface PreviewState {
  files: PreviewFile[];
  activeId: string | null;
  open: boolean;
  dock: boolean;
  refreshKey: number;
  addFiles: (files: File[] | FileList) => void;
  addFile: (file: File, path?: string) => void;
  setActive: (id: string) => void;
  step: (delta: number) => void;
  close: () => void;
  show: () => void;
  refresh: () => void;
  clear: () => void;
  toggleDock: () => void;
}

const PREVIEWABLE_EXTENSIONS = new Set([
  "txt", "md", "markdown", "json", "csv", "tsv", "js", "mjs", "cjs", "ts", "tsx", "jsx",
  "py", "java", "c", "h", "cpp", "hpp", "rs", "go", "css", "html", "xml", "yaml", "yml",
  "toml", "ini", "cfg", "log", "sh", "bash", "sql", "tex", "bib", "r", "m", "png", "jpg",
  "jpeg", "gif", "webp", "svg", "bmp", "avif", "pdf"
]);

function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index + 1).toLowerCase() : "";
}

function isPreviewable(file: File): boolean {
  return file.type.startsWith("text/") || file.type.startsWith("image/") ||
    file.type === "application/pdf" || PREVIEWABLE_EXTENSIONS.has(extensionOf(file.name));
}

export const usePreviewStore = create<PreviewState>((set, get) => ({
  files: [],
  activeId: null,
  open: false,
  dock: false,
  refreshKey: 0,
  addFiles: (incoming) => {
    const list = Array.from(incoming)
      .filter((file) => file.size > 0 || isPreviewable(file))
      .map((file) => ({
        file,
        path: (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name
      }));
    if (!list.length) return;
    const existing = get().files;
    const next = [...existing];
    for (const item of list) {
      const id = `${item.path}|${item.file.size}|${item.file.lastModified}`;
      if (!next.some((entry) => entry.id === id)) {
        next.push({
          id,
          name: item.file.name,
          path: item.path,
          size: item.file.size,
          type: item.file.type,
          lastModified: item.file.lastModified,
          file: item.file
        });
      }
    }
    const current = next.find((item) => item.id === get().activeId);
    const preferred = next.find((item) => isPreviewable(item.file)) ?? next[0];
    set({ files: next, activeId: current?.id ?? preferred?.id ?? null, open: true });
  },
  addFile: (file, path) => {
    if (!isPreviewable(file) && file.size === 0) return;
    const resolvedPath = path || file.name;
    const id = `${resolvedPath}|${file.size}|${file.lastModified}`;
    const existing = get().files;
    const next = existing.some((item) => item.id === id)
      ? existing
      : [...existing, {
          id,
          name: file.name,
          path: resolvedPath,
          size: file.size,
          type: file.type,
          lastModified: file.lastModified,
          file
        }];
    set({ files: next, activeId: id, open: true });
  },
  setActive: (id) => {
    if (get().files.some((item) => item.id === id)) set({ activeId: id });
  },
  step: (delta) => {
    const { files, activeId } = get();
    if (!files.length) return;
    const index = Math.max(0, files.findIndex((item) => item.id === activeId));
    const next = Math.min(files.length - 1, Math.max(0, index + delta));
    set({ activeId: files[next].id });
  },
  close: () => set({ open: false }),
  show: () => set({ open: true }),
  refresh: () => set((state) => ({ refreshKey: state.refreshKey + 1 })),
  clear: () => set({ files: [], activeId: null, open: true }),
  toggleDock: () => set((state) => ({ dock: !state.dock }))
}));
