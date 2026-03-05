export type MoveClassification =
  | "best"
  | "good"
  | "theory"
  | "inaccuracy"
  | "mistake"
  | "blunder";

type ClassificationMeta = {
  label: string;
  colorClass: string;
  iconSrc: string;
  iconTitle: string;
};

export const CLASSIFICATION_META: Record<MoveClassification, ClassificationMeta> = {
  best: {
    label: "Best",
    colorClass: "bg-chess-best/30 text-chess-best border-chess-best/50",
    iconSrc: "/icons/brilliant_ee.png",
    iconTitle: "Best move",
  },
  good: {
    label: "Good",
    colorClass: "bg-chess-good/30 text-chess-good border-chess-good/50",
    iconSrc: "/icons/good_e.png",
    iconTitle: "Good move",
  },
  theory: {
    label: "Theory",
    colorClass: "bg-chess-theory/30 text-chess-theory border-chess-theory/50",
    iconSrc: "/icons/knowledge.png",
    iconTitle: "Theoretical move",
  },
  inaccuracy: {
    label: "Inaccuracy",
    colorClass: "bg-chess-inaccuracy/30 text-chess-inaccuracy border-chess-inaccuracy/50",
    iconSrc: "/icons/inaccuracy_qe.png",
    iconTitle: "Inaccuracy",
  },
  mistake: {
    label: "Mistake",
    colorClass: "bg-chess-mistake/30 text-chess-mistake border-chess-mistake/50",
    iconSrc: "/icons/mistake_q.png",
    iconTitle: "Mistake",
  },
  blunder: {
    label: "Blunder",
    colorClass: "bg-chess-blunder/30 text-chess-blunder border-chess-blunder/50",
    iconSrc: "/icons/blunder_qq.png",
    iconTitle: "Blunder",
  },
};

export const CLASSIFICATION_ORDER: MoveClassification[] = [
  "best",
  "good",
  "theory",
  "inaccuracy",
  "mistake",
  "blunder",
];
