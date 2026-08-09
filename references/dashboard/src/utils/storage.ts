import { Sponsor, Campaign, UserProfile, Subscription } from '../types';
import { INITIAL_SPONSORS, INITIAL_CAMPAIGNS, INITIAL_USERS, INITIAL_SUBSCRIPTIONS } from '../data/mockData';

const STORAGE_KEYS = {
  SPONSORS: 'jvl_admin_sponsors',
  CAMPAIGNS: 'jvl_admin_campaigns',
  USERS: 'jvl_admin_users',
  SUBSCRIPTIONS: 'jvl_admin_subscriptions',
  GLOBAL_KILL_SWITCH: 'jvl_admin_global_kill_switch',
  ADMIN_ROLE_SIM: 'jvl_admin_role_sim'
};

export const getStoredSponsors = (): Sponsor[] => {
  const data = localStorage.getItem(STORAGE_KEYS.SPONSORS);
  if (!data) {
    localStorage.setItem(STORAGE_KEYS.SPONSORS, JSON.stringify(INITIAL_SPONSORS));
    return INITIAL_SPONSORS;
  }
  try {
    return JSON.parse(data);
  } catch {
    return INITIAL_SPONSORS;
  }
};

export const saveSponsors = (sponsors: Sponsor[]) => {
  localStorage.setItem(STORAGE_KEYS.SPONSORS, JSON.stringify(sponsors));
};

export const getStoredCampaigns = (): Campaign[] => {
  const data = localStorage.getItem(STORAGE_KEYS.CAMPAIGNS);
  if (!data) {
    localStorage.setItem(STORAGE_KEYS.CAMPAIGNS, JSON.stringify(INITIAL_CAMPAIGNS));
    return INITIAL_CAMPAIGNS;
  }
  try {
    return JSON.parse(data);
  } catch {
    return INITIAL_CAMPAIGNS;
  }
};

export const saveCampaigns = (campaigns: Campaign[]) => {
  localStorage.setItem(STORAGE_KEYS.CAMPAIGNS, JSON.stringify(campaigns));
};

export const getStoredUsers = (): UserProfile[] => {
  const data = localStorage.getItem(STORAGE_KEYS.USERS);
  if (!data) {
    localStorage.setItem(STORAGE_KEYS.USERS, JSON.stringify(INITIAL_USERS));
    return INITIAL_USERS;
  }
  try {
    return JSON.parse(data);
  } catch {
    return INITIAL_USERS;
  }
};

export const saveUsers = (users: UserProfile[]) => {
  localStorage.setItem(STORAGE_KEYS.USERS, JSON.stringify(users));
};

export const getStoredSubscriptions = (): Subscription[] => {
  const data = localStorage.getItem(STORAGE_KEYS.SUBSCRIPTIONS);
  if (!data) {
    localStorage.setItem(STORAGE_KEYS.SUBSCRIPTIONS, JSON.stringify(INITIAL_SUBSCRIPTIONS));
    return INITIAL_SUBSCRIPTIONS;
  }
  try {
    return JSON.parse(data);
  } catch {
    return INITIAL_SUBSCRIPTIONS;
  }
};

export const saveSubscriptions = (subs: Subscription[]) => {
  localStorage.setItem(STORAGE_KEYS.SUBSCRIPTIONS, JSON.stringify(subs));
};

export const getGlobalKillSwitch = (): boolean => {
  const data = localStorage.getItem(STORAGE_KEYS.GLOBAL_KILL_SWITCH);
  return data ? JSON.parse(data) : false; // false means ads active, true means ALL ads paused
};

export const saveGlobalKillSwitch = (paused: boolean) => {
  localStorage.setItem(STORAGE_KEYS.GLOBAL_KILL_SWITCH, JSON.stringify(paused));
};

export const getSimulatedRole = (): 'admin' | 'reader' => {
  const data = localStorage.getItem(STORAGE_KEYS.ADMIN_ROLE_SIM);
  return (data === 'reader' ? 'reader' : 'admin');
};

export const saveSimulatedRole = (role: 'admin' | 'reader') => {
  localStorage.setItem(STORAGE_KEYS.ADMIN_ROLE_SIM, role);
};

// CSV Export Utility
export const exportToCSV = (filename: string, rows: Record<string, any>[]) => {
  if (!rows || !rows.length) return;
  const headers = Object.keys(rows[0]);
  const csvContent = [
    headers.join(','),
    ...rows.map(row =>
      headers
        .map(field => {
          const val = row[field] ?? '';
          const escaped = String(val).replace(/"/g, '""');
          return `"${escaped}"`;
        })
        .join(',')
    )
  ].join('\n');

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.setAttribute('href', url);
  link.setAttribute('download', `${filename}_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
};
