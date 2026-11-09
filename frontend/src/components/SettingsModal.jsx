import React, { useState } from 'react';
import { Eye, EyeOff, KeyRound, X } from 'lucide-react';
import { MODEL_PROVIDERS } from '../config/modelProviders';

const SettingsModal = ({ isOpen, settings, onClose, onSave }) => {
    const [draft, setDraft] = useState(() => ({ ...settings, apiKey: settings.apiKeys?.[settings.provider] || '' }));
    const [isKeyVisible, setIsKeyVisible] = useState(false);

    if (!isOpen) return null;

    const provider = MODEL_PROVIDERS[draft.provider] || MODEL_PROVIDERS.groq;
    const validModel = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,149}$/.test(draft.model.trim())
        && !draft.model.includes('..')
        && !draft.model.includes('//')
        && !draft.model.startsWith('/')
        && !draft.model.endsWith('/');

    const changeProvider = (nextProvider) => {
        setDraft(current => ({
            ...current,
            provider: nextProvider,
            model: MODEL_PROVIDERS[nextProvider].model,
            apiKey: current.apiKeys?.[nextProvider] || '',
        }));
    };

    return (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm" onMouseDown={onClose}>
            <section
                role="dialog"
                aria-modal="true"
                aria-labelledby="settings-title"
                className="w-full max-w-lg rounded-3xl bg-white p-6 text-slate-800 shadow-2xl md:p-8"
                onMouseDown={event => event.stopPropagation()}
            >
                <div className="mb-6 flex items-start justify-between gap-4">
                    <div>
                        <div className="mb-2 flex items-center gap-2 text-primary">
                            <KeyRound size={20} />
                            <span className="text-xs font-bold uppercase tracking-widest">AI provider</span>
                        </div>
                        <h2 id="settings-title" className="text-2xl font-bold">Settings</h2>
                        <p className="mt-1 text-sm text-slate-500">Choose the provider used for new AI responses.</p>
                    </div>
                    <button onClick={onClose} aria-label="Close settings" className="rounded-xl p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700">
                        <X size={20} />
                    </button>
                </div>

                <label className="mb-4 block">
                    <span className="mb-1.5 block text-sm font-semibold">Provider</span>
                    <select
                        value={draft.provider}
                        onChange={event => changeProvider(event.target.value)}
                        className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                    >
                        {Object.entries(MODEL_PROVIDERS).map(([id, item]) => (
                            <option key={id} value={id}>{item.label}</option>
                        ))}
                    </select>
                </label>

                <label className="mb-4 block">
                    <span className="mb-1.5 block text-sm font-semibold">Model ID</span>
                    <input
                        value={draft.model}
                        onChange={event => setDraft(current => ({ ...current, model: event.target.value }))}
                        autoComplete="off"
                        spellCheck="false"
                        className="w-full rounded-xl border border-slate-200 px-4 py-3 font-mono text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                        placeholder={provider.model}
                    />
                    <span className={`mt-1 block text-xs ${validModel ? 'text-slate-500' : 'text-rose-600'}`}>
                        {validModel ? `Use a model ID supported by ${provider.label}.` : 'Enter a valid model ID.'}
                    </span>
                </label>

                <label className="mb-3 block">
                    <span className="mb-1.5 block text-sm font-semibold">API key</span>
                    <span className="relative block">
                        <input
                            type={isKeyVisible ? 'text' : 'password'}
                            value={draft.apiKey}
                            onChange={event => setDraft(current => ({ ...current, apiKey: event.target.value }))}
                            autoComplete="new-password"
                            spellCheck="false"
                            className="w-full rounded-xl border border-slate-200 px-4 py-3 pr-12 font-mono text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                            placeholder="Paste your provider API key"
                        />
                        <button
                            type="button"
                            onClick={() => setIsKeyVisible(visible => !visible)}
                            aria-label={isKeyVisible ? 'Hide API key' : 'Show API key'}
                            className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                        >
                            {isKeyVisible ? <EyeOff size={18} /> : <Eye size={18} />}
                        </button>
                    </span>
                    <span className="mt-1 block text-xs text-slate-500">Leave blank to use a server-configured key, if available.</span>
                </label>

                <div className="mb-5 flex items-start gap-2 text-xs leading-relaxed text-slate-500">
                    <input
                        id="remember-api-key"
                        type="checkbox"
                        checked={Boolean(draft.rememberKey)}
                        onChange={event => setDraft(current => ({ ...current, rememberKey: event.target.checked }))}
                        className="mt-0.5 accent-primary"
                    />
                    <label htmlFor="remember-api-key">Remember key in this browser. If unchecked, it is kept only for this browser tab.</label>
                </div>

                <p className="mb-5 rounded-xl bg-slate-50 p-3 text-xs leading-relaxed text-slate-500">
                    The key is sent to this app’s backend with each chat so it can call {provider.label}. This app does not save it in chat history. Use HTTPS when deployed.{' '}
                    <a href={provider.keyUrl} target="_blank" rel="noreferrer" className="font-semibold text-primary underline">Get a key</a>
                </p>

                <div className="flex justify-end gap-3">
                    <button onClick={onClose} className="rounded-xl px-4 py-3 text-sm font-semibold text-slate-600 hover:bg-slate-100">Cancel</button>
                    <button
                        onClick={() => onSave({ ...draft, apiKey: draft.apiKey.trim(), model: draft.model.trim() })}
                        disabled={!validModel}
                        className="rounded-xl bg-primary px-5 py-3 text-sm font-bold text-white shadow-lg shadow-blue-500/20 hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        Save settings
                    </button>
                </div>
            </section>
        </div>
    );
};

export default SettingsModal;
