import { Sponsor, Campaign, UserProfile, Subscription, DailyMetrics } from '../types';

export const INITIAL_SPONSORS: Sponsor[] = [
  {
    id: 'sp-1',
    name: 'TechCorp Industries',
    cnpj: '12.345.678/0001-90',
    email: 'contato@techcorp.com.br',
    logoUrl: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=150&auto=format&fit=crop&q=80',
    is_active: true,
    contract_end: '2026-12-31',
    createdAt: '2026-01-15'
  },
  {
    id: 'sp-2',
    name: 'Liberty Financial Group',
    cnpj: '98.765.432/0001-10',
    email: 'mkt@libertyfin.com.br',
    logoUrl: 'https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=150&auto=format&fit=crop&q=80',
    is_active: true,
    contract_end: '2026-10-30',
    createdAt: '2026-02-01'
  },
  {
    id: 'sp-3',
    name: 'Global Motors Vale',
    cnpj: '45.123.890/0001-55',
    email: 'comercial@globalmotors.com.br',
    logoUrl: 'https://images.unsplash.com/photo-1563986768609-322da13575f3?w=150&auto=format&fit=crop&q=80',
    is_active: true,
    contract_end: '2026-09-15',
    createdAt: '2026-03-10'
  },
  {
    id: 'sp-4',
    name: 'EcoEnergia Renovável',
    cnpj: '33.999.111/0001-44',
    email: 'anuncios@ecoenergia.com.br',
    logoUrl: 'https://images.unsplash.com/photo-1497435334941-8c899ee9e8e9?w=150&auto=format&fit=crop&q=80',
    is_active: false,
    contract_end: '2026-06-01',
    createdAt: '2025-11-20'
  }
];

export const INITIAL_CAMPAIGNS: Campaign[] = [
  {
    id: 'cmp-1',
    sponsor_id: 'sp-1',
    sponsor_name: 'TechCorp Industries',
    name: 'Q3 Premium Audio Sponsorship',
    format: 'audio',
    headline: 'Upgrade to Premium Now',
    cta_url: 'techcorp.com/premium-audio',
    start_date: '2026-07-01',
    end_date: '2026-09-30',
    media_name: 'campaign-hero.jpg',
    media_size: '1.2 MB',
    media_url: 'https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=800&auto=format&fit=crop&q=80',
    is_active: true,
    impressions: 142500,
    clicks: 12430,
    skips: 3200,
    errors: 45,
    status: 'active'
  },
  {
    id: 'cmp-2',
    sponsor_id: 'sp-2',
    sponsor_name: 'Liberty Financial Group',
    name: 'Investimentos Inteligentes 2026',
    format: 'banner',
    headline: 'Multiplique seu Capital com Taxas Exclusivas',
    cta_url: 'libertyfin.com.br/investir',
    start_date: '2026-08-01',
    end_date: '2026-11-01',
    media_name: 'banner-finance.jpg',
    media_size: '850 KB',
    media_url: 'https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=800&auto=format&fit=crop&q=80',
    is_active: true,
    impressions: 98400,
    clicks: 7650,
    skips: 0,
    errors: 12,
    status: 'active'
  },
  {
    id: 'cmp-3',
    sponsor_id: 'sp-3',
    sponsor_name: 'Global Motors Vale',
    name: 'Lançamento Novo SUV Híbrido',
    format: 'video',
    headline: 'O Futuro da Mobilidade Chegou ao Vale',
    cta_url: 'globalmotors.com.br/suv-2026',
    start_date: '2026-07-15',
    end_date: '2026-08-31',
    media_name: 'suv-spot-30s.mp4',
    media_size: '18.4 MB',
    media_url: 'https://images.unsplash.com/photo-1563986768609-322da13575f3?w=800&auto=format&fit=crop&q=80',
    is_active: true,
    impressions: 215000,
    clicks: 19800,
    skips: 14200,
    errors: 89,
    status: 'active'
  },
  {
    id: 'cmp-4',
    sponsor_id: 'sp-4',
    sponsor_name: 'EcoEnergia Renovável',
    name: 'Energia Solar Residencial',
    format: 'banner',
    headline: 'Economize até 95% na Conta de Luz',
    cta_url: 'ecoenergia.com.br/solar',
    start_date: '2026-05-01',
    end_date: '2026-06-30',
    media_name: 'eco-banner.png',
    media_size: '1.1 MB',
    media_url: 'https://images.unsplash.com/photo-1497435334941-8c899ee9e8e9?w=800&auto=format&fit=crop&q=80',
    is_active: false,
    impressions: 54000,
    clicks: 3100,
    skips: 0,
    errors: 5,
    status: 'ended'
  }
];

export const INITIAL_USERS: UserProfile[] = [
  {
    id: 'usr-1',
    name: 'Osmar Henzen (Admin)',
    email: 'henzen3d@gmail.com',
    avatar_url: 'https://lh3.googleusercontent.com/aida-public/AB6AXuDm-vJKa4F88bI75oZuKXurMxAwHNLsOOG6SXrpzLp8OvOAXTnWVVA6Ghrz97OXNDTypXUWY-MBVBlmenL16VqmdKuomyL73XuTdnaC4VOu72j5ANKQtKPxfgEsXfIK9omJ9dxH8JO296MblxePGJCpx7Wo05qG_I93EpRq1X7uDOxNXN_CfasxLGYBB8z0daLt1jZiQQQwPt2DbPosmIMFzqy0tiuq5ix_r4UsXAJpvAku0YDJGOZSVg',
    role: 'admin',
    created_at: '2025-01-10',
    last_login: '2026-08-03'
  },
  {
    id: 'usr-2',
    name: 'Ana Cláudia Silva',
    email: 'ana.silva@valedaliberdade.com.br',
    avatar_url: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150&auto=format&fit=crop&q=80',
    role: 'editor',
    created_at: '2025-03-22',
    last_login: '2026-08-02'
  },
  {
    id: 'usr-3',
    name: 'Carlos Eduardo Santos',
    email: 'carlos.santos@gmail.com',
    avatar_url: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80',
    role: 'reader',
    created_at: '2026-02-14',
    last_login: '2026-08-03'
  },
  {
    id: 'usr-4',
    name: 'Mariana Oliveira',
    email: 'mariana.oliveira@outlook.com',
    avatar_url: 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80',
    role: 'reader',
    created_at: '2026-04-05',
    last_login: '2026-08-01'
  },
  {
    id: 'usr-5',
    name: 'Roberto Mendes',
    email: 'roberto.mendes@empresa.com',
    avatar_url: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150&auto=format&fit=crop&q=80',
    role: 'reader',
    created_at: '2026-05-18',
    last_login: '2026-07-29'
  }
];

export const INITIAL_SUBSCRIPTIONS: Subscription[] = [
  {
    id: 'sub-101',
    user_id: 'usr-3',
    user_name: 'Carlos Eduardo Santos',
    user_email: 'carlos.santos@gmail.com',
    plan: 'vip',
    status: 'active',
    price_monthly: 49.90,
    start_date: '2026-02-14',
    expires_at: '2027-02-14'
  },
  {
    id: 'sub-102',
    user_id: 'usr-4',
    user_name: 'Mariana Oliveira',
    user_email: 'mariana.oliveira@outlook.com',
    plan: 'premium',
    status: 'active',
    price_monthly: 29.90,
    start_date: '2026-04-05',
    expires_at: '2026-10-05'
  },
  {
    id: 'sub-103',
    user_id: 'usr-5',
    user_name: 'Roberto Mendes',
    user_email: 'roberto.mendes@empresa.com',
    plan: 'free',
    status: 'active',
    price_monthly: 0.00,
    start_date: '2026-05-18',
    expires_at: '2099-12-31'
  }
];

export const DAILY_METRICS: DailyMetrics[] = [
  { date: '27 Jul', impressions: 45200, clicks: 3890, ctr: 8.6, skips: 920, errors: 12, revenue: 1420 },
  { date: '28 Jul', impressions: 52100, clicks: 4510, ctr: 8.65, skips: 1100, errors: 8, revenue: 1680 },
  { date: '29 Jul', impressions: 61000, clicks: 5420, ctr: 8.88, skips: 1350, errors: 15, revenue: 1950 },
  { date: '30 Jul', impressions: 58900, clicks: 5120, ctr: 8.69, skips: 1210, errors: 6, revenue: 1820 },
  { date: '31 Jul', impressions: 69400, clicks: 6200, ctr: 8.93, skips: 1480, errors: 19, revenue: 2240 },
  { date: '01 Aug', impressions: 74200, clicks: 6890, ctr: 9.28, skips: 1620, errors: 10, revenue: 2480 },
  { date: '02 Aug', impressions: 81500, clicks: 7920, ctr: 9.71, skips: 1840, errors: 14, revenue: 2890 },
  { date: '03 Aug', impressions: 87600, clicks: 8450, ctr: 9.64, skips: 1980, errors: 7, revenue: 3120 }
];
