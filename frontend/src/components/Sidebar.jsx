import React, { useEffect, useMemo, useState } from 'react';
import { X, Github, Linkedin, Plus, MessageSquare, RefreshCw, Settings, LogOut } from 'lucide-react';
import Logo from '../assets/logo.png';
import client from '../api/client';

const HISTORY_PAGE_SIZE = 50;

const formatDate = (value) => {
    if (!value) return '';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
};

const Sidebar = ({ onNewChat, onSelectConversation, onOpenSettings, onLogout, user, activeSessionId, historyVersion, isOpen, onClose }) => {
    const [historyRows, setHistoryRows] = useState([]);
    const [isLoadingHistory, setIsLoadingHistory] = useState(true);
    const [isLoadingOlder, setIsLoadingOlder] = useState(false);
    const [historyError, setHistoryError] = useState(false);
    const [hasMoreHistory, setHasMoreHistory] = useState(false);
    const [manualRefresh, setManualRefresh] = useState(0);

    useEffect(() => {
        let isCurrent = true;

        const loadHistory = async () => {
            setIsLoadingHistory(true);
            setHistoryError(false);
            try {
                const response = await client.get('/history', {
                    params: { limit: HISTORY_PAGE_SIZE, offset: 0 },
                });
                if (!isCurrent) return;
                const rows = Array.isArray(response.data) ? response.data : [];
                setHistoryRows(rows);
                setHasMoreHistory(rows.length === HISTORY_PAGE_SIZE);
            } catch {
                if (isCurrent) setHistoryError(true);
            } finally {
                if (isCurrent) setIsLoadingHistory(false);
            }
        };

        loadHistory();
        return () => { isCurrent = false; };
    }, [historyVersion, manualRefresh]);

    const conversations = useMemo(() => {
        const grouped = new Map();
        for (const row of historyRows) {
            if (!row.session_id) continue;
            if (!grouped.has(row.session_id)) grouped.set(row.session_id, []);
            grouped.get(row.session_id).push(row);
        }

        return [...grouped.entries()].map(([sessionId, turns]) => {
            turns.sort((a, b) => a.id - b.id);
            const messages = turns.flatMap(turn => {
                const timestamp = turn.created_at ? new Date(turn.created_at) : new Date();
                const items = [{ role: 'user', content: turn.question, timestamp }];
                if (turn.answer) {
                    items.push({ role: 'ai', content: turn.answer, source: turn.source, timestamp });
                }
                return items;
            });
            return {
                sessionId,
                title: turns[0]?.question || 'New conversation',
                lastActivity: turns[turns.length - 1]?.created_at,
                messages,
            };
        });
    }, [historyRows]);

    const loadOlderHistory = async () => {
        if (isLoadingOlder || !hasMoreHistory) return;
        setIsLoadingOlder(true);
        try {
            const response = await client.get('/history', {
                params: { limit: HISTORY_PAGE_SIZE, offset: historyRows.length },
            });
            const rows = Array.isArray(response.data) ? response.data : [];
            setHistoryRows(current => [...current, ...rows]);
            setHasMoreHistory(rows.length === HISTORY_PAGE_SIZE);
        } catch {
            setHistoryError(true);
        } finally {
            setIsLoadingOlder(false);
        }
    };

    const openConversation = (conversation) => {
        onSelectConversation?.({ sessionId: conversation.sessionId, messages: conversation.messages });
        onClose?.();
    };

    return (
        <div className={`w-[280px] md:w-[320px] h-screen bg-gradient-to-b from-[#4361ee] to-[#3a0ca3] text-white fixed left-0 top-0 z-50 flex flex-col shadow-2xl overflow-hidden transition-transform duration-500 cubic-bezier(0.2, 0.8, 0.2, 1) ${isOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}>
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.15),transparent)] pointer-events-none z-0"></div>
            <div className="absolute top-[-10%] left-[-10%] w-32 h-32 bg-purple-400/30 rounded-full blur-3xl pointer-events-none z-0"></div>
            <div className="absolute bottom-[10%] right-[-10%] w-40 h-40 bg-blue-400/20 rounded-full blur-3xl pointer-events-none z-0"></div>

            <button
                onClick={onClose}
                aria-label="Close sidebar"
                className="md:hidden absolute top-4 right-4 p-2 text-white/80 hover:text-white transition-colors z-20"
            >
                <X size={24} />
            </button>

            <div className="p-6 md:p-8 flex flex-col h-full min-h-0 relative z-10 font-sans">
                <div className="text-center mb-6 shrink-0 mt-8 md:mt-0">
                    <div className="mx-auto mb-3 flex items-center justify-center">
                        <img src={Logo} alt="TrueWealth AI Logo" className="w-16 h-16 object-contain drop-shadow-lg" />
                    </div>
                    <h1 className="text-2xl font-bold tracking-tight mb-1">TrueWealth AI</h1>
                    <p className="text-xs font-light text-blue-200 uppercase tracking-widest">Financial Strategist</p>
                </div>

                <section className="flex-1 min-h-0 flex flex-col" aria-label="Chat history">
                    <div className="flex items-center justify-between mb-3 px-1 shrink-0">
                        <h2 className="text-xs font-semibold text-blue-200 uppercase tracking-wider">Recent chats</h2>
                        <button
                            onClick={() => setManualRefresh(value => value + 1)}
                            aria-label="Refresh chat history"
                            title="Refresh chat history"
                            className="p-1.5 rounded-lg text-white/70 hover:text-white hover:bg-white/10 transition-colors"
                        >
                            <RefreshCw size={15} />
                        </button>
                    </div>
                    <div className="flex-1 min-h-0 overflow-y-auto space-y-1 pr-1">
                        {isLoadingHistory && conversations.length === 0 && (
                            <p className="px-3 py-2 text-sm text-blue-100/70">Loading chats…</p>
                        )}
                        {historyError && conversations.length === 0 && !isLoadingHistory && (
                            <p className="px-3 py-2 text-sm text-blue-100/80">Could not load chat history.</p>
                        )}
                        {!isLoadingHistory && !historyError && conversations.length === 0 && (
                            <p className="px-3 py-2 text-sm text-blue-100/70">Your saved chats will appear here.</p>
                        )}
                        {conversations.map(conversation => (
                            <button
                                key={conversation.sessionId}
                                onClick={() => openConversation(conversation)}
                                title={conversation.title}
                                aria-current={activeSessionId === conversation.sessionId ? 'true' : undefined}
                                className={`w-full text-left px-3 py-2.5 rounded-xl transition-colors ${activeSessionId === conversation.sessionId ? 'bg-white/20' : 'hover:bg-white/10'}`}
                            >
                                <span className="flex items-center gap-2 min-w-0">
                                    <MessageSquare size={15} className="shrink-0 text-blue-200" />
                                    <span className="truncate text-sm font-medium">{conversation.title}</span>
                                </span>
                                <span className="block pl-[23px] mt-1 text-[11px] text-blue-200/80">
                                    {formatDate(conversation.lastActivity)}
                                </span>
                            </button>
                        ))}
                        {hasMoreHistory && (
                            <button
                                onClick={loadOlderHistory}
                                disabled={isLoadingOlder}
                                className="w-full px-3 py-2 text-sm text-blue-100 hover:text-white disabled:opacity-60"
                            >
                                {isLoadingOlder ? 'Loading…' : 'Load older chats'}
                            </button>
                        )}
                    </div>
                </section>

                <div className="mt-4 shrink-0">
                    <div className="bg-white/10 p-4 rounded-2xl mb-4 backdrop-blur-sm border border-white/10">
                        <p className="text-xs font-semibold text-blue-200 uppercase tracking-wider mb-3">Signed in</p>
                        <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-full bg-blue-500/30 flex items-center justify-center text-sm font-bold border border-white/20">
                                {(user?.username || 'U').slice(0, 2).toUpperCase()}
                            </div>
                            <div>
                                <p className="font-medium text-sm">{user?.username}</p>
                                <p className="text-xs text-blue-200">{user?.email}</p>
                            </div>
                        </div>
                        <div className="mt-4 grid grid-cols-2 gap-2 border-t border-white/10 pt-3">
                            <a
                                href="https://www.linkedin.com/in/siddhartha-sagi/"
                                aria-label="LinkedIn profile"
                                title="LinkedIn"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-xs font-medium text-white/80 transition-colors hover:border-white/25 hover:bg-white/15 hover:text-white"
                            >
                                <Linkedin size={16} />
                                <span>LinkedIn</span>
                            </a>
                            <a
                                href="https://github.com/space-rock-0/TrueWealth-"
                                aria-label="GitHub profile"
                                title="GitHub"
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-xs font-medium text-white/80 transition-colors hover:border-white/25 hover:bg-white/15 hover:text-white"
                            >
                                <Github size={16} />
                                <span>GitHub</span>
                            </a>
                        </div>
                    </div>
                    <button
                        onClick={onLogout}
                        className="w-full mb-3 rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/20 flex items-center justify-center gap-2"
                    >
                        <LogOut size={17} />
                        <span>Sign out</span>
                    </button>
                    <button
                        onClick={() => { onOpenSettings?.(); onClose?.(); }}
                        className="w-full mb-3 rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/20 flex items-center justify-center gap-2"
                    >
                        <Settings size={17} />
                        <span>AI Provider Settings</span>
                    </button>
                    <button
                        onClick={onNewChat}
                        className="group w-full bg-white text-[#4361ee] py-3.5 px-6 rounded-2xl font-bold shadow-lg shadow-black/10 transition-all hover:shadow-xl hover:-translate-y-0.5 flex items-center justify-center gap-3"
                    >
                        <Plus size={20} strokeWidth={3} className="group-hover:rotate-90 transition-transform duration-300" />
                        <span>New Chat</span>
                    </button>
                </div>
            </div>
        </div>
    );
};

export default Sidebar;
