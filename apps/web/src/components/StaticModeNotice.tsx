/** Static builds disable the runtime at compile time (vite.config.ts).
 * Before this notice, the workbench silently removed every run/sign control and
 * reported a failed /live request as "start the runtime", which misattributed a
 * build-time limitation to the user. This only discloses the mode; it changes
 * no state, no gate and no command.
 */
export function StaticModeNotice() {
  if (!__STATIC_ONLY__) return null;
  return (
    <div className="static-mode-notice" role="status">
      <strong>静态演示模式</strong>
      <span>
        runtime 已在构建时禁用：真实运行、人工签核与导出只在本地 CLI 可用。claim 人工门面板可复制 CLI 命令、导入已签署的 claim.json，或预览签署后的界面状态（DEMO 预览不产生签名）；页面数值来自快照或本地演示状态，不是研究证据。
      </span>
    </div>
  );
}
