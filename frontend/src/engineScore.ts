import type { EngineScore } from "./api/types";

export function presentScore(score: EngineScore | null | undefined): { label: string; whitePercent: number; description: string } {
  if (score?.perspective !== "white") {
    return { label: "—", whitePercent: 50, description: "Нет проверенной оценки. Старые числовые оценки не определяют мат или преимущество." };
  }
  if (score.mate != null && Number.isFinite(score.mate)) {
    const winner = score.mate === 0 ? score.mate_winner : score.mate > 0 ? "white" : "black";
    if (!winner) return { label: "—", whitePercent: 50, description: "Мат: победитель неизвестен." };
    return {
      label: `${winner === "white" ? "+" : "−"}M${Math.abs(score.mate)}`,
      whitePercent: winner === "white" ? 100 : 0,
      description: score.mate === 0
        ? `Мат. Победили ${winner === "white" ? "белые" : "чёрные"}.`
        : `Мат в ${Math.abs(score.mate)}. Побеждают ${winner === "white" ? "белые" : "чёрные"}.`,
    };
  }
  if (score.cp != null && Number.isFinite(score.cp)) {
    return {
      label: `${score.cp > 0 ? "+" : ""}${(score.cp / 100).toFixed(1)}`,
      whitePercent: (Math.min(500, Math.max(-500, score.cp)) + 500) / 10,
      description: `Оценка с точки зрения белых: ${(score.cp / 100).toFixed(1)} пешки.`,
    };
  }
  return { label: "—", whitePercent: 50, description: "Оценка недоступна." };
}
