/**
 * @repo: https://github.com/xiaotuolu/DevSupport-AI
 */
import { Divider, Typography } from "antd";
import Highlight from "./Highlight";

/** 结构化诊断卡片：结论 / 证据 / 建议步骤（引用由外层渲染）。 */
export default function DiagnosisCard({ card }: { card: any }) {
  if (!card) return null;
  return (
    <div>
      {card.conclusion && (
        <div style={{ background: "#f6ffed", border: "1px solid #b7eb8f", borderRadius: 6, padding: "8px 12px" }}>
          <Typography.Text strong style={{ color: "#389e0d" }}>结论：</Typography.Text>
          <Highlight text={card.conclusion} />
        </div>
      )}
      {card.evidence?.length > 0 && (
        <>
          <Divider style={{ margin: "12px 0 8px" }} orientation="left" plain>证据</Divider>
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            {card.evidence.map((e: string, i: number) => (
              <li key={i}><Highlight text={e} /></li>
            ))}
          </ul>
        </>
      )}
      {card.steps?.length > 0 && (
        <>
          <Divider style={{ margin: "12px 0 8px" }} orientation="left" plain>建议步骤</Divider>
          <ol style={{ margin: 0, paddingLeft: 20 }}>
            {card.steps.map((s: string, i: number) => (
              <li key={i} style={{ margin: "3px 0" }}><Highlight text={s} /></li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
