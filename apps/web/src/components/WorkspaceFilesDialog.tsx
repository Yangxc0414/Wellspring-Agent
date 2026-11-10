import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { workspaceFiles } from "../adapters/workspaceFiles";
import type { WorkspaceFileEntry, WorkspaceFileScan } from "../domain/types";
import { formatBytes, isoNow } from "../domain/utils";
import { usePreviewStore } from "../state/previewStore";
import { useWorkspaceStore } from "../state/workspaceStore";
import { Icon } from "./Icon";

const PROJECT_FILES = ["AGENTS.md", "CLAUDE.md", "README.md", "SKILL.md"];

function modified(value: number): string {
  if (!value) return "—";
  const date = new Date(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export function WorkspaceFilesDialog() {
  const open = useWorkspaceStore((state) => state.ui.filesOpen);
  const workspaceId = useWorkspaceStore((state) => state.ui.filesWorkspaceId);
  const workspaces = useWorkspaceStore((state) => state.workspaces);
  const actions = useWorkspaceStore((state) => state.actions);
  const addPreviewFile = usePreviewStore((state) => state.addFile);
  const [scan, setScan] = useState<WorkspaceFileScan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const workspace = workspaces.find((item) => item.id === workspaceId) ?? null;

  useEffect(() => {
    if (!open || !workspaceId) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    workspaceFiles.restore(workspaceId)
      .then((result) => {
        if (cancelled) return;
        setScan(result);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "文件读取失败");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, workspaceId]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") actions.setUI({ filesOpen: false });
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, actions]);

  const filtered = useMemo(() => {
    if (!scan) return [];
    const needle = query.trim().toLowerCase();
    if (!needle) return scan.entries;
    return scan.entries.filter((entry) => entry.path.toLowerCase().includes(needle));
  }, [scan, query]);

  const projectEntries = useMemo(
    () => (scan ? scan.entries.filter((entry) => PROJECT_FILES.includes(entry.name)) : []),
    [scan]
  );

  if (!open || !workspace) return null;

  const adopt = (result: WorkspaceFileScan) => {
    setScan(result);
    setError("");
    actions.updateWorkspaceFolder(workspace.id, {
      name: result.name,
      files: result.entries.length,
      bytes: result.bytes,
      importedAt: isoNow()
    });
  };

  const choose = async () => {
    setError("");
    if (!workspaceFiles.supported) {
      fileInputRef.current?.click();
      return;
    }
    setLoading(true);
    try {
      adopt(await workspaceFiles.choose(workspace.id));
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setError(caught instanceof Error ? caught.message : "文件夹选择失败");
      }
    } finally {
      setLoading(false);
    }
  };

  const onFolderInput = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length) return;
    setLoading(true);
    try {
      adopt(await workspaceFiles.fromFiles(workspace.id, files));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取文件夹失败");
    } finally {
      setLoading(false);
    }
  };

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const result = await workspaceFiles.restore(workspace.id);
      if (result) adopt(result);
      else setError("文件夹句柄已失效；请重新选择");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "重新读取失败");
    } finally {
      setLoading(false);
    }
  };

  const preview = async (entry: WorkspaceFileEntry) => {
    try {
      const file = await workspaceFiles.read(entry);
      addPreviewFile(file, entry.path);
      actions.setUI({ filesOpen: false });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取文件失败");
    }
  };

  return (
    <div
      className="modal-layer files-layer"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) actions.setUI({ filesOpen: false });
      }}
    >
      <section className="modal files-modal" role="dialog" aria-modal="true" aria-label="工作区文件">
        <header className="files-head">
          <div>
            <span className="eyebrow">WORKSPACE / FILES</span>
            <h2>{workspace.name}</h2>
            <p>
              {scan
                ? `${scan.name} · ${scan.entries.length} 个文件 · ${formatBytes(scan.bytes)}${scan.truncated ? " · 已达到扫描上限" : ""}`
                : "只读浏览本地工作区文件；不上传、不写入证据链。"}
            </p>
          </div>
          <div className="files-head-actions">
            <button type="button" className="mini-button" onClick={() => void choose()}>
              <Icon name="folder" size={11} />
              {scan ? "更换文件夹" : "选择文件夹"}
            </button>
            <button type="button" className="mini-button" onClick={() => void refresh()} disabled={!scan || loading}>
              <Icon name="refresh" size={11} />
              刷新
            </button>
            <button type="button" className="icon-button" onClick={() => actions.setUI({ filesOpen: false })} aria-label="关闭工作区文件">
              <Icon name="close" size={14} />
            </button>
          </div>
        </header>

        {loading && <p className="files-empty">读取文件夹索引…</p>}
        {error && <p className="files-empty is-error">{error}</p>}
        {!loading && !scan && !error && (
          <div className="files-empty">
            <Icon name="folder" size={20} />
            <b>还没有关联本地文件夹</b>
            <span>选择一个只读文件夹，浏览项目说明、论文 Markdown、数据和已有产物。浏览器不会上传内容。</span>
            <button type="button" className="solid-button" onClick={() => void choose()}>选择本地文件夹</button>
          </div>
        )}

        {scan && (
          <>
            <div className="files-toolbar">
              <label className="files-search">
                <Icon name="search" size={12} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="按路径搜索文件…"
                  aria-label="搜索工作区文件"
                />
              </label>
              <span>{filtered.length}/{scan.entries.length} files</span>
              {scan.source === "files" && <em>本次会话临时读取；刷新后需重选文件夹</em>}
            </div>

            {projectEntries.length > 0 && (
              <div className="files-project">
                <b>项目说明 / 技能入口</b>
                <div>
                  {projectEntries.map((entry) => (
                    <button key={entry.path} type="button" className="file-chip" onClick={() => void preview(entry)} title={entry.path}>
                      <Icon name="book" size={10} />
                      {entry.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="files-list" role="list" aria-label="工作区文件列表">
              {filtered.map((entry) => (
                <button
                  key={entry.path}
                  type="button"
                  className="file-row"
                  role="listitem"
                  onClick={() => void preview(entry)}
                  title={`预览 ${entry.path}`}
                >
                  <span className="file-row-mark"><Icon name={entry.extension === "md" ? "book" : "tasks"} size={12} /></span>
                  <span className="file-row-copy">
                    <b>{entry.path}</b>
                    <small>{formatBytes(entry.size)} · {modified(entry.lastModified)}</small>
                  </span>
                  <span className="file-row-action">预览</span>
                </button>
              ))}
              {!filtered.length && <p className="files-empty">没有匹配的文件。</p>}
            </div>
            <footer className="files-foot">
              <Icon name="lock" size={10} />
              只读：文件和文本不会自动进入 claim/evidence；预览支持文本、Markdown、JSON、图片与 PDF（文本上限 512KB）。
            </footer>
          </>
        )}

        <input
          ref={fileInputRef}
          type="file"
          multiple
          style={{ display: "none" }}
          onChange={(event) => void onFolderInput(event)}
          {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
        />
      </section>
    </div>
  );
}
