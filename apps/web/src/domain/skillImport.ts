import type { Skill } from "./types";

const MAX_SKILL_FILE = 128 * 1024;
const MAX_SKILLS = 50;
const MAX_INSTRUCTIONS = 4000;

export interface SkippedSkill {
  name: string;
  reason: string;
}

export interface SkillImportResult {
  skills: Skill[];
  skipped: SkippedSkill[];
  errors: string[];
}

type DirectoryHandle = FileSystemDirectoryHandle & {
  values(): AsyncIterable<FileSystemFileHandle | FileSystemDirectoryHandle>;
};

function cleanScalar(value: string): string {
  return value
    .trim()
    .replace(/^["']|["']$/g, "")
    .replace(/\s+#.*$/, "")
    .trim();
}

function parseFrontmatter(raw: string): { meta: Record<string, string>; body: string } | null {
  const match = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  if (!match) return null;
  const meta: Record<string, string> = {};
  for (const line of match[1].split(/\r?\n/)) {
    if (!line.trim() || /^\s/.test(line) || line.trim().startsWith("#")) continue;
    const separator = line.indexOf(":");
    if (separator <= 0) continue;
    const key = line.slice(0, separator).trim();
    const value = cleanScalar(line.slice(separator + 1));
    if (key && value) meta[key] = value;
  }
  return { meta, body: raw.slice(match[0].length).trim() };
}

function slug(value: string): string {
  return value
    .toLowerCase()
    .replace(/\s+/g, "-")
    .replace(/[^\w\u4e00-\u9fa5-]/g, "")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");
}

function toolsFrom(meta: Record<string, string>): string[] {
  const raw = meta["allowed-tools"] || meta["allowed_tools"] || meta.tools || "";
  const tools = raw
    .replace(/^\[|\]$/g, "")
    .split(/[,;\s]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  return tools.length ? Array.from(new Set(tools)).slice(0, 12) : ["session.inspect"];
}

function skillId(name: string): string {
  const base = slug(name) || "imported";
  return base.startsWith("skill-") ? base : `skill-${base}`;
}

export function parseSkillMarkdown(
  raw: string,
  fallbackName: string,
  origin?: string
): { skill?: Skill; reason?: string } {
  if (raw.length > MAX_SKILL_FILE) {
    return { reason: "文件超过 128KB；请拆分 references" };
  }
  const parsed = parseFrontmatter(raw);
  const name = cleanScalar(parsed?.meta.name || fallbackName.replace(/\.md$/i, "") || "");
  const description = cleanScalar(parsed?.meta.description || "");
  if (!name) return { reason: "缺少 name" };
  if (!description) return { reason: "缺少 description（触发条件）" };
  const body = parsed?.body || description;
  const instructions = body.length > MAX_INSTRUCTIONS
    ? `${body.slice(0, MAX_INSTRUCTIONS)}\n\n[导入截断：仅保留前 ${MAX_INSTRUCTIONS} 字符]`
    : body;
  return {
    skill: {
      id: skillId(name),
      name,
      description: description.slice(0, 300),
      instructions,
      tools: toolsFrom(parsed?.meta ?? {}),
      activation: "off",
      source: "imported",
      version: cleanScalar(parsed?.meta.version || "0.1.0") || "0.1.0",
      createdAt: new Date().toISOString(),
      origin,
      license: cleanScalar(parsed?.meta.license || "") || undefined
    }
  };
}

function mergeResult(target: SkillImportResult, name: string, item: { skill?: Skill; reason?: string }) {
  if (item.skill) {
    if (target.skills.some((skill) => skill.name === item.skill?.name)) {
      target.skipped.push({ name, reason: "同名 Skill 已存在，跳过" });
    } else {
      target.skills.push(item.skill);
    }
  } else {
    target.skipped.push({ name, reason: item.reason || "无法解析" });
  }
}

export async function parseSkillFiles(files: File[]): Promise<SkillImportResult> {
  const result: SkillImportResult = { skills: [], skipped: [], errors: [] };
  const candidates = files.filter(
    (file) => file.name.toLowerCase() === "skill.md" || file.name.toLowerCase().endsWith(".md")
  );
  for (const file of candidates) {
    if (result.skills.length >= MAX_SKILLS) {
      result.skipped.push({ name: file.name, reason: `最多导入 ${MAX_SKILLS} 个 Skill` });
      continue;
    }
    try {
      const raw = await file.text();
      const relative = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
      mergeResult(result, file.name, parseSkillMarkdown(raw, file.name, relative || file.name));
    } catch (error) {
      result.errors.push(`${file.name}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
  return result;
}

export async function scanSkillDirectory(root: FileSystemDirectoryHandle): Promise<SkillImportResult> {
  const result: SkillImportResult = { skills: [], skipped: [], errors: [] };
  let visited = 0;

  const readCandidate = async (file: FileSystemFileHandle, path: string) => {
    if (result.skills.length >= MAX_SKILLS) return;
    try {
      const raw = await (await file.getFile()).text();
      mergeResult(result, path, parseSkillMarkdown(raw, file.name, path));
    } catch (error) {
      result.errors.push(`${path}: ${error instanceof Error ? error.message : String(error)}`);
    }
  };

  const walk = async (directory: FileSystemDirectoryHandle, depth: number, prefix: string) => {
    if (depth > 4 || visited > 200 || result.skills.length >= MAX_SKILLS) return;
    visited += 1;
    const entries: Array<[string, FileSystemFileHandle | FileSystemDirectoryHandle]> = [];
    try {
      for await (const entry of (directory as DirectoryHandle).values()) {
        entries.push([entry.name, entry]);
      }
    } catch (error) {
      result.errors.push(`${prefix || directory.name}: ${error instanceof Error ? error.message : String(error)}`);
      return;
    }
    const skillFile = entries.find(
      ([name, entry]) => entry.kind === "file" && name.toLowerCase() === "skill.md"
    );
    if (skillFile) {
      await readCandidate(skillFile[1] as FileSystemFileHandle, `${prefix}${skillFile[0]}`);
      return;
    }
    if (depth === 0) {
      for (const [name, entry] of entries) {
        if (entry.kind === "file" && name.toLowerCase().endsWith(".md")) {
          await readCandidate(entry as FileSystemFileHandle, `${prefix}${name}`);
        }
      }
    }
    for (const [name, entry] of entries) {
      if (entry.kind === "directory") {
        await walk(entry as FileSystemDirectoryHandle, depth + 1, `${prefix}${name}/`);
      }
    }
  };

  await walk(root, 0, `${root.name}/`);
  return result;
}
