import React, { useState, useRef } from 'react';
import { Campaign, Sponsor, AdFormat, AdsSubTab } from '../types';
import { Plus, Power, CloudUpload, Image as ImageIcon, Volume2, Sparkles, ChevronRight, Play, Pause, SkipBack, SkipForward, Shuffle, Repeat, Trash2, Edit3, ExternalLink } from 'lucide-react';

interface AdsTabProps {
  campaigns: Campaign[];
  sponsors: Sponsor[];
  globalKillSwitch: boolean;
  onSaveCampaign: (campaign: Campaign) => void;
  onToggleCampaignActive: (id: string) => void;
  onDeleteCampaign: (id: string) => void;
  onSaveSponsor: (sponsor: Sponsor) => void;
  onDeleteSponsor: (id: string) => void;
  initialSubTab?: AdsSubTab;
}

export const AdsTab: React.FC<AdsTabProps> = ({
  campaigns,
  sponsors,
  globalKillSwitch,
  onSaveCampaign,
  onToggleCampaignActive,
  onDeleteCampaign,
  onSaveSponsor,
  onDeleteSponsor,
  initialSubTab = 'campaigns'
}) => {
  const [subTab, setSubTab] = useState<AdsSubTab>(initialSubTab);

  // Form State for New Campaign
  const [formId, setFormId] = useState<string>('');
  const [campaignName, setCampaignName] = useState<string>('Q3 Premium Audio Sponsorship');
  const [sponsorId, setSponsorId] = useState<string>(sponsors[0]?.id || 'sp-1');
  const [adFormat, setAdFormat] = useState<AdFormat>('audio');
  const [headline, setHeadline] = useState<string>('Upgrade to Premium Now');
  const [ctaUrl, setCtaUrl] = useState<string>('techcorp.com/premium-audio');
  const [startDate, setStartDate] = useState<string>('2026-07-01');
  const [endDate, setEndDate] = useState<string>('2026-09-30');
  const [mediaName, setMediaName] = useState<string>('campaign-hero.jpg');
  const [mediaSize, setMediaSize] = useState<string>('1.2 MB');
  const [mediaUrl, setMediaUrl] = useState<string>(
    'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=80'
  );

  // Audio preview simulation state
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [audioProgress, setAudioProgress] = useState<number>(35);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  // New Sponsor Form Modal
  const [showSponsorModal, setShowSponsorModal] = useState<boolean>(false);
  const [newSponsorName, setNewSponsorName] = useState<string>('');
  const [newSponsorCnpj, setNewSponsorCnpj] = useState<string>('');
  const [newSponsorEmail, setNewSponsorEmail] = useState<string>('');

  const selectedSponsorName = sponsors.find(s => s.id === sponsorId)?.name || 'TechCorp Industries';

  const handleEditCampaign = (c: Campaign) => {
    setFormId(c.id);
    setCampaignName(c.name);
    setSponsorId(c.sponsor_id);
    setAdFormat(c.format);
    setHeadline(c.headline);
    setCtaUrl(c.cta_url);
    setStartDate(c.start_date);
    setEndDate(c.end_date);
    setMediaName(c.media_name || 'asset.jpg');
    setMediaSize(c.media_size || '1.0 MB');
    setMediaUrl(c.media_url || 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=80');
    setSubTab('create');
  };

  const handleCreateNewClick = () => {
    setFormId('');
    setCampaignName('Nova Campanha de Anúncio');
    setHeadline('Headline em Destaque');
    setCtaUrl('valedaliberdade.com.br/anuncie');
    setStartDate(new Date().toISOString().slice(0, 10));
    setEndDate(new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10));
    setSubTab('create');
  };

  const handleSubmitCampaign = (e: React.FormEvent) => {
    e.preventDefault();
    const newCamp: Campaign = {
      id: formId || `cmp-${Date.now()}`,
      sponsor_id: sponsorId,
      sponsor_name: selectedSponsorName,
      name: campaignName,
      format: adFormat,
      headline,
      cta_url: ctaUrl,
      start_date: startDate,
      end_date: endDate,
      media_name: mediaName,
      media_size: mediaSize,
      media_url: mediaUrl,
      is_active: true,
      impressions: formId ? campaigns.find(c => c.id === formId)?.impressions || 0 : 0,
      clicks: formId ? campaigns.find(c => c.id === formId)?.clicks || 0 : 0,
      skips: 0,
      errors: 0,
      status: 'active'
    };
    onSaveCampaign(newCamp);
    setSubTab('campaigns');
  };

  const handleAddSponsorSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSponsorName) return;
    const sponsor: Sponsor = {
      id: `sp-${Date.now()}`,
      name: newSponsorName,
      cnpj: newSponsorCnpj || '00.000.000/0001-00',
      email: newSponsorEmail || 'contato@patrocinador.com.br',
      is_active: true,
      createdAt: new Date().toISOString().slice(0, 10)
    };
    onSaveSponsor(sponsor);
    setSponsorId(sponsor.id);
    setNewSponsorName('');
    setNewSponsorCnpj('');
    setNewSponsorEmail('');
    setShowSponsorModal(false);
  };

  // Preset Image Assets for test
  const sampleImages = [
    { name: 'Tech Abstract', url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=80' },
    { name: 'Finance Growth', url: 'https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=800&auto=format&fit=crop&q=80' },
    { name: 'Modern Vehicle', url: 'https://images.unsplash.com/photo-1563986768609-322da13575f3?w=800&auto=format&fit=crop&q=80' },
    { name: 'Clean Energy', url: 'https://images.unsplash.com/photo-1497435334941-8c899ee9e8e9?w=800&auto=format&fit=crop&q=80' }
  ];

  return (
    <div className="space-y-6">
      {/* Sub Header & Navigation */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 pb-4 border-b border-white/5">
        <div className="flex bg-[#18181b] p-1 rounded-xl border border-white/10">
          <button
            onClick={() => setSubTab('campaigns')}
            className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
              subTab === 'campaigns'
                ? 'bg-emerald-600 text-white shadow-sm font-bold'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Campanhas & Criativos ({campaigns.length})
          </button>

          <button
            onClick={() => setSubTab('create')}
            className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
              subTab === 'create'
                ? 'bg-emerald-600 text-white shadow-sm font-bold'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            {formId ? 'Editar Campanha' : '+ Criar Nova Campanha'}
          </button>

          <button
            onClick={() => setSubTab('sponsors')}
            className={`px-4 py-2 rounded-lg text-xs font-semibold transition-all ${
              subTab === 'sponsors'
                ? 'bg-emerald-600 text-white shadow-sm font-bold'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Patrocinadores ({sponsors.length})
          </button>
        </div>

        {subTab === 'campaigns' && (
          <button
            onClick={handleCreateNewClick}
            className="px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            <span>Novo Anúncio</span>
          </button>
        )}

        {subTab === 'sponsors' && (
          <button
            onClick={() => setShowSponsorModal(true)}
            className="px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            <span>Adicionar Patrocinador</span>
          </button>
        )}
      </div>

      {/* SUBTAB 1: CAMPAIGNS LIST */}
      {subTab === 'campaigns' && (
        <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden shadow-xl p-6 space-y-4">
          <div className="flex justify-between items-center mb-2">
            <div>
              <h3 className="text-lg font-bold text-white">Gestão de Anúncios & Campanhas</h3>
              <p className="text-xs text-slate-400">
                Controle de exibição instantâneo via Kill-Switch em 1-clique
              </p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-white/5 text-slate-400 uppercase tracking-wider font-semibold border-b border-white/10">
                <tr>
                  <th className="py-3 px-4">Anúncio</th>
                  <th className="py-3 px-4">Patrocinador</th>
                  <th className="py-3 px-4">Formato</th>
                  <th className="py-3 px-4">Vigência</th>
                  <th className="py-3 px-4">Métricas (Imp / Cliques)</th>
                  <th className="py-3 px-4 text-center">1-Click Kill Switch</th>
                  <th className="py-3 px-4 text-right">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-slate-300">
                {campaigns.map(c => {
                  const isPaused = !c.is_active || globalKillSwitch;

                  return (
                    <tr key={c.id} className="hover:bg-white/5 transition-colors">
                      <td className="py-4 px-4">
                        <div className="flex items-center gap-3">
                          {c.media_url ? (
                            <img src={c.media_url} alt="" className="w-10 h-10 rounded-lg object-cover border border-white/10" />
                          ) : (
                            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center font-bold">
                              {c.format[0].toUpperCase()}
                            </div>
                          )}
                          <div>
                            <p className="font-bold text-white text-sm">{c.name}</p>
                            <p className="text-[11px] text-slate-400 italic">"{c.headline}"</p>
                          </div>
                        </div>
                      </td>
                      <td className="py-4 px-4 font-semibold text-white">{c.sponsor_name}</td>
                      <td className="py-4 px-4">
                        <span className="px-2.5 py-1 rounded bg-white/5 border border-white/10 text-[10px] uppercase font-bold text-emerald-400">
                          {c.format}
                        </span>
                      </td>
                      <td className="py-4 px-4 text-slate-400 text-[11px]">
                        {c.start_date} até {c.end_date}
                      </td>
                      <td className="py-4 px-4 font-mono">
                        <span className="text-white font-bold">{c.impressions.toLocaleString('pt-BR')}</span> imp /{' '}
                        <span className="text-emerald-400 font-bold">{c.clicks.toLocaleString('pt-BR')}</span> clicks
                      </td>
                      <td className="py-4 px-4 text-center">
                        <button
                          onClick={() => onToggleCampaignActive(c.id)}
                          disabled={globalKillSwitch}
                          className={`px-3 py-1 rounded-full text-[11px] font-bold border transition-all flex items-center gap-1.5 mx-auto ${
                            isPaused
                              ? 'bg-rose-500/10 border-rose-500/20 text-rose-400 hover:bg-rose-500/20'
                              : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20'
                          }`}
                        >
                          <Power className="w-3.5 h-3.5" />
                          <span>{isPaused ? 'PAUSADO' : 'ATIVO'}</span>
                        </button>
                      </td>
                      <td className="py-4 px-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => handleEditCampaign(c)}
                            className="p-1.5 text-slate-400 hover:text-emerald-400 hover:bg-white/5 rounded-lg transition-colors"
                            title="Editar Anúncio"
                          >
                            <Edit3 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => onDeleteCampaign(c.id)}
                            className="p-1.5 text-rose-400 hover:text-rose-300 hover:bg-rose-500/10 rounded-lg transition-colors"
                            title="Excluir Anúncio"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* SUBTAB 2: CREATE / EDIT CAMPAIGN FORM WITH LIVE PREVIEW */}
      {subTab === 'create' && (
        <form onSubmit={handleSubmitCampaign} className="grid grid-cols-1 xl:grid-cols-12 gap-6">
          {/* Left Column: Form Fields (7 cols) */}
          <div className="xl:col-span-7 space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-xl font-bold text-white">
                  {formId ? 'Editar Anúncio Publicitário' : 'Novo Anúncio Publicitário'}
                </h2>
                <p className="text-xs text-[#bbcabf] mt-0.5">
                  Configure os dados da campanha e veja a prévia instantânea no celular ao lado.
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setSubTab('campaigns')}
                  className="px-4 py-2 rounded-xl text-xs font-semibold border border-white/10 text-[#bbcabf] hover:bg-white/5 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl text-xs font-bold bg-[#4edea3] text-[#002113] hover:bg-[#6ffbbe] transition-all shadow-[0_0_15px_rgba(78,222,163,0.3)]"
                >
                  {formId ? 'Salvar Alterações' : 'Publicar Anúncio'}
                </button>
              </div>
            </div>

            {/* Core Information Card */}
            <div className="glass-panel rounded-xl p-6 shadow-xl space-y-5">
              <h3 className="text-sm font-bold text-white flex items-center gap-2 border-b border-white/5 pb-3">
                <Sparkles className="w-4 h-4 text-[#4edea3]" />
                Informações Principais da Campanha
              </h3>

              <div>
                <label className="block text-xs font-semibold text-[#bbcabf] mb-1.5">Nome Interno da Campanha</label>
                <input
                  type="text"
                  required
                  value={campaignName}
                  onChange={e => setCampaignName(e.target.value)}
                  placeholder="ex: Q3 Premium Audio Sponsorship"
                  className="w-full glass-input rounded-xl px-4 py-2.5 text-sm"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[#bbcabf] mb-1.5">Patrocinador / Cliente</label>
                  <select
                    value={sponsorId}
                    onChange={e => setSponsorId(e.target.value)}
                    className="w-full glass-input rounded-xl px-4 py-2.5 text-sm bg-[#0b1326]"
                  >
                    {sponsors.map(s => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#bbcabf] mb-1.5">Formato do Anúncio</label>
                  <div className="flex p-1 bg-[#131b2e] rounded-xl border border-white/10">
                    <button
                      type="button"
                      onClick={() => setAdFormat('audio')}
                      className={`flex-1 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                        adFormat === 'audio'
                          ? 'bg-[#4edea3] text-[#002113] shadow'
                          : 'text-[#bbcabf] hover:text-white'
                      }`}
                    >
                      Áudio
                    </button>
                    <button
                      type="button"
                      onClick={() => setAdFormat('banner')}
                      className={`flex-1 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                        adFormat === 'banner'
                          ? 'bg-[#4edea3] text-[#002113] shadow'
                          : 'text-[#bbcabf] hover:text-white'
                      }`}
                    >
                      Banner
                    </button>
                    <button
                      type="button"
                      onClick={() => setAdFormat('video')}
                      className={`flex-1 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                        adFormat === 'video'
                          ? 'bg-[#4edea3] text-[#002113] shadow'
                          : 'text-[#bbcabf] hover:text-white'
                      }`}
                    >
                      Vídeo
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Creative Assets Upload Card */}
            <div className="glass-panel rounded-xl p-6 shadow-xl space-y-4">
              <h3 className="text-sm font-bold text-white flex items-center gap-2 border-b border-white/5 pb-3">
                <ImageIcon className="w-4 h-4 text-[#4edea3]" />
                Mídia & Elementos Criativos
              </h3>

              <div className="border-2 border-dashed border-white/15 hover:border-[#4edea3]/50 transition-colors rounded-xl bg-[#0b1326]/40 p-6 text-center cursor-pointer">
                <CloudUpload className="w-10 h-10 text-[#4edea3] mx-auto mb-2" />
                <p className="text-xs font-semibold text-white">Arraste a mídia da campanha aqui</p>
                <p className="text-[11px] text-[#bbcabf] mt-1">Suporta MP3, WAV, JPG, PNG, MP4 (Máx 50MB)</p>

                {/* Preset Selector for quick demo */}
                <div className="mt-4 pt-3 border-t border-white/5">
                  <p className="text-[10px] text-[#bbcabf] mb-2 uppercase font-bold tracking-wider">
                    Ou selecione um modelo criativo:
                  </p>
                  <div className="flex flex-wrap gap-2 justify-center">
                    {sampleImages.map((img, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => {
                          setMediaUrl(img.url);
                          setMediaName(`${img.name.toLowerCase().replace(' ', '-')}.jpg`);
                        }}
                        className={`px-2.5 py-1 text-[11px] rounded-lg border transition-all ${
                          mediaUrl === img.url
                            ? 'bg-[#4edea3]/20 border-[#4edea3] text-[#4edea3] font-bold'
                            : 'bg-white/5 border-white/10 text-gray-300 hover:bg-white/10'
                        }`}
                      >
                        {img.name}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Selected File Badge */}
              <div className="p-3 bg-[#131b2e] rounded-xl border border-white/10 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 bg-[#4edea3]/20 rounded-lg flex items-center justify-center text-[#4edea3]">
                    <ImageIcon className="w-5 h-5" />
                  </div>
                  <div>
                    <p className="text-xs font-bold text-white">{mediaName}</p>
                    <p className="text-[10px] text-[#bbcabf]">{mediaSize}</p>
                  </div>
                </div>
                <span className="text-[10px] text-[#4edea3] bg-[#4edea3]/10 px-2 py-1 rounded-full font-semibold">
                  Mídia Carregada
                </span>
              </div>
            </div>

            {/* Action & Schedule Card */}
            <div className="glass-panel rounded-xl p-6 shadow-xl space-y-4">
              <h3 className="text-sm font-bold text-white flex items-center gap-2 border-b border-white/5 pb-3">
                <ExternalLink className="w-4 h-4 text-[#4edea3]" />
                Chamada para Ação & Programação
              </h3>

              <div>
                <label className="block text-xs font-semibold text-[#bbcabf] mb-1.5">Título / Headline Exibida</label>
                <input
                  type="text"
                  required
                  value={headline}
                  onChange={e => setHeadline(e.target.value)}
                  placeholder="ex: Upgrade to Premium Now"
                  className="w-full glass-input rounded-xl px-4 py-2.5 text-sm"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-[#bbcabf] mb-1.5">Link da Chamada (CTA)</label>
                <div className="flex rounded-xl overflow-hidden border border-white/10">
                  <span className="bg-[#131b2e] px-3.5 py-2.5 text-xs text-[#bbcabf] font-mono border-r border-white/10 flex items-center">
                    https://
                  </span>
                  <input
                    type="text"
                    required
                    value={ctaUrl}
                    onChange={e => setCtaUrl(e.target.value)}
                    placeholder="techcorp.com/promo"
                    className="w-full bg-[#0b1326]/60 text-white px-4 py-2.5 text-sm focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-[#bbcabf] mb-1.5">Data Inicial</label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={e => setStartDate(e.target.value)}
                    className="w-full glass-input rounded-xl px-4 py-2 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-[#bbcabf] mb-1.5">Data Final</label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={e => setEndDate(e.target.value)}
                    className="w-full glass-input rounded-xl px-4 py-2 text-xs"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Right Column: Live Mobile Phone Preview Mockup (5 cols) */}
          <div className="xl:col-span-5 flex flex-col items-center justify-start pt-4 relative">
            <div className="mb-3 text-center">
              <span className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-[#171f33] border border-white/15 text-xs font-bold text-[#4edea3] uppercase tracking-widest shadow-lg">
                <span className="w-2 h-2 rounded-full bg-[#4edea3] animate-pulse"></span>
                PRÉVIA INTERATIVA EM TEMPO REAL
              </span>
            </div>

            {/* Mobile Device Shell */}
            <div className="relative w-[340px] h-[680px] bg-black rounded-[44px] border-[8px] border-[#222a3d] shadow-2xl overflow-hidden shrink-0 flex flex-col justify-between border-t-[#31394d]">
              {/* Dynamic Notch */}
              <div className="absolute top-0 inset-x-0 h-6 flex justify-center z-50 pointer-events-none">
                <div className="w-28 h-5 bg-black rounded-b-xl"></div>
              </div>

              {/* Mobile Content Display */}
              <div className="w-full h-full bg-gradient-to-b from-[#131b2e] via-[#0b1326] to-black flex flex-col text-white pt-8 pb-4 px-5 relative justify-between">
                {/* Header info */}
                <div className="flex justify-between items-center text-xs text-gray-400 pb-2 border-b border-white/10">
                  <span className="text-[10px] font-mono text-[#4edea3]">JORNAL VALE</span>
                  <span className="font-bold text-[10px] uppercase tracking-widest bg-[#4edea3]/20 text-[#4edea3] px-2 py-0.5 rounded">
                    PATROCINADO
                  </span>
                  <Volume2 className="w-4 h-4 text-[#4edea3]" />
                </div>

                {/* Creative Hero Display */}
                <div className="my-auto space-y-4">
                  <div className="w-full aspect-square rounded-2xl shadow-2xl overflow-hidden relative border border-white/15 group">
                    <img
                      src={mediaUrl}
                      alt="Ad Preview"
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                    />
                    <div className="absolute top-3 left-3 bg-black/75 backdrop-blur-md px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider text-white border border-white/20">
                      PUBLICIDADE {adFormat.toUpperCase()}
                    </div>
                  </div>

                  {/* Dynamic Ad Details */}
                  <div className="space-y-1">
                    <h4 className="text-lg font-bold text-white leading-tight line-clamp-2">{headline || 'Título do Anúncio'}</h4>
                    <p className="text-xs text-[#4edea3] font-semibold flex items-center gap-1">
                      {selectedSponsorName}
                    </p>
                  </div>

                  {/* Interactive Audio Progress Bar */}
                  {adFormat === 'audio' && (
                    <div className="space-y-2 py-2">
                      <div className="w-full h-1.5 bg-white/20 rounded-full overflow-hidden cursor-pointer">
                        <div
                          className="h-full bg-[#4edea3] transition-all duration-300"
                          style={{ width: `${audioProgress}%` }}
                        ></div>
                      </div>
                      <div className="flex justify-between text-[10px] text-gray-400 font-mono">
                        <span>0:15</span>
                        <span>-0:15</span>
                      </div>

                      {/* Controls */}
                      <div className="flex justify-between items-center px-4 pt-1">
                        <Shuffle className="w-4 h-4 text-gray-500" />
                        <SkipBack className="w-5 h-5 text-gray-300" />
                        <button
                          type="button"
                          onClick={() => {
                            setIsPlaying(!isPlaying);
                            setAudioProgress(prev => (prev >= 100 ? 0 : prev + 20));
                          }}
                          className="w-12 h-12 rounded-full bg-[#4edea3] text-[#002113] flex items-center justify-center font-bold shadow-lg hover:scale-105 transition-transform"
                        >
                          {isPlaying ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6 ml-0.5" />}
                        </button>
                        <SkipForward className="w-5 h-5 text-gray-300" />
                        <Repeat className="w-4 h-4 text-gray-500" />
                      </div>
                    </div>
                  )}
                </div>

                {/* Mobile Bottom Call to Action Bar */}
                <a
                  href={`https://${ctaUrl.replace(/^https?:\/\//, '')}`}
                  target="_blank"
                  rel="noreferrer"
                  className="w-full bg-[#171f33]/90 backdrop-blur-xl hover:bg-[#222a3d] border border-[#4edea3]/40 p-3.5 rounded-2xl flex items-center justify-between group transition-all shadow-xl"
                >
                  <div className="flex flex-col text-left">
                    <span className="text-xs font-bold text-white group-hover:text-[#4edea3] transition-colors">
                      Acessar Patrocinador
                    </span>
                    <span className="text-[10px] text-gray-400 font-mono line-clamp-1">{ctaUrl}</span>
                  </div>
                  <div className="w-7 h-7 rounded-full bg-[#4edea3]/20 flex items-center justify-center text-[#4edea3] group-hover:bg-[#4edea3] group-hover:text-[#002113] transition-all">
                    <ChevronRight className="w-4 h-4" />
                  </div>
                </a>
              </div>
            </div>
          </div>
        </form>
      )}

      {/* SUBTAB 3: SPONSORS LIST & MODAL */}
      {subTab === 'sponsors' && (
        <div className="glass-panel rounded-2xl p-6 shadow-xl space-y-4">
          <div className="flex justify-between items-center mb-2">
            <div>
              <h3 className="text-lg font-bold text-white">Patrocinadores & Clientes Parceiros (Tipo 1)</h3>
              <p className="text-xs text-[#bbcabf]">
                Empresas com contrato publicitário assinado com o Jornal Vale da Liberdade
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {sponsors.map(sp => {
              const activeCount = campaigns.filter(c => c.sponsor_id === sp.id && c.is_active).length;

              return (
                <div key={sp.id} className="p-5 rounded-xl bg-[#0b1326]/60 border border-white/10 space-y-3 relative group">
                  <div className="flex justify-between items-start">
                    <div className="flex items-center gap-3">
                      {sp.logoUrl ? (
                        <img src={sp.logoUrl} alt="" className="w-12 h-12 rounded-xl object-cover border border-white/10" />
                      ) : (
                        <div className="w-12 h-12 rounded-xl bg-[#4edea3]/20 text-[#4edea3] flex items-center justify-center font-bold">
                          {sp.name[0]}
                        </div>
                      )}
                      <div>
                        <h4 className="font-bold text-white text-sm">{sp.name}</h4>
                        <p className="text-[11px] text-[#bbcabf] font-mono">{sp.cnpj}</p>
                      </div>
                    </div>
                    <button
                      onClick={() => onDeleteSponsor(sp.id)}
                      className="text-red-400 hover:text-red-300 p-1 opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Remover Patrocinador"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="text-xs space-y-1 text-[#bbcabf] pt-2 border-t border-white/5">
                    <p>
                      <span className="text-gray-400">E-mail:</span> {sp.email}
                    </p>
                    <p>
                      <span className="text-gray-400">Contrato:</span> Ativo até {sp.contract_end || '2026-12-31'}
                    </p>
                    <p>
                      <span className="text-gray-400">Campanhas Ativas:</span>{' '}
                      <span className="text-[#4edea3] font-bold">{activeCount} veiculando</span>
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* SPONSOR MODAL */}
      {showSponsorModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
          <form
            onSubmit={handleAddSponsorSubmit}
            className="bg-[#171f33] border border-white/15 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4 text-xs"
          >
            <h3 className="text-base font-bold text-white mb-2">Cadastrar Novo Patrocinador</h3>

            <div>
              <label className="block text-[#bbcabf] font-semibold mb-1">Nome da Empresa / Cliente</label>
              <input
                type="text"
                required
                value={newSponsorName}
                onChange={e => setNewSponsorName(e.target.value)}
                placeholder="ex: Banco Vale da Liberdade"
                className="w-full glass-input rounded-xl px-4 py-2 text-xs"
              />
            </div>

            <div>
              <label className="block text-[#bbcabf] font-semibold mb-1">CNPJ</label>
              <input
                type="text"
                value={newSponsorCnpj}
                onChange={e => setNewSponsorCnpj(e.target.value)}
                placeholder="00.000.000/0001-00"
                className="w-full glass-input rounded-xl px-4 py-2 text-xs font-mono"
              />
            </div>

            <div>
              <label className="block text-[#bbcabf] font-semibold mb-1">E-mail Comercial</label>
              <input
                type="email"
                value={newSponsorEmail}
                onChange={e => setNewSponsorEmail(e.target.value)}
                placeholder="comercial@empresa.com.br"
                className="w-full glass-input rounded-xl px-4 py-2 text-xs"
              />
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t border-white/10">
              <button
                type="button"
                onClick={() => setShowSponsorModal(false)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-[#bbcabf] hover:bg-white/5"
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="px-4 py-2 rounded-xl text-xs font-bold bg-[#4edea3] text-[#002113] hover:bg-[#6ffbbe]"
              >
                Salvar Patrocinador
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
