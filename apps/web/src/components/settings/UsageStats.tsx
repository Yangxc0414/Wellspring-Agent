import { useEffect, useMemo, useState } from "react";
import { loadModelCalls } from "../../adapters/runtimeApi";
import type { ModelCallRecord } from "../../adapters/runtimeApi";
import { formatUsageTokens } from "../../domain/catalog";
import { useAllModelProfiles } from "../../state/modelStore";
import type { TokenUsage } from "../../domain/types";
import { isoDateOffset } from "../../domain/utils";
import { selectCurrentTask, useWorkspaceStore } from "../../state/workspaceStore";

const MODEL_COLORS: Record<string, string> = {
  "gpt-5": "#2563eb",
  "claude-sonnet": "#7c3aed",
  "qwen-local": "#0f8a9e"
};

const FALLBACK_COLORS = ["#2563eb", "#7c3aed", "#0f8a9e", "#b45309", "#be123c"];

const ZERO: TokenUsage = { prompt: 0, completion: 0, requests: 0 };
const HEATMAP_WEEKS = 52;

function addUsage(target: TokenUsage, value: TokenUsage): void {
  target.prompt += value.prompt;
  target.completion += value.completion;
  target.requests += value.requests;
}

function dateFromKey(key: string): Date {
  return new Date(`${key}T00:00:00Z`);
}

function keyFromDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function monthDay(key: string): string {
  const date = dateFromKey(key);
  return `${date.getUTCMonth() + 1}/${date.getUTCDate()}`;
}

function longDate(key: string): string {
  const date = dateFromKey(key);
  return `${date.getUTCFullYear()}年${date.getUTCMonth() + 1}月${date.getUTCDate()}日`;
}

function monthDayLong(key: string): string {
  const date = dateFromKey(key);
  return `${date.getUTCMonth() + 1}月${date.getUTCDate()}日`;
}

function heatLevel(value: number, max: number): number {
  if (!value) return 0;
  if (max <= 0) return 1;
  const ratio = value / max;
  if (ratio <= 0.2) return 1;
  if (ratio <= 0.42) return 2;
  if (ratio <= 0.7) return 3;
  return 4;
}

function smoothPath(points: Array<{ x: number; y: number }>, top: number, bottom: number): string {
  if (!points.length) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  const clampY = (value: number) => Math.min(bottom, Math.max(top, value));
  let path = `M ${points[0].x} ${points[0].y}`;
  for (let index = 0; index < points.length - 1; index += 1) {
    const p0 = points[Math.max(index - 1, 0)];
    const p1 = points[index];
    const p2 = points[index + 1];
    const p3 = points[Math.min(index + 2, points.length - 1)];
    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = clampY(p1.y + (p2.y - p0.y) / 6);
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = clampY(p2.y - (p3.y - p1.y) / 6);
    path += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
  }
  return path;
}

interface DayBucket {
  total: number;
  byModel: Record<string, number>;
}

export function UsageStats() {
  const tasks = useWorkspaceStore((state) => state.tasks);
  const currentTask = useWorkspaceStore(selectCurrentTask);
  const profiles = useAllModelProfiles();
  const [range, setRange] = useState<7 | 30>(7);
  const [runtimeCalls, setRuntimeCalls] = useState<ModelCallRecord[]>([]);
  const [runtimeCallError, setRuntimeCallError] = useState("");
  const todayKey = isoDateOffset(0);

  useEffect(() => {
    loadModelCalls()
      .then((calls) => {
        setRuntimeCalls(calls);
        setRuntimeCallError("");
      })
      .catch((error: unknown) => {
        setRuntimeCalls([]);
        setRuntimeCallError(error instanceof Error ? error.message : String(error));
      });
  }, []);

  const callTokens = (call: ModelCallRecord) =>
    Object.values(call.usage ?? {}).reduce(
      (sum, value) => sum + (typeof value === "number" ? value : 0),
      0
    );

  const aggregate = useMemo(() => {
    const totals: Record<string, TokenUsage> = {};
    let requests = 0;
    for (const task of tasks) {
      for (const [profileId, usage] of Object.entries(task.usage ?? {})) {
        const target = totals[profileId] ?? { ...ZERO };
        addUsage(target, usage);
        totals[profileId] = target;
        requests += usage.requests;
      }
    }
    const totalTokens = Object.values(totals).reduce(
      (sum, usage) => sum + usage.prompt + usage.completion,
      0
    );
    return { totals, totalTokens, requests };
  }, [tasks]);

  const daily = useMemo(() => {
    const map = new Map<string, DayBucket>();
    for (let i = 0; i < 366; i += 1) {
      map.set(isoDateOffset(-i), { total: 0, byModel: {} });
    }
    for (const task of tasks) {
      for (const [key, bucket] of Object.entries(task.usageDays ?? {})) {
        const target = map.get(key);
        if (!target) continue;
        for (const [profileId, usage] of Object.entries(bucket)) {
          const tokens = usage.prompt + usage.completion;
          target.total += tokens;
          target.byModel[profileId] = (target.byModel[profileId] ?? 0) + tokens;
        }
      }
    }
    return map;
  }, [tasks]);

  const heatmap = useMemo(() => {
    const today = dateFromKey(todayKey);
    const weekday = (today.getUTCDay() + 6) % 7;
    const start = new Date(today);
    start.setUTCDate(start.getUTCDate() - weekday - (HEATMAP_WEEKS - 1) * 7);
    const cells: Array<{ key: string; value: number; future: boolean }> = [];
    const months: Array<{ key: string; label: string }> = [];
    let lastMonth = start.getUTCMonth();
    for (let week = 0; week < HEATMAP_WEEKS; week += 1) {
      const columnStart = new Date(start);
      columnStart.setUTCDate(start.getUTCDate() + week * 7);
      const month = columnStart.getUTCMonth();
      months.push({
        key: `${week}-${month}`,
        label: week > 0 && month !== lastMonth ? `${month + 1}月` : ""
      });
      lastMonth = month;
      for (let day = 0; day < 7; day += 1) {
        const date = new Date(start);
        date.setUTCDate(start.getUTCDate() + week * 7 + day);
        const key = keyFromDate(date);
        cells.push({
          key,
          value: daily.get(key)?.total ?? 0,
          future: key > todayKey
        });
      }
    }
    const max = Math.max(0, ...cells.filter((cell) => !cell.future).map((cell) => cell.value));
    return { cells, months, max };
  }, [daily, todayKey]);

  const streak = useMemo(() => {
    const keys: string[] = [];
    for (let i = 365; i >= 0; i -= 1) keys.push(isoDateOffset(-i));
    let longest = 0;
    let run = 0;
    for (const key of keys) {
      if ((daily.get(key)?.total ?? 0) > 0) {
        run += 1;
        longest = Math.max(longest, run);
      } else {
        run = 0;
      }
    }
    let current = 0;
    for (let i = 0; i < keys.length; i += 1) {
      if ((daily.get(keys[keys.length - 1 - i])?.total ?? 0) > 0) current += 1;
      else break;
    }
    return { current, longest };
  }, [daily]);

  const rangeDays = useMemo(
    () => Array.from({ length: range }, (_, index) => isoDateOffset(-(range - 1 - index))),
    [range]
  );

  const series = useMemo(
    () => profiles.map((profile, index) => ({
      profile,
      color: MODEL_COLORS[profile.id] ?? FALLBACK_COLORS[index % FALLBACK_COLORS.length],
      values: rangeDays.map((key) => daily.get(key)?.byModel[profile.id] ?? 0)
    })),
    [daily, rangeDays]
  );

  const chart = useMemo(() => {
    const width = 920;
    const height = 230;
    const pad = { left: 38, right: 12, top: 14, bottom: 28 };
    const innerW = width - pad.left - pad.right;
    const innerH = height - pad.top - pad.bottom;
    const valueMax = Math.max(1, ...series.flatMap((item) => item.values));
    const x = (index: number) =>
      pad.left + (rangeDays.length <= 1 ? innerW / 2 : (innerW * index) / (rangeDays.length - 1));
    const y = (value: number) => pad.top + innerH * (1 - value / valueMax);
    const grid = [0, 0.25, 0.5, 0.75, 1].map((ratio) => ({
      ratio,
      y: pad.top + innerH * (1 - ratio),
      value: valueMax * ratio
    }));
    const labelIndices = range <= 7
      ? rangeDays.map((_, index) => index)
      : [0, 5, 10, 15, 20, 25, rangeDays.length - 1].filter((index, position, all) =>
          all.indexOf(index) === position && index < rangeDays.length
        );
    return { width, height, pad, valueMax, x, y, grid, labelIndices };
  }, [range, rangeDays, series]);

  const modelUsage = useMemo(
    () => profiles.map((profile, index) => {
      const usage = aggregate.totals[profile.id] ?? ZERO;
      const tokens = usage.prompt + usage.completion;
      return {
        profile,
        usage,
        tokens,
        share: aggregate.totalTokens ? (tokens / aggregate.totalTokens) * 100 : 0,
        color: MODEL_COLORS[profile.id] ?? FALLBACK_COLORS[index % FALLBACK_COLORS.length]
      };
    }),
    [aggregate]
  );

  const donut = useMemo(() => {
    const radius = 66;
    const circumference = 2 * Math.PI * radius;
    let accumulated = 0;
    const segments = modelUsage
      .filter((item) => item.tokens > 0)
      .map((item) => {
        const length = (item.share / 100) * circumference;
        const segment = {
          ...item,
          dash: Math.max(length - 2, 0.8),
          offset: -(accumulated / 100) * circumference
        };
        accumulated += item.share;
        return segment;
      });
    return { radius, circumference, segments };
  }, [modelUsage]);

  return (
    <div className="settings-section-body usage-page">
      <div className="settings-page-head">
        <div>
          <div className="settings-heading-line">
            <h1>使用统计</h1>
            <span className="settings-tag">应用用量</span>
          </div>
          <p>统计本工作台全部任务的消息与卡片长度估算；不是 API 计费数据。</p>
        </div>
      </div>

      <section className="stats-summary" aria-label="用量概览">
        <div className="summary-card">
          <b>{formatUsageTokens(aggregate.totalTokens)}</b>
          <span>累计 Token 数</span>
          <small>{tasks.length} 个任务</small>
        </div>
        <div className="summary-card">
          <b>{formatUsageTokens(heatmap.max)}</b>
          <span>峰值 Token 数</span>
          <small>单日峰值</small>
        </div>
        <div className="summary-card">
          <b>{aggregate.requests}</b>
          <span>累计请求</span>
          <small>消息级估算</small>
        </div>
        <div className="summary-card">
          <b>{streak.current}<i> 天</i></b>
          <span>当前连续天数</span>
          <small>截至今天</small>
        </div>
        <div className="summary-card">
          <b>{streak.longest}<i> 天</i></b>
          <span>最长连续天数</span>
          <small>过去 12 个月</small>
        </div>
      </section>

      <section className="settings-card heatmap-card">
        <div className="settings-card-head">
          <div>
            <h2>Token 活动</h2>
            <p>每日 token 估算 · 过去 12 个月</p>
          </div>
          <span className="quiet-chip">每日</span>
        </div>
        <div className="heatmap-layout">
          <div className="heatmap-weekdays" aria-hidden="true">
            <span>一</span>
            <span />
            <span>三</span>
            <span />
            <span>五</span>
            <span />
            <span />
          </div>
          <div className="heatmap-scroll">
            <div className="heatmap-months">
              {heatmap.months.map((month) => (
                <span key={month.key}>{month.label}</span>
              ))}
            </div>
            <div className="heatmap-grid" role="img" aria-label="过去 12 个月的每日 token 热力图">
              {heatmap.cells.map((cell) => (
                <span
                  key={cell.key}
                  className={`heatmap-cell level-${cell.future ? 0 : heatLevel(cell.value, heatmap.max)}${cell.key === todayKey ? " is-today" : ""}${cell.future ? " is-future" : ""}`}
                  title={cell.future ? "" : `${longDate(cell.key)} · ${formatUsageTokens(cell.value)} tokens`}
                />
              ))}
            </div>
          </div>
        </div>
        <div className="heatmap-legend">
          <span>少</span>
          {[0, 1, 2, 3, 4].map((level) => <i className={`heatmap-cell level-${level}`} key={level} />)}
          <span>多</span>
          <em>色块 = 当日全部模型输入 + 输出 · 窄屏可横向滑动</em>
        </div>
      </section>

      <div className="settings-range-row">
        <span>时间范围</span>
        <div className="range-switch" role="group" aria-label="趋势时间范围">
          <button type="button" aria-pressed={range === 7} className={range === 7 ? "is-on" : ""} onClick={() => setRange(7)}>近 7 日</button>
          <button type="button" aria-pressed={range === 30} className={range === 30 ? "is-on" : ""} onClick={() => setRange(30)}>近 30 日</button>
        </div>
      </div>

      <section className="settings-card trend-card">
        <div className="settings-card-head">
          <div>
            <h2>每日 Token 趋势图</h2>
            <p>按模型拆分 · 本地估算 · 窄屏可横向滑动</p>
          </div>
        </div>
        <div className="chart-legend">
          {series.map((item) => (
            <span key={item.profile.id}>
              <i style={{ background: item.color }} />
              {item.profile.name}
            </span>
          ))}
        </div>
        <div className="trend-scroll">
          <svg
            className="trend-chart"
            viewBox={`0 0 ${chart.width} ${chart.height}`}
            role="img"
            aria-label="每日 token 趋势图"
          >
            {chart.grid.map((line) => (
              <g key={line.ratio}>
                <line
                  x1={chart.pad.left}
                  x2={chart.width - chart.pad.right}
                  y1={line.y}
                  y2={line.y}
                  className="chart-grid-line"
                />
                {(line.ratio === 0 || line.ratio === 1) && (
                  <text x={chart.pad.left - 6} y={line.y + 3} textAnchor="end" className="chart-axis-label">
                    {formatUsageTokens(Math.round(line.value))}
                  </text>
                )}
              </g>
            ))}
            {series.map((item) => {
              const points = item.values.map((value, index) => ({
                x: chart.x(index),
                y: chart.y(value)
              }));
              const chartTop = chart.pad.top;
              const chartBottom = chart.height - chart.pad.bottom;
              return (
                <g key={item.profile.id}>
                  <path
                    d={smoothPath(points, chartTop, chartBottom)}
                    fill="none"
                    stroke={item.color}
                    strokeWidth="1.8"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                  {item.values.map((value, index) => (
                    value > 0 ? (
                      <circle
                        key={rangeDays[index]}
                        cx={chart.x(index)}
                        cy={chart.y(value)}
                        r="2.2"
                        fill={item.color}
                      >
                        <title>{`${item.profile.short} · ${longDate(rangeDays[index])} · ${formatUsageTokens(value)} tokens`}</title>
                      </circle>
                    ) : null
                  ))}
                </g>
              );
            })}
            {chart.labelIndices.map((index) => (
              <text
                key={rangeDays[index]}
                x={chart.x(index)}
                y={chart.height - 8}
                textAnchor={index === 0 ? "start" : index === rangeDays.length - 1 ? "end" : "middle"}
                className="chart-axis-label"
              >
                {range <= 7 ? monthDayLong(rangeDays[index]) : monthDay(rangeDays[index])}
              </text>
            ))}
          </svg>
        </div>
      </section>

      <section className="settings-card model-usage-card">
        <div className="settings-card-head">
          <div>
            <h2>模型用量</h2>
            <p>累计输入 + 输出 · 全部任务</p>
          </div>
          <span className="quiet-chip">{formatUsageTokens(aggregate.totalTokens)} total</span>
        </div>
        <div className="model-usage-panel">
          <div className="donut-wrap">
            <svg viewBox="0 0 200 200" className="donut-chart" role="img" aria-label="各模型 token 用量占比">
              <circle cx="100" cy="100" r={donut.radius} className="donut-track" strokeWidth="20" fill="none" />
              <g transform="rotate(-90 100 100)">
                {donut.segments.map((segment) => (
                  <circle
                    key={segment.profile.id}
                    cx="100"
                    cy="100"
                    r={donut.radius}
                    stroke={segment.color}
                    strokeWidth="20"
                    fill="none"
                    strokeDasharray={`${segment.dash} ${donut.circumference - segment.dash}`}
                    strokeDashoffset={segment.offset}
                    className="donut-segment"
                  >
                    <title>{`${segment.profile.short} · ${segment.share.toFixed(1)}% · ${formatUsageTokens(segment.tokens)} tokens`}</title>
                  </circle>
                ))}
              </g>
              <text x="100" y="98" textAnchor="middle" className="donut-total">
                {formatUsageTokens(aggregate.totalTokens)}
              </text>
              <text x="100" y="116" textAnchor="middle" className="donut-caption">tokens</text>
            </svg>
          </div>
          <div className="model-legend">
            {modelUsage.map((item) => (
              <div className={`model-legend-row${currentTask?.model.profileId === item.profile.id ? " is-current" : ""}`} key={item.profile.id}>
                <span className="model-legend-name">
                  <i style={{ background: item.color }} />
                  <span>
                    <b>{item.profile.short}</b>
                    <small>{formatUsageTokens(item.tokens)} tokens · {item.usage.requests} req</small>
                  </span>
                </span>
                <span className="model-legend-share">{item.share.toFixed(item.share < 10 ? 1 : 0)}%</span>
              </div>
            ))}
            <p className="model-legend-note">当前任务模型以强调色标记；输入与输出合计计入占比。</p>
          </div>
        </div>
      </section>

      <section className="settings-card">
        <div className="settings-card-head">
          <div>
            <h2>Runtime 模型调用</h2>
            <p>来自 <code>/api/models/calls</code> · 最近 100 条元数据 · 不含 prompt / response / key</p>
          </div>
          <span className="quiet-chip">{runtimeCalls.length} calls</span>
        </div>
        {runtimeCallError ? (
          <p className="settings-empty">runtime 未连接；当前只显示本地估算。{runtimeCallError}</p>
        ) : runtimeCalls.length ? (
          <div className="settings-kv-list">
            {runtimeCalls.slice(0, 8).map((call, index) => (
              <div key={`${call.at}-${call.request_id}-${index}`}>
                <span>{call.ok ? "OK" : "FAIL"} · {call.latency_ms} ms</span>
                <b>{call.model || call.profile_id} · {formatUsageTokens(callTokens(call))} tokens</b>
              </div>
            ))}
          </div>
        ) : (
          <p className="settings-empty">还没有真实模型调用；Probe 或绑定后的 runtime pipeline（planner / writer / idea / experiment / judge）调用后会出现在这里。</p>
        )}
      </section>

      <p className="settings-inline-note">
        本地用量由 <code>usage</code> / <code>usageDays</code> 估算；Runtime 调用是网关返回的真实 usage 元数据。两者分开展示，避免把估算值当成 API 账单。
      </p>
    </div>
  );
}
