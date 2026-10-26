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
    colorClass: "bg-chess-best/15 text-green-900 border-chess-best/50 dark:bg-chess-best/10 dark:text-green-200",
    iconSrc: "/icons/star_s.png",
    iconTitle: "Лучший ход",
  },
  excellent: {
    label: "Отличный",
    colorClass: "bg-chess-excellent/15 text-emerald-900 border-chess-excellent/50 dark:bg-chess-excellent/10 dark:text-emerald-200",
    iconSrc: "/icons/brilliant_ee.png",
    iconTitle: "Отличный ход",
  },
  good: {
    label: "Хороший",
    colorClass: "bg-chess-good/15 text-lime-900 border-chess-good/50 dark:bg-chess-good/10 dark:text-lime-200",
    iconSrc: "/icons/good_e.png",
    iconTitle: "Хороший ход",
  },
  theory: {
    label: "Теория",
    colorClass: "bg-chess-theory/15 text-blue-900 border-chess-theory/50 dark:bg-chess-theory/10 dark:text-blue-200",
    iconSrc: "/icons/knowledge.png",
    iconTitle: "Теоретический ход",
  },
  inaccuracy: {
    label: "Неточность",
    colorClass: "bg-chess-inaccuracy/15 text-yellow-900 border-chess-inaccuracy/50 dark:bg-chess-inaccuracy/10 dark:text-yellow-200",
    iconSrc: "/icons/inaccuracy_qe.png",
    iconTitle: "Неточность",
  },
  mistake: {
    label: "Ошибка",
    colorClass: "bg-chess-mistake/15 text-orange-900 border-chess-mistake/50 dark:bg-chess-mistake/10 dark:text-orange-200",
    iconSrc: "/icons/mistake_q.png",
    iconTitle: "Ошибка",
  },
  blunder: {
    label: "Зевок",
    colorClass: "bg-chess-blunder/15 text-red-900 border-chess-blunder/50 dark:bg-chess-blunder/10 dark:text-red-200",
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
