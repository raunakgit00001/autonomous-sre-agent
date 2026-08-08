'use client';

import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  Zap,
  HardDrive,
  Cpu,
  CheckCircle2,
  XCircle,
  Clock,
  Database,
  ArrowRight,
  RefreshCw,
  AlertTriangle,
  Send,
  Sparkles,
  Server
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';

interface Postmortem {
  id: string;
  title: string;
  similarity_score?: number;
  root_cause: string;
}

interface TimelineStep {
  step: string;
  timestamp: string;
  detail: string;
}

interface Incident {
  id: string;
  type: string;
  title: string;
  service: string;
  severity: string;
  status: string;
  created_at: string;
  updated_at: string;
  autonomy_tier: string;
  risk_level: string;
  confidence: number;
  blast_radius: string;
  proposed_action: string;
  retrieved_postmortems: Postmortem[];
  hypothesis?: string;
  timeline: TimelineStep[];
  slack_ts?: string;
}

export default function SreDashboard() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [selectedIncident, setSelectedIncident] = useState<string | null>(null);
  const [triggeringType, setTriggeringType] = useState<string | null>(null);

  const fetchIncidents = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/incidents`);
      if (res.ok) {
        const data = await res.json();
        setIncidents(data.incidents || []);
        if (data.incidents?.length > 0 && !selectedIncident) {
          setSelectedIncident(data.incidents[0].id);
        }
      }
    } catch (err) {
      console.error('Error polling incidents:', err);
    }
  };

  useEffect(() => {
    fetchIncidents();
    const interval = setInterval(fetchIncidents, 1500);
    return () => clearInterval(interval);
  }, []);

  const triggerIncident = async (type: string) => {
    setTriggeringType(type);
    try {
      const res = await fetch(`${API_BASE}/api/incidents/trigger`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type }),
      });
      if (res.ok) {
        const data = await res.json();
        setSelectedIncident(data.incident_id);
        await fetchIncidents();
      }
    } catch (err) {
      console.error('Trigger error:', err);
    } finally {
      setTriggeringType(null);
    }
  };

  const handleLocalApproval = async (incidentId: string, approved: boolean) => {
    try {
      await fetch(`${API_BASE}/api/incidents/${incidentId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved, operator: 'Dashboard Web User' }),
      });
      await fetchIncidents();
    } catch (err) {
      console.error('Approval error:', err);
    }
  };

  const activeIncident = incidents.find((i) => i.id === selectedIncident) || incidents[0];

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col font-sans">
      {/* Top Navigation Bar */}
      <header className="border-b border-slate-800 bg-[#0d1322] px-6 py-4 flex items-center justify-between shadow-lg">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-purple-600/20 border border-purple-500/30 rounded-xl text-purple-400">
            <Cpu className="w-6 h-6 animate-pulse" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-purple-400 via-cyan-400 to-emerald-400 bg-clip-text text-transparent">
              Autonomous SRE Agent
            </h1>
            <p className="text-xs text-slate-400 flex items-center gap-2">
              <span className="inline-block w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span>
              Live Telemetry Stream • API Base: <code className="text-slate-300 px-1 py-0.5 bg-slate-800 rounded">{API_BASE}</code>
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <div className="text-right hidden sm:block">
            <div className="text-xs text-slate-400">Active Monitoring</div>
            <div className="text-sm font-semibold text-emerald-400 flex items-center justify-end gap-1">
              <Server className="w-3.5 h-3.5" /> 3 Nodes Protected
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 p-6 max-w-7xl mx-auto w-full space-y-6">
        
        {/* Incident Trigger Buttons Section */}
        <section className="glass-panel p-5 rounded-2xl border border-slate-800 bg-slate-900/60 shadow-xl">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-base font-semibold text-slate-200 flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-purple-400" /> Simulate Infrastructure Incidents
              </h2>
              <p className="text-xs text-slate-400">
                Trigger real-time incident detection, vector postmortem search, LLM reasoning, and confidence-gated autonomy.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Memory Leak (Human Escalation Path) */}
            <button
              id="btn-trigger-memory-leak"
              onClick={() => triggerIncident('memory_leak')}
              disabled={triggeringType === 'memory_leak'}
              className="group text-left p-4 rounded-xl border border-amber-500/30 bg-amber-950/20 hover:bg-amber-950/40 hover:border-amber-500/60 transition-all duration-200 shadow-md relative overflow-hidden"
            >
              <div className="flex justify-between items-start mb-2">
                <div className="p-2 bg-amber-500/20 rounded-lg text-amber-400">
                  <ShieldAlert className="w-5 h-5" />
                </div>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-500/40 text-amber-300">
                  ✋ Escalates to Slack
                </span>
              </div>
              <h3 className="font-semibold text-sm text-slate-100 group-hover:text-amber-300 transition-colors">
                Auth Memory Leak
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                Medium Risk • High memory pressure triggers Slack approval loop with Blast Radius.
              </p>
            </button>

            {/* DB High Latency (Autonomous Path) */}
            <button
              id="btn-trigger-high-latency"
              onClick={() => triggerIncident('high_latency')}
              disabled={triggeringType === 'high_latency'}
              className="group text-left p-4 rounded-xl border border-emerald-500/30 bg-emerald-950/20 hover:bg-emerald-950/40 hover:border-emerald-500/60 transition-all duration-200 shadow-md relative overflow-hidden"
            >
              <div className="flex justify-between items-start mb-2">
                <div className="p-2 bg-emerald-500/20 rounded-lg text-emerald-400">
                  <Zap className="w-5 h-5" />
                </div>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 border border-emerald-500/40 text-emerald-300">
                  ⚡ 100% Autonomous
                </span>
              </div>
              <h3 className="font-semibold text-sm text-slate-100 group-hover:text-emerald-300 transition-colors">
                API Latency Spike
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                Low Risk • High confidence auto-scales replicas with zero human intervention.
              </p>
            </button>

            {/* Disk Full (Autonomous Path) */}
            <button
              id="btn-trigger-disk-full"
              onClick={() => triggerIncident('disk_full')}
              disabled={triggeringType === 'disk_full'}
              className="group text-left p-4 rounded-xl border border-cyan-500/30 bg-cyan-950/20 hover:bg-cyan-950/40 hover:border-cyan-500/60 transition-all duration-200 shadow-md relative overflow-hidden"
            >
              <div className="flex justify-between items-start mb-2">
                <div className="p-2 bg-cyan-500/20 rounded-lg text-cyan-400">
                  <HardDrive className="w-5 h-5" />
                </div>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-cyan-500/20 border border-cyan-500/40 text-cyan-300">
                  ⚡ 100% Autonomous
                </span>
              </div>
              <h3 className="font-semibold text-sm text-slate-100 group-hover:text-cyan-300 transition-colors">
                Node Disk Full
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                Low Risk • Automatically truncates raw access logs & rotates storage.
              </p>
            </button>
          </div>
        </section>

        {/* Incidents Stream & Detail View Split Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* Left Column: Live Incident Feed */}
          <div className="lg:col-span-5 space-y-3">
            <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between">
              <span>Incidents Feed ({incidents.length})</span>
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-slate-500" />
            </h3>

            {incidents.length === 0 ? (
              <div className="p-8 text-center glass-panel rounded-2xl text-slate-500 text-sm">
                No active incidents. Click a button above to simulate an incident!
              </div>
            ) : (
              <div className="space-y-3 max-h-[650px] overflow-y-auto pr-1">
                {incidents.map((incident) => {
                  const isSelected = incident.id === activeIncident?.id;
                  const isAutonomous = incident.autonomy_tier === 'AUTO_EXECUTE';
                  const isResolved = incident.status === 'RESOLVED';
                  const isAwaiting = incident.status === 'AWAITING_APPROVAL';

                  return (
                    <div
                      key={incident.id}
                      onClick={() => setSelectedIncident(incident.id)}
                      className={`p-4 rounded-xl border transition-all cursor-pointer ${
                        isSelected
                          ? 'bg-slate-800/90 border-purple-500/60 shadow-lg shadow-purple-950/30'
                          : 'bg-slate-900/40 border-slate-800/80 hover:bg-slate-800/40'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-mono font-bold text-slate-400">
                          {incident.id}
                        </span>
                        
                        {/* Instant Visual Autonomy Badge */}
                        {isAutonomous ? (
                          <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
                            <Zap className="w-3 h-3" /> Autonomous (0 Human Checks)
                          </span>
                        ) : (
                          <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3" /> Human Approval Required
                          </span>
                        )}
                      </div>

                      <h4 className="font-semibold text-sm text-slate-100 mb-1">
                        {incident.title}
                      </h4>

                      <div className="flex items-center justify-between text-xs text-slate-400 mt-2">
                        <span className="flex items-center gap-1">
                          Service: <span className="text-slate-300 font-mono">{incident.service}</span>
                        </span>
                        
                        {isResolved ? (
                          <span className="text-emerald-400 font-semibold flex items-center gap-1">
                            <CheckCircle2 className="w-3.5 h-3.5" /> RESOLVED
                          </span>
                        ) : isAwaiting ? (
                          <span className="text-amber-400 font-semibold animate-pulse flex items-center gap-1">
                            <Clock className="w-3.5 h-3.5" /> AWAITING APPROVAL
                          </span>
                        ) : (
                          <span className="text-cyan-400 font-semibold flex items-center gap-1">
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" /> {incident.status}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right Column: Reasoning Trace & Decision Timeline */}
          <div className="lg:col-span-7">
            {activeIncident ? (
              <div className="glass-panel p-6 rounded-2xl border border-slate-800 bg-slate-900/80 shadow-2xl space-y-6">
                
                {/* Incident Header & Meta */}
                <div className="border-b border-slate-800 pb-4 flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-mono px-2 py-0.5 bg-slate-800 text-purple-400 rounded">
                        {activeIncident.id}
                      </span>
                      <span className="text-xs font-semibold px-2 py-0.5 bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded">
                        SEVERITY: {activeIncident.severity}
                      </span>
                    </div>
                    <h3 className="text-lg font-bold text-slate-100">
                      {activeIncident.title}
                    </h3>
                  </div>

                  {/* Autonomy Tier Card */}
                  <div className="text-right">
                    <div className="text-xs text-slate-400">Confidence Score</div>
                    <div className="text-lg font-extrabold text-cyan-400">
                      {Math.round(activeIncident.confidence * 100)}%
                    </div>
                  </div>
                </div>

                {/* Vector Postmortem Retrieval Callout */}
                {activeIncident.retrieved_postmortems?.length > 0 && (
                  <div className="p-4 rounded-xl bg-purple-950/20 border border-purple-500/30 space-y-2">
                    <div className="flex items-center justify-between text-xs text-purple-300 font-semibold">
                      <span className="flex items-center gap-1.5">
                        <Database className="w-4 h-4 text-purple-400" /> Vector Search Match (In-Process Similarity Engine)
                      </span>
                      <span className="px-2 py-0.5 bg-purple-500/20 rounded font-mono">
                        Cos Sim: {activeIncident.retrieved_postmortems[0].similarity_score}
                      </span>
                    </div>
                    <div className="text-sm font-semibold text-slate-100">
                      Ref Postmortem: <code className="text-purple-300 font-mono">{activeIncident.retrieved_postmortems[0].id}</code> — {activeIncident.retrieved_postmortems[0].title}
                    </div>
                    <p className="text-xs text-slate-400">
                      <strong className="text-slate-300">Historical Root Cause:</strong> {activeIncident.retrieved_postmortems[0].root_cause}
                    </p>
                  </div>
                )}

                {/* LLM Root Cause Hypothesis */}
                {activeIncident.hypothesis && (
                  <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 space-y-1">
                    <div className="text-xs font-semibold text-cyan-400 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5" /> LLM Root Cause Synthesis
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed italic">
                      "{activeIncident.hypothesis}"
                    </p>
                  </div>
                )}

                {/* Blast Radius Preview Callout */}
                <div className="p-4 rounded-xl bg-amber-950/20 border border-amber-500/30 flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                  <div>
                    <div className="text-xs font-bold text-amber-300">
                      Predicted Blast Radius Impact
                    </div>
                    <div className="text-xs text-slate-300 font-mono mt-0.5">
                      {activeIncident.blast_radius}
                    </div>
                  </div>
                </div>

                {/* Slack Approval Banner (if AWAITING_APPROVAL) */}
                {activeIncident.status === 'AWAITING_APPROVAL' && (
                  <div className="p-4 rounded-xl bg-amber-500/10 border-2 border-amber-500/50 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-bold text-amber-300 flex items-center gap-2">
                        <Send className="w-4 h-4 animate-bounce" /> Waiting for Slack Approval
                      </div>
                      <span className="text-xs text-amber-400/80 font-mono">
                        Posted to #sre-alerts
                      </span>
                    </div>
                    <p className="text-xs text-slate-300">
                      An interactive Slack message with working Approve / Deny buttons was dispatched. You can also simulate the Slack click directly below:
                    </p>
                    <div className="flex items-center gap-3 pt-1">
                      <button
                        onClick={() => handleLocalApproval(activeIncident.id, true)}
                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5 shadow-lg shadow-emerald-950/40"
                      >
                        <CheckCircle2 className="w-4 h-4" /> Approve & Execute
                      </button>
                      <button
                        onClick={() => handleLocalApproval(activeIncident.id, false)}
                        className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5 shadow-lg shadow-rose-950/40"
                      >
                        <XCircle className="w-4 h-4" /> Deny & Escalate
                      </button>
                    </div>
                  </div>
                )}

                {/* Execution Timeline Trace */}
                <div>
                  <h4 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                    Reasoning & Execution Trajectory
                  </h4>
                  <div className="space-y-2 relative before:absolute before:inset-0 before:left-2.5 before:w-0.5 before:bg-slate-800">
                    {activeIncident.timeline.map((step, idx) => (
                      <div key={idx} className="flex items-start gap-3 relative pl-6">
                        <div className="absolute left-1 top-1 w-3 h-3 rounded-full bg-purple-500 border-2 border-[#090d16]" />
                        <div className="flex-1 bg-slate-950/40 p-2.5 rounded-lg border border-slate-800/60 text-xs">
                          <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono mb-0.5">
                            <span className="font-bold text-purple-400">{step.step}</span>
                            <span>{new Date(step.timestamp).toLocaleTimeString()}</span>
                          </div>
                          <div className="text-slate-300">{step.detail}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>

              </div>
            ) : (
              <div className="p-12 text-center glass-panel rounded-2xl text-slate-500 text-sm">
                Select an incident from the feed to view reasoning details.
              </div>
            )}
          </div>

        </div>
      </main>
    </div>
  );
}
