// components/event/IntelligencePanel.tsx
import type { EventDossier } from "@/lib/types";

export default function IntelligencePanel({ event }: { event: EventDossier }) {
  const analysis = event.llm_analysis as Record<string, unknown> | null;

  if (!analysis || Object.keys(analysis).length === 0) {
    return (
      <div className="bg-[#172554] border border-blue-900/50 rounded-xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-sm">✨</span>
          <h2 className="text-xs uppercase tracking-wider text-blue-300 font-semibold">
            AI Intelligence
          </h2>
        </div>
        <p className="text-sm text-blue-200/70">
          AI analysis not yet generated for this event.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-[#172554] border border-blue-900/50 rounded-xl p-5">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-sm">✨</span>
        <h2 className="text-xs uppercase tracking-wider text-blue-300 font-semibold">
          AI Intelligence
        </h2>
      </div>

      <div className="space-y-3">
        {analysis.event_summary && (
          <div>
            <span className="text-[10px] uppercase text-blue-400/70">Summary</span>
            <p className="text-sm text-blue-100 mt-0.5">{String(analysis.event_summary)}</p>
          </div>
        )}

        <div className="grid grid-cols-3 gap-3">
          {analysis.market_effect && (
            <div className="bg-blue-900/30 rounded-lg p-3">
              <span className="text-[10px] uppercase text-blue-400/70">Market</span>
              <p className="text-sm font-medium text-blue-100 mt-0.5">
                {String(analysis.market_effect)}
              </p>
            </div>
          )}
          {analysis.risk_level && (
            <div className="bg-blue-900/30 rounded-lg p-3">
              <span className="text-[10px] uppercase text-blue-400/70">Risk</span>
              <p className="text-sm font-medium text-blue-100 mt-0.5">
                {String(analysis.risk_level).toUpperCase()}
              </p>
            </div>
          )}
          {analysis.confidence && (
            <div className="bg-blue-900/30 rounded-lg p-3">
              <span className="text-[10px] uppercase text-blue-400/70">Confidence</span>
              <p className="text-sm font-medium text-blue-100 mt-0.5">
                {Math.round(Number(analysis.confidence) * 100)}%
              </p>
            </div>
          )}
        </div>

        {analysis.forecast && (
          <div>
            <span className="text-[10px] uppercase text-blue-400/70">Forecast</span>
            <p className="text-sm text-blue-100 mt-0.5">{String(analysis.forecast)}</p>
          </div>
        )}

        {analysis.significance && (
          <div>
            <span className="text-[10px] uppercase text-blue-400/70">Significance</span>
            <p className="text-sm text-blue-100 mt-0.5">{String(analysis.significance)}</p>
          </div>
        )}
      </div>
    </div>
  );
}
