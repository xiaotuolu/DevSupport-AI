/**
 * @repo: https://github.com/xiaotuolu/DevSupport-AI
 */
/** 高亮文本中的关键实体：request_id、错误码、接口路径、HTTP 状态码。 */
const PATTERNS: { re: RegExp; color: string; bg: string }[] = [
  { re: /req_[0-9a-zA-Z_]+/g, color: "#0958d9", bg: "#e6f4ff" }, // request_id
  { re: /\/v\d+\/[A-Za-z0-9/_-]+/g, color: "#531dab", bg: "#f9f0ff" }, // 接口路径
  { re: /\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b/g, color: "#ad4e00", bg: "#fff7e6" }, // 错误码
  { re: /\b[1-5]\d{2}\b/g, color: "#cf1322", bg: "#fff1f0" }, // HTTP 状态码
];

interface Seg {
  start: number;
  end: number;
  style: { color: string; bg: string };
}

export default function Highlight({ text }: { text: string }) {
  if (!text) return null;
  const segs: Seg[] = [];
  for (const { re, color, bg } of PATTERNS) {
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text))) {
      const start = m.index;
      const end = start + m[0].length;
      // 避免重叠（前面已标注的区间优先）
      if (!segs.some((s) => start < s.end && end > s.start)) {
        segs.push({ start, end, style: { color, bg } });
      }
    }
  }
  segs.sort((a, b) => a.start - b.start);

  const parts: (string | Seg)[] = [];
  let cursor = 0;
  for (const s of segs) {
    if (s.start > cursor) parts.push(text.slice(cursor, s.start));
    parts.push(s);
    cursor = s.end;
  }
  if (cursor < text.length) parts.push(text.slice(cursor));

  return (
    <>
      {parts.map((p, i) =>
        typeof p === "string" ? (
          <span key={i}>{p}</span>
        ) : (
          <mark
            key={i}
            style={{ color: p.style.color, background: p.style.bg, padding: "0 3px", borderRadius: 3, fontWeight: 600 }}
          >
            {text.slice(p.start, p.end)}
          </mark>
        )
      )}
    </>
  );
}
