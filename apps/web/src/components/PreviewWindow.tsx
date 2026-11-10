import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { formatBytes } from "../domain/utils";
import { usePreviewStore } from "../state/previewStore";
import { Icon } from "./Icon";
import { RichText } from "./RichText";

const MAX_TEXT_BYTES = 512 * 1024;
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "avif"]);
const MARKDOWN_EXTENSIONS = new Set(["md", "markdown"]);
const TEXT_EXTENSIONS = new Set([
  "txt", "md", "markdown", "json", "csv", "tsv", "js", "mjs", "cjs", "ts", "tsx", "jsx",
  "py", "java", "c", "h", "cpp", "hpp", "rs", "go", "css", "html", "xml", "yaml", "yml",
  "toml", "ini", "cfg", "log", "sh", "bash", "sql", "tex", "bib", "r", "m"
]);

type PreviewContent =
  | { kind: "empty" }
  | { kind: "loading" }
  | { kind: "text" | "markdown"; text: string; truncated: boolean }
  | { kind: "image" | "pdf" | "binary"; url: string }
  | { kind: "error"; message: string };

function extensionOf(name: string): string {
  const index = name.lastIndexOf(".");
  return index >= 0 ? name.slice(index + 1).toLowerCase() : "";
}

export function PreviewWindow() {
  const { files, activeId, open, dock, refreshKey, addFiles, setActive, step, close, refresh, clear, toggleDock } =
    usePreviewStore();
  const active = files.find((item) => item.id === activeId) ?? files[0];
  const activeIndex = active ? files.findIndex((item) => item.id === active.id) : -1;
  const [content, setContent] = useState<PreviewContent>({ kind: "empty" });
  const [copied, setCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!active) {
      setContent({ kind: "empty" });
      return;
    }
    let cancelled = false;
    let objectUrl: string | undefined;
    const extension = extensionOf(active.name);
    const isImage = active.type.startsWith("image/") || IMAGE_EXTENSIONS.has(extension);
    const isPdf = active.type === "application/pdf" || extension === "pdf";
    const isMarkdown = MARKDOWN_EXTENSIONS.has(extension);
    const isJson = extension === "json" || active.type === "application/json";
    const isText = active.type.startsWith("text/") || TEXT_EXTENSIONS.has(extension);

    const load = async () => {
      setContent({ kind: "loading" });
      try {
        if (isImage || isPdf || !isText) {
          objectUrl = URL.createObjectURL(active.file);
          if (isImage) setContent({ kind: "image", url: objectUrl });
          else if (isPdf) setContent({ kind: "pdf", url: objectUrl });
          else setContent({ kind: "binary", url: objectUrl });
          return;
        }
        const truncated = active.size > MAX_TEXT_BYTES;
        let text = await active.file.slice(0, MAX_TEXT_BYTES).text();
        if (isJson && !truncated) {
          try {
            text = JSON.stringify(JSON.parse(text), null, 2);
          } catch {
            /* show the original text when JSON is malformed */
          }
        }
        if (!cancelled) {
          setContent({ kind: isMarkdown ? "markdown" : "text", text, truncated });
        }
      } catch (error) {
        if (!cancelled) setContent({ kind: "error", message: String(error) });
      }
    };
    void load();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [active?.id, refreshKey]);

  if (!open) return null;

  const pick = (event: ChangeEvent<HTMLInputElement>) => {
    addFiles(event.target.files ?? []);
    event.target.value = "";
  };

  const drop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (event.dataTransfer.files.length) addFiles(event.dataTransfer.files);
  };

  const copyPath = async () => {
    if (!active) return;
    try {
      await navigator.clipboard.writeText(`local://${active.path}`);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className="preview-window" role="dialog" aria-label="本地文件预览">
      <header className="preview-chrome">
        <div className="preview-window-title">
          <span className="preview-dots" aria-hidden="true"><i /><i /><i /></span>
          <b>LOCAL PREVIEW</b>
        </div>
        <div className="preview-window-actions">
          <button type="button" className={`preview-icon${dock ? " is-on" : ""}`} onClick={toggleDock} title={dock ? "改为浮动窗" : "停靠到右侧"} aria-label={dock ? "改为浮动窗" : "停靠到右侧"} aria-pressed={dock}>
            <Icon name="panel" size={12} />
          </button>
          <button type="button" className="preview-icon" onClick={() => inputRef.current?.click()} title="选择文件" aria-label="选择文件">
            <Icon name="paperclip" size={13} />
          </button>
          <button type="button" className="preview-icon" onClick={clear} title="清空预览" aria-label="清空预览" disabled={!files.length}>
            <Icon name="trash" size={12} />
          </button>
          <button type="button" className="preview-icon" onClick={close} title="关闭预览" aria-label="关闭预览">
            <Icon name="close" size={13} />
          </button>
        </div>
      </header>

      <div className="preview-address-row">
        <button type="button" className="preview-icon" onClick={() => step(-1)} disabled={activeIndex <= 0} aria-label="上一个文件">
          <span className="preview-back"><Icon name="arrow" size={12} /></span>
        </button>
        <button type="button" className="preview-icon" onClick={() => step(1)} disabled={activeIndex < 0 || activeIndex >= files.length - 1} aria-label="下一个文件">
          <Icon name="arrow" size={12} />
        </button>
        <label className="preview-address" title="浏览器不会暴露绝对路径；这里显示相对路径或文件名">
          <Icon name="lock" size={10} />
          <input readOnly value={active ? `local://${active.path}` : "local://no-file-selected"} aria-label="本地文件地址" />
        </label>
        <button type="button" className="preview-icon" onClick={copyPath} disabled={!active} title={copied ? "已复制" : "复制地址"} aria-label="复制地址">
          <Icon name={copied ? "check" : "copy"} size={12} />
        </button>
        <button type="button" className="preview-icon" onClick={refresh} disabled={!active} title="重新读取" aria-label="重新读取">
          <Icon name="refresh" size={12} />
        </button>
      </div>

      {files.length > 1 && (
        <div className="preview-tabs" role="tablist" aria-label="已选文件">
          {files.map((file) => (
            <button
              key={file.id}
              type="button"
              role="tab"
              aria-selected={file.id === active?.id}
              className={`preview-tab${file.id === active?.id ? " is-on" : ""}`}
              onClick={() => setActive(file.id)}
              title={file.path}
            >
              {file.name}
            </button>
          ))}
        </div>
      )}

      <div className="preview-body" onDragOver={(event) => event.preventDefault()} onDrop={drop}>
        {!active && (
          <div className="preview-empty">
            <Icon name="eye" size={24} />
            <b>选择一个本地文件</b>
            <p>支持文本、Markdown、JSON、代码、图片与 PDF；也可以把文件拖进这个窗口。文件只在浏览器内存中读取，不上传、不持久化。</p>
            <button type="button" className="preview-button primary" onClick={() => inputRef.current?.click()}>
              选择文件
            </button>
          </div>
        )}
        {active && content.kind === "loading" && <div className="preview-empty"><span className="preview-spinner" />读取中…</div>}
        {active && content.kind === "error" && (
          <div className="preview-empty"><b>读取失败</b><p>{content.message}</p></div>
        )}
        {active && content.kind === "text" && (
          <pre className="preview-text">{content.text}</pre>
        )}
        {active && content.kind === "markdown" && (
          <div className="preview-markdown"><RichText text={content.text} /></div>
        )}
        {active && content.kind === "image" && (
          <div className="preview-image-wrap"><img src={content.url} alt={active.name} /></div>
        )}
        {active && content.kind === "pdf" && (
          <iframe className="preview-frame" src={content.url} title={active.name} />
        )}
        {active && content.kind === "binary" && (
          <div className="preview-empty">
            <Icon name="database" size={24} />
            <b>不在浏览器内渲染</b>
            <p>{active.type || "未知类型"} · {formatBytes(active.size)}</p>
            <a className="preview-button" href={content.url} download={active.name}>下载 / 打开文件</a>
          </div>
        )}
        {active && (content.kind === "text" || content.kind === "markdown") && content.truncated && (
          <div className="preview-truncated">文件较大，只显示前 512 KB。</div>
        )}
      </div>

      <footer className="preview-foot">
        <span>LOCAL ONLY · NOT UPLOADED</span>
        <span>{active ? `${formatBytes(active.size)} · ${active.type || extensionOf(active.name) || "unknown"}` : "no file"}</span>
      </footer>

      <input ref={inputRef} type="file" multiple className="folder-input preview-input" onChange={pick} aria-hidden="true" tabIndex={-1} />
    </section>
  );
}
