import React, { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import StatusBar from './components/StatusBar';
import { Menu } from 'lucide-react';
import SettingsModal from './components/SettingsModal';
import { MODEL_PROVIDERS } from './config/modelProviders';
import client from './api/client';
import AuthPage from './components/AuthPage';
import StatementsPanel from './components/StatementsPanel';

const settingsKey = userId => `truewealth.ai.settings.v1.${userId}`;
const sessionKey = userId => `truewealth.ai.session-key.v1.${userId}`;

const readModelSettings = (userId) => {
  const fallback = { provider: 'groq', model: MODEL_PROVIDERS.groq.model, apiKeys: {}, rememberKey: false };
  try {
    const saved = JSON.parse(localStorage.getItem(settingsKey(userId)) || '{}');
    const provider = MODEL_PROVIDERS[saved.provider] ? saved.provider : fallback.provider;
    const rememberKey = Boolean(saved.rememberKey);
    const savedKeys = saved.apiKeys && typeof saved.apiKeys === 'object' ? saved.apiKeys : {};
    let apiKeys = Object.fromEntries(
      Object.entries(MODEL_PROVIDERS)
        .filter(([providerId]) => typeof savedKeys[providerId] === 'string')
        .map(([providerId]) => [providerId, savedKeys[providerId]])
    );
    if (!rememberKey) {
      try {
        const sessionKeys = JSON.parse(sessionStorage.getItem(sessionKey(userId)) || '{}');
        apiKeys = Object.fromEntries(
          Object.entries(MODEL_PROVIDERS)
            .filter(([providerId]) => typeof sessionKeys[providerId] === 'string')
            .map(([providerId]) => [providerId, sessionKeys[providerId]])
        );
      } catch {
        apiKeys = {};
      }
    }
    return {
      provider,
      model: typeof saved.model === 'string' && saved.model.trim() ? saved.model : MODEL_PROVIDERS[provider].model,
      apiKeys,
      rememberKey,
    };
  } catch {
    return fallback;
  }
};

function App() {
  const [workspace, setWorkspace] = useState('chat');
  const [auth, setAuth] = useState(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [chatKey, setChatKey] = useState(0);
  const [activeConversation, setActiveConversation] = useState(() => ({
    sessionId: `session_${Date.now()}`,
    messages: [],
  }));
  const [historyVersion, setHistoryVersion] = useState(0);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [modelSettings, setModelSettings] = useState({ provider: 'groq', model: MODEL_PROVIDERS.groq.model, apiKeys: {}, rememberKey: false });

  useEffect(() => {
    client.get('/auth/csrf').then(() => client.get('/auth/me')).then(({ data }) => setAuth(data))
      .catch(() => setAuth(null)).finally(() => setAuthLoading(false));
  }, []);

  useEffect(() => {
    if (auth?.id) setModelSettings(readModelSettings(auth.id));
  }, [auth?.id]);

  const logout = async () => {
    try { await client.get('/auth/csrf'); await client.post('/auth/logout'); }
    finally {
      setAuth(null);
      setModelSettings({ provider: 'groq', model: MODEL_PROVIDERS.groq.model, apiKeys: {}, rememberKey: false });
      setActiveConversation({ sessionId: `session_${Date.now()}`, messages: [] });
    }
  };

  const startNewChat = () => {
    setWorkspace('chat');
    setActiveConversation({ sessionId: `session_${Date.now()}`, messages: [] });
    setChatKey(prev => prev + 1);
    setIsSidebarOpen(false); // Close sidebar on mobile when new chat starts
  };

  const openConversation = (conversation) => {
    setWorkspace('chat');
    setActiveConversation(conversation);
    setChatKey(prev => prev + 1);
    setIsSidebarOpen(false);
  };

  const saveModelSettings = (settings) => {
    const apiKeys = {
      ...(modelSettings.apiKeys || {}),
      [settings.provider]: settings.apiKey.trim(),
    };
    const nextSettings = {
      ...settings,
      provider: MODEL_PROVIDERS[settings.provider] ? settings.provider : 'groq',
      model: settings.model.trim(),
      apiKeys,
      rememberKey: Boolean(settings.rememberKey),
    };
    try {
      localStorage.setItem(settingsKey(auth.id), JSON.stringify({
        provider: nextSettings.provider,
        model: nextSettings.model,
        rememberKey: nextSettings.rememberKey,
        apiKeys: nextSettings.rememberKey ? nextSettings.apiKeys : {},
      }));
      if (nextSettings.rememberKey) sessionStorage.removeItem(sessionKey(auth.id));
      else sessionStorage.setItem(sessionKey(auth.id), JSON.stringify(nextSettings.apiKeys));
    } catch {
      // Keep settings in memory if browser storage is disabled or unavailable.
    }
    setModelSettings(nextSettings);
    setIsSettingsOpen(false);
  };

  if (authLoading) return <div className="min-h-screen bg-slate-950 text-slate-300 grid place-items-center">Loading your account…</div>;
  if (!auth) return <AuthPage onAuthenticated={setAuth} />;

  return (
    <div className="flex h-screen font-sans overflow-hidden">
      {/* Background Mesh Gradient */}
      <div className="bg-circles">
        <div className="circle-1"></div>
        <div className="circle-2"></div>
        <div className="circle-3"></div>
        <div className="circle-4"></div>
      </div>

      {/* Mobile Menu Button - Floating Glass */}
      <button
        onClick={() => setIsSidebarOpen(true)}
        className="md:hidden fixed top-4 left-4 z-40 p-3 bg-white/70 backdrop-blur-md rounded-xl shadow-lg text-slate-700 hover:text-primary transition-all active:scale-95 border border-white/50"
      >
        <Menu size={24} />
      </button>

      {/* Sidebar with Responsive Props */}
      <Sidebar
        onNewChat={startNewChat}
        onSelectConversation={openConversation}
        onOpenSettings={() => setIsSettingsOpen(true)}
        user={auth}
        onLogout={logout}
        activeSessionId={activeConversation.sessionId}
        historyVersion={historyVersion}
        isOpen={isSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
      />

      {/* Overlay for mobile */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-slate-900/20 z-40 md:hidden backdrop-blur-sm transition-opacity"
          onClick={() => setIsSidebarOpen(false)}
        ></div>
      )}

      <div className="flex-1 flex flex-col relative z-0 md:ml-[320px] transition-all duration-500">
        {/* Helper div to push content down on mobile if needed, or StatusBar handles it */}
        <StatusBar />
        <nav aria-label="Workspace" className="flex gap-2 px-5 py-3 border-b border-slate-200 bg-white/60">
          {['chat', 'statements'].map(tab => <button key={tab} onClick={() => setWorkspace(tab)} aria-pressed={workspace === tab} className={`rounded-xl px-4 py-2 text-sm font-semibold ${workspace === tab ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-white'}`}>{tab === 'chat' ? 'AI Advisor' : 'Bank Statements'}</button>)}
        </nav>
        {workspace === 'statements' ? <StatementsPanel key={auth.id} modelSettings={modelSettings} /> : <ChatInterface
          key={chatKey}
          sessionId={activeConversation.sessionId}
          initialMessages={activeConversation.messages}
          modelSettings={modelSettings}
          onHistoryChanged={() => setHistoryVersion(version => version + 1)}
        />}
      </div>

      {isSettingsOpen && (
        <SettingsModal
          isOpen={isSettingsOpen}
          settings={modelSettings}
          onClose={() => setIsSettingsOpen(false)}
          onSave={saveModelSettings}
        />
      )}
    </div>
  );
}

export default App;
