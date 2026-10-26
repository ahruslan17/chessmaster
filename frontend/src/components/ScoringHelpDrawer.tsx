import { useEffect, useRef } from "react";

interface ScoringHelpDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ScoringHelpDrawer({ isOpen, onClose }: ScoringHelpDrawerProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (isOpen && !dialog.open) dialog.showModal();
    else if (!isOpen && dialog.open) dialog.close();
  }, [isOpen]);

  return (
    <dialog
        ref={dialogRef}
        aria-labelledby="scoring-help-title"
        onCancel={onClose}
        onClose={onClose}
        onClick={(event) => {
          if (event.target !== event.currentTarget) return;
          const bounds = event.currentTarget.getBoundingClientRect();
          if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose();
        }}
        className="fixed inset-0 m-0 ml-auto h-dvh max-h-dvh w-full max-w-xl border-l border-stone-300 bg-stone-100 p-0 font-coach text-stone-800 shadow-2xl backdrop:bg-black/45 dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
      >
        <div className="flex h-full flex-col">
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-stone-300 px-5 py-4 dark:border-stone-600">
            <h2 id="scoring-help-title" className="text-base font-semibold text-stone-800 dark:text-stone-100">
              Как читать оценку
            </h2>
            <button
              type="button"
              autoFocus
              onClick={onClose}
              className="min-h-10 rounded border border-stone-400 px-3 py-1 text-sm text-stone-700 transition hover:bg-stone-200 dark:border-stone-500 dark:text-stone-200 dark:hover:bg-stone-600/40"
            >
              Закрыть
            </button>
          </div>

          <div className="min-h-0 space-y-4 overflow-y-auto px-5 py-4 text-sm leading-relaxed text-stone-700 dark:text-stone-200">
            <p>Плюс означает преимущество белых, минус — чёрных. Например, +1.0 — оценка в пользу белых примерно на одну пешку, а не лишняя пешка на доске. Поворот доски не меняет знак.</p>
            <p>Буква M означает найденный движком мат. Знак указывает выигрывающую сторону; число показывает расстояние до мата. Прочерк означает, что оценка недоступна, в том числе при просмотре варианта.</p>
            <p>Метка хода показывает, насколько он ухудшил оценку позиции для сделавшей его стороны. Несколько разных ходов могут получить метку «Лучший». Ход из дебютной базы отмечается отдельно.</p>
            <details>
              <summary className="cursor-pointer py-2 font-medium">Подробности расчёта</summary>
              <div className="mt-2 space-y-4 break-words [&_code]:[overflow-wrap:anywhere]">
                <section className="rounded border border-stone-300 bg-stone-200/60 p-3 dark:border-stone-600 dark:bg-chess-light/30">
                  <p className="font-medium text-stone-700 dark:text-stone-200">Принцип</p>
                  <p className="mt-2">
                    Классификация строится не по сырому <code>cp_loss</code>, а по потере{" "}
                    <code>win chance</code> для игрока, который сделал ход.
                  </p>
                </section>

                <section className="space-y-2">
                  <p className="font-medium text-stone-700 dark:text-stone-200">Шаги расчета</p>
                  <p>1. Движок дает eval до и после хода (в centipawn, с точки зрения белых).</p>
                  <p>
                    2. Eval переводится в шанс через логистику:{" "}
                    <code>P = 1 / (1 + exp(-0.00368208 * eval_cp))</code>.
                  </p>
                  <p>3. Для черных берется обратная перспектива (меняется знак eval).</p>
                  <p>
                    4. Потеря шанса: <code>loss = max(0, P_before - P_after)</code>.
                  </p>
                  <p>5. По порогам loss определяется класс хода.</p>
                  <p>Переход к вынужденному мату соперника отмечается как зевок, потеря своего вынужденного мата — как ошибка, даже если шкала шансов почти не изменилась.</p>
                </section>

                <section className="space-y-2">
                  <p className="font-medium text-stone-700 dark:text-stone-200">Пороги</p>
                  <p>
                    <code>best</code>: loss &lt;= 0.02
                  </p>
                  <p>
                    <code>good</code>: 0.02 &lt; loss &lt;= 0.05
                  </p>
                  <p>
                    <code>inaccuracy</code>: 0.05 &lt; loss &lt;= 0.10
                  </p>
                  <p>
                    <code>mistake</code>: 0.10 &lt; loss &lt;= 0.20
                  </p>
                  <p>
                    <code>blunder</code>: loss &gt; 0.20
                  </p>
                </section>

                <section className="rounded border border-stone-300 bg-stone-200/60 p-3 dark:border-stone-600 dark:bg-chess-light/30">
                  <p className="font-medium text-stone-700 dark:text-stone-200">Ограничения</p>
                  <p className="mt-2">
                    Скачок оценки между поисками не доказывает гениальность хода, поэтому
                    метка <code>excellent</code> автоматически не назначается. Совпадение с
                    дебютной базой не заменяет оценку качества хода.
                  </p>
                </section>
              </div>
            </details>
          </div>
        </div>
      </dialog>
  );
}
