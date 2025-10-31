import { BrainCircuit } from "lucide-react";


export default function InfoCard() {
  return (
    <section className="info-card-section max-w-2xl mx-auto">
        <div className="info-card bg-slate-800/50 backdrop-blur-sm border border-white/10 rounded-xl p-4 flex items-center justify-center space-x-3">
            <BrainCircuit className="w-6 h-6 text-cyan-400" />
            <p className="text-slate-300 text-sm md:text-base">As previsões são geradas pela nossa IA avançada usando análise estatística..</p>
        </div>
    </section>
  );
}
