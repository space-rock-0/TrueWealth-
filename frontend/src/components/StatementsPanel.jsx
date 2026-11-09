import React, { useCallback, useEffect, useMemo, useState } from 'react';
import client from '../api/client';

const money = value => Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const maxOcrPages = import.meta.env.VITE_MAX_OCR_PAGES || 20;
const errorText = e => typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Request failed. Please retry.';

export default function StatementsPanel({ modelSettings }) {
  const [documents, setDocuments] = useState([]);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [year, setYear] = useState('all');
  const [quarter, setQuarter] = useState('all');
  const [currency, setCurrency] = useState('all');
  const [summary, setSummary] = useState(null);

  const headers = () => ({
    'X-LLM-Provider': modelSettings.provider,
    'X-LLM-Model': modelSettings.model,
    ...(modelSettings.apiKeys?.[modelSettings.provider] ? { 'X-LLM-API-Key': modelSettings.apiKeys[modelSettings.provider] } : {}),
  });
  const refresh = useCallback(async () => {
    try { const { data } = await client.get('/statements'); setDocuments(data); }
    catch (e) { setError(errorText(e)); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (!documents.some(doc => doc.status === 'processing')) return;
    const timer = setTimeout(refresh, 3000);
    return () => clearTimeout(timer);
  }, [documents, refresh]);
  useEffect(() => {
    if (selected?.status !== 'processing') return;
    const timer = setTimeout(() => client.get(`/statements/${selected.id}`).then(({ data }) => setSelected(data)).catch(e => setError(errorText(e))), 3000);
    return () => clearTimeout(timer);
  }, [selected]);
  useEffect(() => {
    let current = true;
    client.get('/statements/analytics/summary', { params: { ...(year !== 'all' ? { year } : {}), ...(quarter !== 'all' ? { quarter } : {}) } })
      .then(({ data }) => { if (current) setSummary(data); }).catch(e => { if (current) setError(errorText(e)); });
    return () => { current = false; };
  }, [documents, year, quarter]);

  const open = async id => {
    setError(''); setAnswer('');
    try { const { data } = await client.get(`/statements/${id}`); setSelected(data); }
    catch (e) { setError(errorText(e)); }
  };
  const analyze = async id => {
    await client.post(`/statements/${id}/analyze-background`, {}, { headers: headers() });
    for (let attempt = 0; attempt < 100; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 2000));
      const { data } = await client.get(`/statements/${id}`);
      setSelected(data);
      if (data.status === 'completed') return data;
      if (data.status === 'failed') throw new Error(data.error || 'Analysis failed.');
    }
    throw new Error('Analysis is still processing. Reopen the statement to check its status.');
  };
  const uploadBatch = async event => {
    const files = [...event.target.files]; event.target.value = '';
    if (!files.length) return;
    if (files.length > 10) { setError('Select at most 10 files per batch.'); return; }
    setBusy(true); setError(''); const failures = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i]; setProgress(`${i + 1}/${files.length}: ${file.name}`);
      try {
        if (file.size > 10 * 1024 * 1024) throw new Error('File exceeds 10 MB.');
        const content = await new Promise((resolve, reject) => {
          const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]);
          reader.onerror = reject; reader.readAsDataURL(file);
        });
        const { data } = await client.post('/statements', { filename: file.name, content });
        await refresh();
        if (data.status === 'completed' || data.status === 'processing') await open(data.id);
        else await analyze(data.id);
      } catch (e) { failures.push(`${file.name}: ${e.response ? errorText(e) : e.message}`); }
    }
    await refresh(); setBusy(false); setProgress(''); setError(failures.join(' '));
  };
  const rows = useMemo(() => (selected?.transactions || []).filter(tx =>
    (year === 'all' || tx.date.startsWith(year)) &&
    (quarter === 'all' || Math.ceil(Number(tx.date.slice(5, 7)) / 3) === Number(quarter)) &&
    (currency === 'all' || tx.currency === currency)
  ), [selected, year, quarter, currency]);
  const totals = useMemo(() => {
    const groups = {};
    for (const tx of rows) {
      const group = groups[tx.currency] ||= { credit: 0, debit: 0 };
      group.credit += Math.round(Number(tx.credit) * 100); group.debit += Math.round(Number(tx.debit) * 100);
    }
    return groups;
  }, [rows]);
  const years = [...new Set((selected?.transactions || []).map(tx => tx.date.slice(0, 4)))].sort();
  const currencies = [...new Set((selected?.transactions || []).map(tx => tx.currency))].sort();
  const exportCsv = async () => {
    try {
      const { data } = await client.get(`/statements/${selected.id}/export`, { responseType: 'blob' });
      const url = URL.createObjectURL(data); const a = document.createElement('a');
      a.href = url; a.download = `statement-${selected.id}.csv`; a.click(); URL.revokeObjectURL(url);
    } catch (e) { setError(errorText(e)); }
  };
  const exportReport = async () => {
    try {
      const { data } = await client.get(`/statements/${selected.id}/report`, { responseType: 'blob' });
      const url = URL.createObjectURL(data); const a = document.createElement('a');
      a.href = url; a.download = `statement-${selected.id}.md`; a.click(); URL.revokeObjectURL(url);
    } catch (e) { setError(errorText(e)); }
  };
  const retry = async () => {
    setBusy(true); setError('');
    try { await analyze(selected.id); } catch (e) { setError(errorText(e)); }
    finally { setBusy(false); refresh(); }
  };
  const ask = async event => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const { data } = await client.post(`/statements/${selected.id}/question`, { question }, { headers: headers(), timeout: 180000 });
      setAnswer(data.answer);
    } catch (e) { setError(errorText(e)); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!window.confirm('Permanently delete this statement and its extracted transactions?')) return;
    try { await client.post(`/statements/${selected.id}/delete`); setSelected(null); await refresh(); }
    catch (e) { setError(errorText(e)); }
  };
  const exportDashboard = () => {
    const lines = ['# TrueWealth AI financial dashboard', '', `Period: ${year} / quarter ${quarter}`, ''];
    for (const [code, group] of Object.entries(summary?.currencies || {})) {
      lines.push(`## ${code}`, `Credits: ${money(group.credits)}`, `Debits: ${money(group.debits)}`, `Net: ${money(group.net)}`, '', '| Month | Credits | Debits |', '| --- | ---: | ---: |');
      for (const [month, values] of Object.entries(group.months).sort()) lines.push(`| ${month} | ${money(values.credits)} | ${money(values.debits)} |`);
      lines.push('');
    }
    lines.push('AI-extracted amounts require comparison with original statements. Overlapping statements may include duplicate transactions.');
    const url = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/markdown' }));
    const a = document.createElement('a'); a.href = url; a.download = 'truewealth-financial-summary.md'; a.click(); URL.revokeObjectURL(url);
  };
  const button = 'rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-100 disabled:opacity-50';
  return <section className="statements-workspace flex-1 overflow-y-auto p-5 md:p-8 text-slate-800">
    <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
      <div><h1 className="text-2xl font-bold">Bank statements</h1><p className="text-sm text-slate-500">Upload, analyze, and ask about your financial documents.</p></div>
      <label className={`${button} cursor-pointer bg-blue-600! text-white!`}>
        Upload and analyze<input aria-label="Upload bank statements" className="sr-only" type="file" accept=".pdf,.csv,.txt" multiple disabled={busy} onChange={uploadBatch} />
      </label>
    </div>
    <p className="text-xs text-slate-500 mb-4">PDF, CSV, or TXT · up to 10 files per batch · 10 MB each. Uses your selected AI provider. Text is redacted for common account numbers and emails before storage and AI processing; review documents for other personal details before uploading. Scanned pages use server OCR (up to {maxOcrPages} scanned pages per file).</p>
    {busy && <p role="status" className="mb-3 text-blue-600">{progress || 'Processing… Keep this page open.'}</p>}
    {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 p-3 text-red-700">{error}</p>}
    <details className="mb-5 rounded-2xl border border-slate-200 bg-white/90 p-4" open={!selected}>
      <summary className="font-semibold cursor-pointer">Financial dashboard · {summary?.statement_count || 0} analyzed statements</summary>
      <button onClick={exportDashboard} className={`${button} mt-3`}>Download dashboard report</button>
      <div className="flex gap-2 my-3"><input aria-label="Dashboard year" placeholder="All years" type="number" min="1900" max="2200" value={year === 'all' ? '' : year} onChange={e => setYear(e.target.value || 'all')} className={`${button} w-32`} /><select aria-label="Dashboard quarter" value={quarter} onChange={e => setQuarter(e.target.value)} className={button}><option value="all">Full year</option>{[1, 2, 3, 4].map(q => <option key={q} value={q}>Q{q}</option>)}</select></div>
      {Object.entries(summary?.currencies || {}).map(([code, group]) => <div key={code} className="mb-4"><h3 className="font-semibold mb-2">{code} · {group.count} transactions</h3><p className="text-sm mb-2">Credits {money(group.credits)} · Debits {money(group.debits)} · Net {money(group.net)}</p><div className="grid md:grid-cols-2 gap-4"><div><h4 className="text-sm font-semibold">Monthly cash flow</h4>{Object.entries(group.months).sort().map(([month, values]) => <div key={month} className="text-xs flex justify-between border-b py-2 gap-3"><span>{month}</span><span className="text-emerald-700">+{money(values.credits)}</span><span className="text-red-600">−{money(values.debits)}</span></div>)}</div><div><h4 className="text-sm font-semibold">Debit categories</h4>{Object.entries(group.categories).sort((a, b) => Number(b[1]) - Number(a[1])).map(([category, amount]) => <div key={category} className="text-xs flex justify-between border-b py-2"><span>{category}</span><span>{money(amount)}</span></div>)}</div></div></div>)}
      {!Object.keys(summary?.currencies || {}).length && <p className="text-sm text-slate-500">Analyze a statement to see monthly totals and spending categories.</p>}
    </details>
    <div className="grid lg:grid-cols-[240px_1fr] gap-5">
      <aside className="space-y-2"><h2 className="font-semibold">Document history</h2>
        {!documents.length && <p className="text-sm text-slate-500">Your uploaded statements will appear here.</p>}
        {documents.map(doc => <button key={doc.id} onClick={() => open(doc.id)} className={`${button} w-full text-left ${selected?.id === doc.id ? 'border-blue-500' : ''}`}>
          <span className="block truncate">{doc.filename}</span><span className="text-xs text-slate-500">{doc.status} · {doc.transaction_count} transactions</span>
        </button>)}
      </aside>
      {selected && <article className="min-w-0 rounded-2xl bg-white/90 border border-slate-200 p-5">
        <div className="flex flex-wrap justify-between gap-2 mb-4"><h2 className="font-bold truncate">{selected.filename}</h2>
          <div className="flex flex-wrap gap-2"><button className={button} disabled={busy} onClick={retry}>Analyze again</button><button className={button} onClick={exportCsv}>Export CSV</button><button className={button} onClick={exportReport}>Markdown report</button><button className={button} onClick={() => window.print()}>Print / PDF</button><button className={`${button} text-red-600`} disabled={busy} onClick={remove}>Delete</button></div>
        </div>
        {selected.error && <p className="text-red-600 text-sm mb-3">{selected.error}</p>}
        <div className="flex gap-2 mb-4 flex-wrap">
          <select aria-label="Year" className={button} value={year} onChange={e => setYear(e.target.value)}><option value="all">All years</option>{years.map(y => <option key={y}>{y}</option>)}</select>
          <select aria-label="Quarter" className={button} value={quarter} onChange={e => setQuarter(e.target.value)}><option value="all">All quarters</option>{[1, 2, 3, 4].map(q => <option key={q} value={q}>Q{q}</option>)}</select>
          <select aria-label="Currency" className={button} value={currency} onChange={e => setCurrency(e.target.value)}><option value="all">All currencies</option>{currencies.map(c => <option key={c}>{c}</option>)}</select>
        </div>
        {Object.entries(totals).map(([code, total]) => <div key={code} className="mb-4 grid grid-cols-3 gap-3 rounded-xl bg-slate-50 p-4 text-sm"><div>Credits ({code})<strong className="block text-emerald-700">{money(total.credit / 100)}</strong></div><div>Debits<strong className="block text-red-600">{money(total.debit / 100)}</strong></div><div>Net<strong className="block">{money((total.credit - total.debit) / 100)}</strong></div></div>)}
        <div className="overflow-x-auto max-h-96"><table className="w-full text-sm text-left"><thead><tr>{['Date', 'Description', 'Category', 'Credit', 'Debit', 'Currency'].map(h => <th className="p-2 border-b" key={h}>{h}</th>)}</tr></thead><tbody>{rows.map((tx, i) => <tr key={i}>{[tx.date, tx.description, tx.category, money(tx.credit), money(tx.debit), tx.currency].map((v, j) => <td className="p-2 border-b border-slate-100" key={j}>{v}</td>)}</tr>)}</tbody></table></div>
        <p className="text-xs text-amber-700 my-4">AI extraction can contain mistakes. Compare the transactions with the original statement. Credits and debits are cash flows; transfers are not necessarily income or spending.</p>
        <form onSubmit={ask} className="flex gap-2"><input aria-label="Question about this statement" required maxLength={2000} value={question} onChange={e => setQuestion(e.target.value)} placeholder="Ask about this statement…" className="min-w-0 flex-1 border rounded-xl px-3 py-2" /><button className={button} disabled={busy}>Ask AI</button></form>
        {answer && <div className="mt-4 whitespace-pre-wrap text-sm leading-relaxed">{answer}</div>}
      </article>}
    </div>
  </section>;
}
