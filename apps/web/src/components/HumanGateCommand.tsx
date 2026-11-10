import { useRef, useState } from "react";
import { CLI_ONLY_NOTE } from "../domain/gateCommands";
import { Icon } from "./Icon";

type CopyState = "idle" | "copied" | "selected";

export function GateCommandItem({ command }: { command: string }) {
  const codeRef = useRef<HTMLElement>(null);
  const [state, setState] = useState<CopyState>("idle");

  const selectCommand = () => {
    const node = codeRef.current;
    const selection = window.getSelection?.();
    if (!node || !selection) return false;
    const range = document.createRange();
    range.selectNodeContents(node);
    selection.removeAllRanges();
    selection.addRange(range);
    return true;
  };

  const copy = () => {
    try {
      if (!navigator.clipboard) throw new Error("clipboard unavailable");
      void navigator.clipboard.writeText(command).then(
        () => {
          setState("copied");
          window.setTimeout(() => setState("idle"), 1400);
        },
        () => setState(selectCommand() ? "selected" : "idle")
      );
    } catch {
      setState(selectCommand() ? "selected" : "idle");
    }
  };

  return (
    <div className="human-gate-cmd">
      <pre><code ref={codeRef}>{command}</code></pre>
      <button type="button" className="human-gate-copy" onClick={copy}>
        <Icon name={state === "copied" ? "check" : "copy"} size={11} />
        {state === "copied" ? "已复制" : "复制"}
      </button>
      {state === "selected" && <small>剪贴板不可用；命令已选中，可直接按 Ctrl+C 复制或手动选中复制。</small>}
    </div>
  );
}

export function HumanGateCommand({
  title,
  detail,
  commands,
  note
}: {
  title: string;
  detail: string;
  commands: string[];
  note?: string;
}) {
  return (
    <div className="artifact-next human-gate-command">
      <b>{title}</b>
      <p>{detail}</p>
      {commands.map((command, index) => (
        <GateCommandItem key={`${index}-${command.split("\n")[0]}`} command={command} />
      ))}
      <p>{note ?? CLI_ONLY_NOTE}</p>
    </div>
  );
}
