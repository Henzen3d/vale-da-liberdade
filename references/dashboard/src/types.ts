export type RoleType = 'admin' | 'editor' | 'reader';

export type PlanType = 'free' | 'premium' | 'vip';
export type SubscriptionStatus = 'active' | 'cancelled' | 'expired' | 'pending';

export type AdFormat = 'audio' | 'banner' | 'video';
export type CampaignStatus = 'active' | 'draft' | 'paused' | 'ended';

export interface Sponsor {
  id: string;
  name: string;
  cnpj: string;
  email: string;
  logoUrl?: string;
  is_active: boolean;
  contract_end?: string;
  createdAt: string;
}

export interface Campaign {
  id: string;
  sponsor_id: string;
  sponsor_name: string;
  name: string;
  format: AdFormat;
  headline: string;
  cta_url: string;
  start_date: string;
  end_date: string;
  media_url?: string;
  media_name?: string;
  media_size?: string;
  is_active: boolean;
  impressions: number;
  clicks: number;
  skips: number;
  errors: number;
  status: CampaignStatus;
}

export interface UserProfile {
  id: string;
  name: string;
  email: string;
  avatar_url?: string;
  role: RoleType;
  created_at: string;
  last_login?: string;
}

export interface Subscription {
  id: string;
  user_id: string;
  user_name: string;
  user_email: string;
  plan: PlanType;
  status: SubscriptionStatus;
  price_monthly: number;
  start_date: string;
  expires_at: string;
}

export interface DailyMetrics {
  date: string;
  impressions: number;
  clicks: number;
  ctr: number;
  skips: number;
  errors: number;
  revenue: number;
}

export type MainTab = 'overview' | 'ads' | 'users' | 'reports';
export type AdsSubTab = 'campaigns' | 'sponsors' | 'create';
