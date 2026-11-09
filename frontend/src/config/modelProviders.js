export const MODEL_PROVIDERS = {
    groq: {
        label: 'Groq',
        model: 'openai/gpt-oss-120b',
        keyUrl: 'https://console.groq.com/keys',
    },
    openai: {
        label: 'OpenAI',
        model: 'gpt-4.1-mini',
        keyUrl: 'https://platform.openai.com/api-keys',
    },
    anthropic: {
        label: 'Anthropic',
        model: 'claude-haiku-5-5',
        keyUrl: 'https://console.anthropic.com/settings/keys',
    },
    gemini: {
        label: 'Google Gemini',
        model: 'gemini-3.8-flash',
        keyUrl: 'https://aistudio.google.com/app/apikey',
    },
};
