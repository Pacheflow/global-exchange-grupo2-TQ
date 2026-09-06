import React from 'react';
import Navbar from '../components/Navbar';
import { Footer } from '../components/Footer';

export default function HistoricoTasas() {
  return (
    <div className="min-h-screen bg-black text-white font-sans">
      <Navbar />
      <div className="pt-24 pb-20 px-6 max-w-7xl mx-auto">
        <h1 className="text-4xl md:text-5xl font-serif mb-6">Histórico de Tasas</h1>
        <p className="text-zinc-400 mb-12">Consulta la evolución de las tasas de cambio (Datos de demostración).</p>
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
          <div className="text-zinc-400">En desarrollo</div>
        </div>
      </div>
      <Footer />
    </div>
  );
};
