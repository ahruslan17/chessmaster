export type MoveClassification =
  | "best"
  | "excellent"
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
    label: "Лучший",
    colorClass: "bg-chess-best/30 text-chess-best border-chess-best/50",
    iconSrc: "/icons/star_s.png",
    iconTitle: "Лучший ход",
  },
  excellent: {
    label: "Отличный",
    colorClass: "bg-chess-excellent/30 text-chess-excellent border-chess-excellent/50",
    iconSrc: "/icons/brilliant_ee.png",
    iconTitle: "Отличный ход",
  },
  good: {
    label: "Хороший",
    colorClass: "bg-chess-good/30 text-chess-good border-chess-good/50",
    iconSrc: "/icons/good_e.png",
    iconTitle: "Хороший ход",
  },
  theory: {
    label: "Теория",
    colorClass: "bg-chess-theory/30 text-chess-theory border-chess-theory/50",
    iconSrc: "/icons/knowledge.png",
    iconTitle: "Теоретический ход",
  },
  inaccuracy: {
    label: "Неточность",
    colorClass: "bg-chess-inaccuracy/30 text-chess-inaccuracy border-chess-inaccuracy/50",
    iconSrc: "/icons/inaccuracy_qe.png",
    iconTitle: "Неточность",
  },
  mistake: {
    label: "Ошибка",
    colorClass: "bg-chess-mistake/30 text-chess-mistake border-chess-mistake/50",
    iconSrc: "/icons/mistake_q.png",
    iconTitle: "Ошибка",
  },
  blunder: {
    label: "Зевок",
    colorClass: "bg-chess-blunder/30 text-chess-blunder border-chess-blunder/50",
    iconSrc: "/icons/blunder_qq.png",
    iconTitle: "Зевок",
  },
};

export const CLASSIFICATION_ORDER: MoveClassification[] = [
  "excellent",
  "best",
  "good",
  "theory",
  "inaccuracy",
  "mistake",
  "blunder",
];
