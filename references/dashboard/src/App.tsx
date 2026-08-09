import React, { useState, useEffect } from 'react';
import { MainTab, AdsSubTab, Sponsor, Campaign, UserProfile, Subscription } from './types';
import {
  getStoredSponsors,
  saveSponsors,
  getStoredCampaigns,
  saveCampaigns,
  getStoredUsers,
  saveUsers,
  getStoredSubscriptions,
  saveSubscriptions,
  getGlobalKillSwitch,
  saveGlobalKillSwitch,
  getSimulatedRole,
  saveSimulatedRole,
  exportToCSV
} from './utils/storage';
import { DAILY_METRICS } from './data/mockData';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { OverviewTab } from './components/OverviewTab';
import { AdsTab } from './components/AdsTab';
import { UsersTab } from './components/UsersTab';
import { ReportsTab } from './components/ReportsTab';
import { AccessDeniedGuard } from './components/AccessDeniedGuard';

export default function App() {
  const [currentTab, setCurrentTab] = useState<MainTab>('overview');
  const [adsSubTab, setAdsSubTab] = useState<AdsSubTab>('campaigns');

  const [sponsors, setSponsors] = useState<Sponsor[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([]);
  const [globalKillSwitch, setGlobalKillSwitch] = useState<boolean>(false);
  const [isAdmin, setIsAdmin] = useState<boolean>(true);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(false);

  // Load initial data on mount
  useEffect(() => {
    setSponsors(getStoredSponsors());
    setCampaigns(getStoredCampaigns());
    setUsers(getStoredUsers());
    setSubscriptions(getStoredSubscriptions());
    setGlobalKillSwitch(getGlobalKillSwitch());
    setIsAdmin(getSimulatedRole() === 'admin');
  }, []);

  // Sync Global Kill Switch
  const handleToggleGlobalKillSwitch = () => {
    const nextState = !globalKillSwitch;
    setGlobalKillSwitch(nextState);
    saveGlobalKillSwitch(nextState);
  };

  // Sync 1-Click Campaign Kill-Switch (RPC toggle_entity_active)
  const handleToggleCampaignActive = (id: string) => {
    const updated = campaigns.map(c => {
      if (c.id === id) {
        return {
          ...c,
          is_active: !c.is_active,
          status: !c.is_active ? ('active' as const) : ('paused' as const)
        };
      }
      return c;
    });
    setCampaigns(updated);
    saveCampaigns(updated);
  };

  // Campaign Save / Delete
  const handleSaveCampaign = (campaign: Campaign) => {
    const exists = campaigns.some(c => c.id === campaign.id);
    let updated: Campaign[];
    if (exists) {
      updated = campaigns.map(c => (c.id === campaign.id ? campaign : c));
    } else {
      updated = [campaign, ...campaigns];
    }
    setCampaigns(updated);
    saveCampaigns(updated);
  };

  const handleDeleteCampaign = (id: string) => {
    const updated = campaigns.filter(c => c.id !== id);
    setCampaigns(updated);
    saveCampaigns(updated);
  };

  // Sponsor Save / Delete
  const handleSaveSponsor = (sponsor: Sponsor) => {
    const exists = sponsors.some(s => s.id === sponsor.id);
    let updated: Sponsor[];
    if (exists) {
      updated = sponsors.map(s => (s.id === sponsor.id ? sponsor : s));
    } else {
      updated = [sponsor, ...sponsors];
    }
    setSponsors(updated);
    saveSponsors(updated);
  };

  const handleDeleteSponsor = (id: string) => {
    const updated = sponsors.filter(s => s.id !== id);
    setSponsors(updated);
    saveSponsors(updated);
  };

  // User & Subscription Handlers
  const handleSaveUser = (user: UserProfile) => {
    const exists = users.some(u => u.id === user.id);
    let updated: UserProfile[];
    if (exists) {
      updated = users.map(u => (u.id === user.id ? user : u));
    } else {
      updated = [user, ...users];
    }
    setUsers(updated);
    saveUsers(updated);
  };

  const handleDeleteUser = (id: string) => {
    const updated = users.filter(u => u.id !== id);
    setUsers(updated);
    saveUsers(updated);
  };

  const handleSaveSubscription = (sub: Subscription) => {
    const exists = subscriptions.some(s => s.id === sub.id);
    let updated: Subscription[];
    if (exists) {
      updated = subscriptions.map(s => (s.id === sub.id ? sub : s));
    } else {
      updated = [sub, ...subscriptions];
    }
    setSubscriptions(updated);
    saveSubscriptions(updated);
  };

  // Role simulation toggle
  const handleToggleRoleSim = () => {
    const nextRole = isAdmin ? 'reader' : 'admin';
    setIsAdmin(nextRole === 'admin');
    saveSimulatedRole(nextRole);
  };

  // CSV Export Handlers
  const handleExportCSV = () => {
    exportToCSV('jornal_vale_metricas_diarias', DAILY_METRICS);
  };

  const handleExportCampaignsCSV = () => {
    exportToCSV('jornal_vale_campanhas_ads', campaigns);
  };

  const handleExportUsersCSV = () => {
    exportToCSV('jornal_vale_assinantes', subscriptions);
  };

  const handleNavigateToCreateAd = () => {
    setCurrentTab('ads');
    setAdsSubTab('create');
  };

  if (!isAdmin) {
    return <AccessDeniedGuard onSwitchToAdmin={() => {
      setIsAdmin(true);
      saveSimulatedRole('admin');
    }} />;
  }

  return (
    <div className="bg-[#0b1326] text-[#dae2fd] font-sans antialiased min-h-screen flex overflow-hidden">
      {/* Sidebar Navigation */}
      <Sidebar
        currentTab={currentTab}
        onSelectTab={tab => {
          setCurrentTab(tab);
          if (tab === 'ads') setAdsSubTab('campaigns');
        }}
        isAdmin={isAdmin}
        onToggleRoleSim={handleToggleRoleSim}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
      />

      {/* Main Container */}
      <div
        className={`flex-1 flex flex-col h-screen overflow-hidden transition-all duration-300 ${
          isSidebarCollapsed ? 'ml-20' : 'ml-64'
        }`}
      >
        {/* Top Header */}
        <Header
          currentTab={currentTab}
          onNewAdClick={handleNavigateToCreateAd}
          globalKillSwitch={globalKillSwitch}
          onToggleGlobalKillSwitch={handleToggleGlobalKillSwitch}
          userRole={isAdmin ? 'admin' : 'reader'}
        />

        {/* Main Canvas Area */}
        <main className="flex-1 overflow-y-auto p-6 relative">
          <div className="max-w-[1600px] mx-auto pb-12">
            {currentTab === 'overview' && (
              <OverviewTab
                campaigns={campaigns}
                sponsors={sponsors}
                subscriptions={subscriptions}
                metrics={DAILY_METRICS}
                globalKillSwitch={globalKillSwitch}
                onToggleGlobalKillSwitch={handleToggleGlobalKillSwitch}
                onToggleCampaignActive={handleToggleCampaignActive}
                onNavigateToCreateAd={handleNavigateToCreateAd}
                onExportCSV={handleExportCSV}
              />
            )}

            {currentTab === 'ads' && (
              <AdsTab
                campaigns={campaigns}
                sponsors={sponsors}
                globalKillSwitch={globalKillSwitch}
                onSaveCampaign={handleSaveCampaign}
                onToggleCampaignActive={handleToggleCampaignActive}
                onDeleteCampaign={handleDeleteCampaign}
                onSaveSponsor={handleSaveSponsor}
                onDeleteSponsor={handleDeleteSponsor}
                initialSubTab={adsSubTab}
              />
            )}

            {currentTab === 'users' && (
              <UsersTab
                users={users}
                subscriptions={subscriptions}
                onSaveUser={handleSaveUser}
                onDeleteUser={handleDeleteUser}
                onSaveSubscription={handleSaveSubscription}
              />
            )}

            {currentTab === 'reports' && (
              <ReportsTab
                metrics={DAILY_METRICS}
                campaigns={campaigns}
                subscriptions={subscriptions}
                onExportCSV={handleExportCSV}
                onExportCampaignsCSV={handleExportCampaignsCSV}
                onExportUsersCSV={handleExportUsersCSV}
              />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
