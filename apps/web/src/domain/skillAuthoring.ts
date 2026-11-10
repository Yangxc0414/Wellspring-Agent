import type { SkillDraft } from "./types";

const CREATE_TRIGGERS = [
  /^\/skill-creator\b/i,
  /^\/skill\s+create\b/i,
  /创建.{0,6}技能/,
  /新建.{0,6}技能/,
  /做一个.{0,6}技能/,
  /帮我.{0,6}技能/,
  /create\s+(?:a\s+)?(?:new\s+)?skill/i
];

function firstMatch(text: string, patterns: RegExp[]): string {
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1]) return match[1].trim();
  }
  return "";
}

function clip(value: string, limit: number): string {
  return value.replace(/\s+/g, " ").trim().slice(0, limit);
}

function clipBlock(value: string, limit: number): string {
  return value.trim().slice(0, limit);
}

function cleanField(value: string): string {
  return value.replace(/[，,。；;：:\s]+$/g, "").trim();
}

export function isSkillCreationIntent(text: string): boolean {
  const normalized = text.trim();
  return Boolean(normalized) && CREATE_TRIGGERS.some((pattern) => pattern.test(normalized));
}

/**
 * Deterministic local draft parser for the static workbench. It intentionally
 * stops at a draft; the human still confirms in the Skills panel. No model
 * call, no filesystem write, no automatic skill activation.
 */
export function skillDraftFromChat(text: string): SkillDraft | null {
  const normalized = text.trim();
  if (!isSkillCreationIntent(normalized)) return null;

  const name = cleanField(firstMatch(normalized, [
    /(?:名称|名字|name)\s*[:：]\s*([^\n，,。；;]+)/i,
    /(?:叫做|叫|名为)\s*([^\n，,。；;]+)/,
    /「([^」]{2,40})」/
  ]));
  const description = cleanField(firstMatch(normalized, [
    /(?:描述|说明|用途|description)\s*[:：]\s*([^，,。；;\n]+)/i,
    /(?:用于|用来|目标是)\s*([^，,。；;\n]+)/
  ]));
  let instructionText = firstMatch(normalized, [
    /(?:指令|步骤|instructions?)\s*[:：]\s*([\s\S]+)/i
  ]);
  const tools = cleanField(firstMatch(normalized, [
    /(?:工具|tools?)\s*[:：]\s*([^。\n]+)/i
  ]));
  instructionText = cleanField(
    instructionText.replace(/(?:工具|tools?)\s*[:：][\s\S]*$/i, "")
  );

  const fallback = normalized
    .replace(/^\/skill-creator\s*/i, "")
    .replace(/^\/skill\s+create\s*/i, "")
    .replace(/创建.{0,6}技能|新建.{0,6}技能|做一个.{0,6}技能|帮我.{0,6}技能/gi, "")
    .trim();
  const safeDescription = clip(description || fallback, 200) || "对话创建的只读检查技能";
  const safeName = clip(name || safeDescription, 40) || "对话技能草稿";
  const parsedTools = tools
    .split(/[,，;；\s]+/)
    .map((item) => cleanField(item))
    .filter(Boolean)
    .slice(0, 12);

  return {
    name: safeName,
    description: safeDescription,
    instructions:
      clipBlock(instructionText, 4000) ||
      `${safeDescription}\n\n1. 读取当前会话上下文；\n2. 按上述目标给出只读检查与下一步建议；\n3. 不调用外部工具、不写 Claim/EA、不绕过人工门。`,
    tools: parsedTools.length ? parsedTools : ["session.inspect"],
    origin: "chat"
  };
}
