import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import type { ContextAttachment, WorkspaceFolder } from "../domain/types";
import { formatBytes, uid } from "../domain/utils";
import { Icon } from "./Icon";

const MAX_FILES = 500;

type DirectoryHandle = FileSystemDirectoryHandle & {
  values(): AsyncIterable<FileSystemFileHandle | FileSystemDirectoryHandle>;
};

async function scanDirectory(handle: FileSystemDirectoryHandle): Promise<{
  files: number;
  bytes: number;
  truncated: boolean;
}> {
  let files = 0;
  let bytes = 0;
  const queue: FileSystemDirectoryHandle[] = [handle];
  while (queue.length && files < MAX_FILES) {
    const directory = queue.pop() as DirectoryHandle;
    for await (const entry of directory.values()) {
      if (files >= MAX_FILES) break;
      if (entry.kind === "file") {
        const file = await (entry as FileSystemFileHandle).getFile();
        files += 1;
        bytes += file.size;
      } else if (entry.kind === "directory") {
        queue.push(entry as FileSystemDirectoryHandle);
      }
    }
  }
  return { files, bytes, truncated: files >= MAX_FILES };
}

function localFolder(name: string, files: number, bytes: number, truncated = false): ContextAttachment {
  return {
    id: uid("ctx"),
    kind: "folder",
    name,
    source: "local",
    files,
    bytes,
    note: truncated ? `最多扫描 ${MAX_FILES} 个文件` : "本地只读元数据"
  };
}

export function ContextPlus({
  workspaceFolder,
  onAdd,
  onMore
}: {
  workspaceFolder?: WorkspaceFolder;
  onAdd: (items: ContextAttachment[]) => void;
  onMore?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const add = (items: ContextAttachment[]) => {
    if (!items.length) return;
    onAdd(items);
    setOpen(false);
    setError("");
  };

  const chooseFolder = async () => {
    setError("");
    if (!window.showDirectoryPicker) {
      folderInputRef.current?.click();
      return;
    }
    try {
      const handle = await window.showDirectoryPicker({
        id: "research-agent-context",
        mode: "read",
        startIn: "documents"
      });
      const stats = await scanDirectory(handle);
      add([localFolder(handle.name, stats.files, stats.bytes, stats.truncated)]);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(caught instanceof Error ? caught.message : "文件夹选择失败");
    }
  };

  const onFolderInput = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    const relative = (files[0] as File & { webkitRelativePath?: string }).webkitRelativePath ?? "";
    const name = relative.split("/")[0] || "本地文件夹";
    const bytes = files.reduce((sum, file) => sum + file.size, 0);
    add([localFolder(name, files.length, bytes)]);
    event.target.value = "";
  };

  const chooseFiles = () => {
    setError("");
    fileInputRef.current?.click();
  };

  const onFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []).slice(0, 12);
    add(
      files.map((file) => ({
        id: uid("ctx"),
        kind: "file" as const,
        name: file.name,
        source: "local" as const,
        files: 1,
        bytes: file.size,
        note: "本地文件元数据"
      }))
    );
    event.target.value = "";
  };

  const addWorkspaceFolder = () => {
    if (!workspaceFolder) return;
    add([
      {
        id: uid("ctx"),
        kind: "folder",
        name: workspaceFolder.name,
        source: "workspace",
        files: workspaceFolder.files,
        bytes: workspaceFolder.bytes,
        note: "工作区已登记文件夹"
      }
    ]);
  };

  return (
    <div className="context-plus" ref={rootRef}>
      <button
        type="button"
        className={`welcome-add${open ? " is-open" : ""}`}
        onClick={() => setOpen((current) => !current)}
        title="添加上下文：本地文件 / 文件夹 / 工作区文件夹"
        aria-label="添加上下文"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Icon name="plus" size={12} />
      </button>
      <input
        ref={folderInputRef}
        type="file"
        multiple
        style={{ display: "none" }}
        onChange={onFolderInput}
        {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
      />
      <input ref={fileInputRef} type="file" multiple style={{ display: "none" }} onChange={onFileInput} />
      {open && (
        <div className="context-menu" role="menu" aria-label="添加上下文">
          <div className="context-menu-head">
            <span>ADD CONTEXT</span>
            <em>只读元数据</em>
          </div>
          <button type="button" className="context-menu-item" role="menuitem" onClick={() => void chooseFolder()}>
            <Icon name="folder" size={13} />
            <span><b>本地文件夹</b><small>扫描文件数与大小，不读取内容</small></span>
          </button>
          <button type="button" className="context-menu-item" role="menuitem" onClick={chooseFiles}>
            <Icon name="tasks" size={13} />
            <span><b>本地文件</b><small>可多选；只登记名称与大小</small></span>
          </button>
          <button
            type="button"
            className="context-menu-item"
            role="menuitem"
            disabled={!workspaceFolder}
            onClick={addWorkspaceFolder}
          >
            <Icon name="folder" size={13} />
            <span>
              <b>{workspaceFolder ? `工作区 · ${workspaceFolder.name}` : "工作区文件夹"}</b>
              <small>{workspaceFolder ? `${workspaceFolder.files} files · ${formatBytes(workspaceFolder.bytes)}` : "当前工作区没有登记文件夹"}</small>
            </span>
          </button>
          {onMore && (
            <>
              <div className="context-menu-sep" />
              <button type="button" className="context-menu-item" role="menuitem" onClick={() => { setOpen(false); onMore(); }}>
                <Icon name="plus" size={13} />
                <span><b>更多新建选项</b><small>命名 / 领域 / 起始模式</small></span>
              </button>
            </>
          )}
          {error && <p className="context-menu-error">{error}</p>}
        </div>
      )}
    </div>
  );
}
