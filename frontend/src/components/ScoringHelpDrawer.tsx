import { useEffect } from "react";

interface ScoringHelpDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ScoringHelpDrawer({ isOpen, onClose }: ScoringHelpDrawerProps) {
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  return (
    <>
      <button
        type="button"
        aria-hidden={!isOpen}
        onClick={onClose}
        className={`fixed inset-0 z-40 bg-black/45 transition ${
          isOpen ? "pointer-events-auto opacity-100" : "pointer-events-none opacity-0"
        }`}
      />

      <aside
        aria-hidden={!isOpen}
        className={`fixed right-0 top-0 z-50 h-full w-full max-w-xl border-l border-stone-300 bg-stone-100 shadow-2xl transition-transform duration-300 dark:border-stone-600 dark:bg-chess-dark ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-stone-300 px-5 py-4 dark:border-stone-600">
            <h2 className="text-base font-semibold text-stone-700 dark:text-stone-100">
              Как считается оценка хода
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-stone-400 px-2 py-1 text-sm text-stone-600 transition hover:bg-stone-200 dark:border-stone-500/50 dark:text-stone-200 dark:hover:bg-stone-600/40"
            >
              Закрыть
            </button>
          </div>

          <div className="space-y-4 overflow-y-auto px-5 py-4 text-sm text-stone-700 dark:text-stone-300">
            <section className="rounded border border-stone-300 bg-stone-200/60 p-3 dark:border-stone-600 dark:bg-chess-light/30">
              <p className="font-medium text-stone-700 dark:text-stone-200">Принцип</p>
              <p className="mt-2">
                Классификация строится не по сырому <code>cp_loss</code>, а по потере{" "}
                <code>win chance</code> для игрока, который сделал ход.
              </p>
            </section>

            <section className="space-y-2">
              <p className="font-medium text-stone-700 dark:text-stone-200">Шаги расчёта</p>
              <p>1. Движок даёт eval до и после хода (в centipawn, с точки зрения белых).</p>
              <p>
                2. Eval переводится в шанс через логистику:{" "}
                <code>P = 1 / (1 + exp(-0.00368208 * eval_cp))</code>.
              </p>
              <p>3. Для чёрных берётся обратная перспектива (меняется знак eval).</p>
              <p>
                4. Потеря шанса: <code>loss = max(0, P_before - P_after)</code>.
              </p>
              <p>5. По порогам loss определяется класс хода.</p>
            </section>

            <section className="space-y-2">
              <p className="font-medium text-stone-700 dark:text-stone-200">Пороги</p>
              <p>
                <code>excellent</code>: loss ≤ 0.005 (редкий, почти компьютерный ход)
              </p>
              <p>
                <code>best</code>: 0.005 &lt; loss ≤ 0.02
              </p>
              <p>
                <code>good</code>: 0.02 &lt; loss ≤ 0.05
              </p>
              <p>
                <code>inaccuracy</code>: 0.05 &lt; loss ≤ 0.10
              </p>
              <p>
                <code>mistake</code>: 0.10 &lt; loss ≤ 0.20
              </p>
              <p>
                <code>blunder</code>: loss &gt; 0.20
              </p>
            </section>

            <section className="rounded border border-stone-300 bg-stone-200/60 p-3 dark:border-stone-600 dark:bg-chess-light/30">
              <p className="font-medium text-stone-700 dark:text-stone-200">Особый случай</p>
              <p className="mt-2">
                <code>theory</code> ставится отдельно по дебютной базе (opening book) и
                не зависит от порогов выше.
              </p>
            </section>
          </div>
        </div>
      </aside>
    </>
  );
}
