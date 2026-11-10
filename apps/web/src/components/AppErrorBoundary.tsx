import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

/** The app has eight lazy panels and no router. Before this boundary, a failed
 * chunk or a render error in any panel produced a blank workspace with no way
 * to tell whether local state had been touched. This only renders a recovery
 * surface: it never writes state, never retries a gate and never hides the error.
 */
interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("workspace render failed", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="app-error-boundary" role="alert">
          <strong>工作台渲染失败</strong>
          <p>这个面板遇到未捕获错误。本地状态未被改动，也没有触发任何门禁或签核；刷新页面即可恢复。</p>
          <code>{this.state.error.message}</code>
          <button type="button" onClick={() => window.location.reload()}>
            重新载入
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
