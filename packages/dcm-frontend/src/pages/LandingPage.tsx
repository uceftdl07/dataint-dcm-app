import { 
  ArrowRight, 
  BarChart3, 
  Cloud, 
  Database, 
  Factory, 
  Fingerprint,
  Network,
  Server,
  Shield, 
  Zap,
  Lock,
  Globe,
} from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import { InteractionStatus } from '@azure/msal-browser';
import { loginRequest } from '../config/msal';
import { FeatureCard } from '../components/domain';
import { LandingAccessGuide } from '../components/landing/LandingAccessGuide';

/** sessionStorage flag: set when the user explicitly starts a login from this page. */
const LOGIN_INITIATED_KEY = 'dcm.login.initiated';

const LandingPage: React.FC = () => {
  const [mounted, setMounted] = useState(false);
  const { instance, accounts, inProgress } = useMsal();
  const navigate = useNavigate();
  
  const [windowSize, setWindowSize] = useState({
    width: typeof window !== 'undefined' ? window.innerWidth : 1200,
    height: typeof window !== 'undefined' ? window.innerHeight : 800
  });

  useEffect(() => {
    setMounted(true);
    const handleResize = () => setWindowSize({
      width: window.innerWidth,
      height: window.innerHeight
    });
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // The landing page is public: never trigger authentication on load.
  // Only redirect to the dashboard when the user explicitly started a login
  // from this page (flag set in handleLogin) and MSAL finished the redirect flow.
  useEffect(() => {
    if (
      inProgress === InteractionStatus.None &&
      accounts.length > 0 &&
      sessionStorage.getItem(LOGIN_INITIATED_KEY)
    ) {
      sessionStorage.removeItem(LOGIN_INITIATED_KEY);
      navigate('/dashboard');
    }
  }, [accounts, inProgress, navigate]);

  const handleLogin = async () => {
    if (accounts.length > 0) {
      navigate('/dashboard');
      return;
    }
    try {
      sessionStorage.setItem(LOGIN_INITIATED_KEY, '1');
      await instance.loginRedirect(loginRequest);
    } catch (error) {
      sessionStorage.removeItem(LOGIN_INITIATED_KEY);
      console.error('Error while signing in:', error);
    }
  };

  const isMobile = windowSize.width < 768;
  const isTablet = windowSize.width >= 768 && windowSize.width < 1024;

  const getX = (x: number) => {
    const centerX = 500;
    const factor = isMobile ? 0.35 : isTablet ? 0.7 : 1;
    return centerX + (x - centerX) * factor;
  };

  const getY = (y: number) => {
    const centerY = 400;
    const factor = isMobile ? 1.2 : 1;
    return centerY + (y - centerY) * factor;
  };

  const DatabricksIcon = (
    <svg viewBox="0 0 18 18" className="w-5 h-5">
      <path d="M1.155,4.93v.512L9,9.868l7.006-3.957,0,1.6L9,11.491,1.55,7.258l-.395.22V10.54L9,14.955l7.006-3.942,0,1.586L9,16.581,1.55,12.347l-.395.22v.519L9,17.5l7.845-4.414V10.021l-.4-.218L9,14.036,1.992,10.054V8.476L9,12.414,16.845,8V4.978l-.4-.219L9,8.993,2.352,5.215,9,1.46l5.476,3.094.479-.269V3.863L9,.5Z" fill="currentColor"/>
    </svg>
  );

  const rawNodes = [
    { id: 'core-api', x: 500, y: 260, label: 'Gateway Groupe', color: '#7c3aed', icon: <Shield size={16} /> },
    { id: 'az-adf', x: 120, y: 320, label: 'Azure ADF', color: '#2563eb', icon: <Factory size={14} /> },
    { id: 'az-sql', x: 80, y: 550, label: 'Azure SQL', color: '#0ea5e9', icon: <Database size={14} /> },
    { id: 'az-dbx', x: 220, y: 450, label: 'Databricks', color: '#ff3621', icon: DatabricksIcon, isEngine: true },
    { id: 'aws-glue', x: 880, y: 320, label: 'AWS Glue', color: '#f97316', icon: <Zap size={14} /> },
    { id: 'aws-s3', x: 920, y: 580, label: 'AWS S3', color: '#eab308', icon: <Cloud size={14} /> },
    { id: 'aws-emr', x: 720, y: 420, label: 'AWS EMR', color: '#c2410c', icon: <Server size={14} /> },
    { id: 'core-lake', x: 500, y: 720, label: 'Lakebase', color: '#6d28d9', icon: <Network size={16} /> },
  ];

  const nodes = rawNodes.map(n => ({ ...n, x: getX(n.x), y: getY(n.y) }));

  const connections = [
    { from: 'core-api', to: 'az-adf', dur: '4s' },
    { from: 'core-api', to: 'aws-glue', dur: '4s' },
    { from: 'az-adf', to: 'az-dbx', dur: '3s' },
    { from: 'az-sql', to: 'az-dbx', dur: '4s' },
    { from: 'aws-glue', to: 'az-dbx', dur: '3.5s' },
    { from: 'aws-s3', to: 'az-dbx', dur: '5s' },
    { from: 'az-dbx', to: 'core-lake', dur: '4s' },
    { from: 'aws-emr', to: 'core-lake', dur: '6s' },
  ];

  return (
    <div className="min-h-screen bg-[#f1f5f9] text-slate-900 selection:bg-blue-100 overflow-x-hidden font-sans custom-scrollbar relative">
      
      {/* 🌌 DYNAMIC RESPONSIVE BACKGROUND */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0 bg-gradient-to-br from-slate-50 via-[#f8fafc] to-blue-50">
        <div className="absolute top-[-10%] left-[-10%] w-[60%] h-[60%] bg-blue-100/40 rounded-full blur-[120px] animate-mesh-1 pointer-events-none"></div>
        <div className="absolute bottom-[-10%] right-[-10%] w-[60%] h-[60%] bg-indigo-100/40 rounded-full blur-[120px] animate-mesh-2 pointer-events-none"></div>
        
        <svg className="absolute inset-0 w-full h-full opacity-40 transition-all duration-700" viewBox="0 0 1000 1000" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <filter id="glow-node-vibrant">
              <feGaussianBlur stdDeviation="3" result="coloredBlur"/><feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
            <linearGradient id="lineGradHigh" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#cbd5e1" /><stop offset="50%" stopColor="#94a3b8" /><stop offset="100%" stopColor="#cbd5e1" />
            </linearGradient>
          </defs>
          
          <g className="network-container">
            {connections.map((conn, idx) => {
              const from = nodes.find(n => n.id === conn.from)!;
              const to = nodes.find(n => n.id === conn.to)!;
              return (
                <g key={`conn-${idx}`} className="pointer-events-none">
                  <path d={`M ${from.x} ${from.y} Q ${(from.x + to.x) / 2} ${(from.y + to.y) / 2 - 50} ${to.x} ${to.y}`} fill="none" stroke="url(#lineGradHigh)" strokeWidth={isMobile ? "0.8" : "1.2"} strokeDasharray="4,2" />
                  <circle r={isMobile ? "1.2" : "2"} fill={from.color} filter="url(#glow-node-vibrant)">
                    <animateMotion dur={conn.dur} repeatCount="indefinite" path={`M ${from.x} ${from.y} Q ${(from.x + to.x) / 2} ${(from.y + to.y) / 2 - 50} ${to.x} ${to.y}`} />
                  </circle>
                </g>
              );
            })}

            {nodes.map((node) => (
              <g key={node.id} className={`node-group pointer-events-none ${node.isEngine ? 'engine-node' : ''}`}>
                <circle cx={node.x} cy={node.y} r={isMobile ? "30" : "40"} fill="transparent" />
                <circle cx={node.x} cy={node.y} r={isMobile ? "20" : "28"} fill={node.color} className="node-glow-vibrant" />
                <circle cx={node.x} cy={node.y} r={isMobile ? "10" : "14"} fill="white" stroke={node.color} strokeWidth={isMobile ? "1.5" : "2.5"} className="node-core pointer-events-none shadow-md" />
                <foreignObject x={node.x - (isMobile ? 6 : 8)} y={node.y - (isMobile ? 6 : 8)} width={isMobile ? "12" : "16"} height={isMobile ? "12" : "16"} className="node-icon pointer-events-none">
                  <div style={{ color: node.color }} className="flex items-center justify-center w-full h-full">
                    {node.icon}
                  </div>
                </foreignObject>
                <text x={node.x} y={node.y + (isMobile ? 25 : 35)} textAnchor="middle" fill="#1e293b" fontSize={isMobile ? "7" : "9"} fontWeight="900" letterSpacing="1" className="node-label uppercase select-none pointer-events-none">
                  {node.label}
                </text>
              </g>
            ))}
          </g>
        </svg>
        <div className="absolute inset-0 bg-[radial-gradient(#cbd5e1_1px,transparent_1px)] bg-[size:40px_40px] opacity-30 pointer-events-none"></div>
      </div>

      {/* 🚀 HEADER */}
      <div className="fixed top-4 md:top-6 left-0 w-full z-50 px-4 md:px-8 pointer-events-none">
        <nav className={`max-w-7xl mx-auto px-4 md:px-8 py-3 md:py-4 bg-white/80 backdrop-blur-3xl border border-white/40 rounded-[20px] md:rounded-[24px] shadow-xl flex items-center justify-between pointer-events-auto transition-all duration-1000 transform ${mounted ? 'translate-y-0 opacity-100' : '-translate-y-10 opacity-0'}`}>
          <div className="flex items-center gap-3 md:gap-5 group font-bold">
            <div className="relative">
              <div className="absolute inset-0 bg-blue-600 blur-xl opacity-10 group-hover:opacity-40 transition-opacity"></div>
              {/* 🏛️ INSTITUTIONAL LOGO INTEGRATION */}
              <div className="relative w-8 h-8 md:w-10 md:h-10 bg-white border border-slate-200 rounded-lg md:rounded-xl flex items-center justify-center shadow-lg group-hover:scale-110 transition-transform duration-500">
                <img src="/images/compagny-logo.png" alt="Company Logo" className="w-5 h-5 md:w-6 md:h-6 object-contain" />
              </div>
            </div>
            <div className="text-left font-bold">
              <h1 className="text-sm md:text-lg font-black tracking-tight text-slate-900">Data <span className="text-blue-600">connect</span></h1>
              <p className="text-[7px] md:text-[8px] uppercase font-black text-slate-500 tracking-[0.3em] mt-0.5">Internal Solution</p>
            </div>
          </div>

          <div className="flex items-center gap-2 md:gap-10 font-bold">
            <div className="hidden lg:flex items-center gap-8 font-bold">
              {['Infrastructures', 'Compliance', 'Performance'].map((item) => (
                <a key={item} href="#" className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-600 hover:text-blue-600 transition-all relative group">
                  {item}
                  <span className="absolute -bottom-2 left-0 w-0 h-1 bg-blue-600 rounded-full transition-all group-hover:w-full"></span>
                </a>
              ))}
            </div>
            <div className="hidden sm:block w-px h-4 bg-slate-200 mx-2"></div>
            <button onClick={() => void handleLogin()} className="flex items-center gap-2 px-4 md:px-6 py-2 md:py-2.5 bg-slate-900 text-white text-[9px] md:text-[10px] font-black uppercase tracking-[0.2em] rounded-lg md:rounded-xl hover:bg-blue-600 transition-all shadow-lg">
              <Lock size={12} className="fill-current text-white" />
              <span>Sign in</span>
            </button>
          </div>
        </nav>
      </div>

      <main className="relative pt-32 md:pt-48 pb-24 px-6 md:px-8 max-w-7xl mx-auto flex flex-col items-center text-center z-10 pointer-events-none text-slate-900 font-bold">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full h-full max-w-4xl max-h-[500px] bg-white/40 blur-[100px] rounded-full pointer-events-none -z-10 opacity-80" />
        <div className="pointer-events-auto flex flex-col items-center">
          <div className={`mb-8 md:mb-10 transition-all duration-1000 delay-300 transform ${mounted ? 'scale-100 opacity-100' : 'scale-50 opacity-0'}`}>
            <div className="inline-flex items-center gap-3 px-4 py-2 md:px-5 md:py-2.5 bg-white border border-slate-200 rounded-full shadow-sm">
              <span className="w-2 md:w-2.5 h-2 md:h-2.5 bg-emerald-500 rounded-full animate-pulse shadow-[0_0_10px_#10b981]"></span>
              <p className="text-[8px] md:text-[10px] font-black uppercase tracking-[0.3em] text-slate-600">Cloud network : <span className="text-emerald-600">100% Operational</span></p>
            </div>
          </div>
          <div className={`relative space-y-4 md:space-y-6 max-w-5xl transition-all duration-1000 delay-500 transform ${mounted ? 'translate-y-0 opacity-100' : 'translate-y-12 opacity-0'}`}>
            <h2 className="text-4xl md:text-6xl lg:text-[84px] font-[1000] tracking-tighter leading-[1.1] md:leading-[0.9] uppercase text-slate-900">
              UNIFIED CONTROL OF <br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#0055A4] via-[#0055A4] to-[#EF4135]">
                DATA ECOSYSTEMS
              </span>
            </h2>
            <p className="text-sm md:text-lg lg:text-xl text-slate-600 font-[900] max-w-3xl mx-auto leading-relaxed mt-4 md:mt-8">
              Institutional multi-cloud supervision portal for the group hybrid infrastructures. 
              Ensure the integrity and <span className="text-[#EF4135]">performance</span> of your Azure and AWS services.
            </p>
          </div>
          <div className={`mt-10 flex flex-col items-center gap-4 md:mt-14 transition-all duration-1000 delay-700 transform ${mounted ? 'translate-y-0 opacity-100' : 'translate-y-12 opacity-0'}`}>
            <div className="flex flex-col gap-4 sm:flex-row md:gap-6">
              <button onClick={() => void handleLogin()} className="group relative px-8 md:px-12 py-4 md:py-6 bg-[#0055A4] text-white rounded-xl md:rounded-2xl font-black uppercase tracking-[0.2em] text-[10px] md:text-xs hover:scale-105 transition-all shadow-2xl shadow-blue-900/20 ring-4 ring-blue-200/70 flex items-center justify-center gap-4">
                Sign in to cockpit
                <ArrowRight className="w-4 h-4 group-hover:translate-x-2 transition-transform" />
              </button>
              <button className="px-8 md:px-12 py-4 md:py-6 bg-white/90 border border-slate-300 rounded-xl md:rounded-2xl font-black uppercase tracking-[0.2em] text-[10px] md:text-xs hover:bg-slate-50 transition-all text-slate-700 shadow-sm">
                View documentation
              </button>
            </div>
            <p className="max-w-xl text-xs font-bold uppercase tracking-[0.18em] text-slate-500">
              Microsoft SSO opens the secured monitoring cockpit. First sign-in creates your DCM account — an admin approves your access. New landing zone? Use the guide at the bottom right.
            </p>
          </div>
        </div>

        <div className={`grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-10 mt-24 md:mt-40 w-full transition-all duration-1000 delay-900 transform ${mounted ? 'translate-y-0 opacity-100' : 'translate-y-24 opacity-0'} pointer-events-auto`}>
          <FeatureCard title="Hybrid operations" description="Centralized control of Landing Zones and orchestrators. Azure ADF and AWS Glue supervision." icon={<Globe />} tone="blue" badge="Ops" meta="Azure + AWS" actionLabel="Discover" />
          <FeatureCard title="Integrity & Security" description="Automated governance and compliance with group cyber security standards." icon={<Fingerprint />} tone="purple" badge="Security" meta="Checks" actionLabel="Secure" />
          <FeatureCard title="Performance & FinOps" description="Cloud cost control and compute resource optimization (Databricks, EMR)." icon={<BarChart3 />} tone="red" badge="FinOps" meta="Optimization" actionLabel="Optimize" />
        </div>
      </main>

      <footer className="mt-40 md:mt-60 border-t-4 border-slate-200 bg-[#f8fafc] px-6 md:px-8 py-12 relative overflow-hidden pointer-events-auto text-slate-900">
        <div className="max-w-7xl mx-auto grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-10 text-left font-bold">
          <div className="col-span-1 sm:col-span-2 space-y-6 md:space-y-8 text-left font-bold">
            <div className="flex items-center gap-4 text-left font-bold">
              {/* 🏛️ FOOTER LOGO INTEGRATION */}
              <div className="w-10 h-10 md:w-12 md:h-12 bg-white border border-slate-200 rounded-xl flex items-center justify-center shadow-lg">
                <img src="/images/compagny-logo.png" alt="Company Logo" className="w-6 h-6 md:w-7 md:h-7 object-contain" />
              </div>
              <span className="text-xl md:text-2xl font-black tracking-tighter text-slate-900 italic">Data <span className="text-[#0055A4]">connect</span></span>
            </div>
            <p className="text-slate-600 max-w-sm text-sm font-black leading-relaxed">Strategic group infra-data monitoring solution.</p>
          </div>
          <div>
            <h4 className="text-[9px] font-black uppercase tracking-[0.3em] text-slate-900 mb-6">Network</h4>
            <ul className="space-y-4 text-xs font-black text-slate-500 uppercase tracking-widest">
              <li><a href="#" className="hover:text-blue-600 font-bold">Portail CCoE</a></li>
              <li><a href="#" className="hover:text-blue-600 font-bold">Technical support</a></li>
            </ul>
          </div>
          <div>
            <h4 className="text-[9px] font-black uppercase tracking-[0.3em] text-slate-900 mb-6">Governance</h4>
            <ul className="space-y-4 text-xs font-black text-slate-500 uppercase tracking-widest">
              <li><a href="#" className="hover:text-blue-600 font-bold">Security</a></li>
              <li><a href="#" className="hover:text-blue-600 font-bold">Legal Hub</a></li>
            </ul>
          </div>
        </div>
        
        <div className="max-w-7xl mx-auto mt-12 pt-8 border-t border-slate-300 flex flex-col md:flex-row justify-between items-center gap-6 font-bold">
          <p className="text-[9px] font-black text-slate-700 uppercase tracking-[0.4em] text-center">© 2026 Data connect — Exclusive property of the group</p>
          <div className="px-4 py-1.5 rounded-full bg-slate-900 text-[9px] font-black text-white uppercase tracking-widest shadow-lg">Version 2.4.0-Stable</div>
        </div>
      </footer>

      <LandingAccessGuide />

      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes gradient-x { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
        .animate-gradient-x { background-size: 200% 200%; animation: gradient-x 6s ease-in-out infinite; }
        @keyframes mesh-1 { 0%, 100% { transform: translate(0, 0) scale(1); } 33% { transform: translate(10%, 10%) scale(1.1); } 66% { transform: translate(-5%, 15%) scale(0.9); } }
        .animate-mesh-1 { animation: mesh-1 15s ease-in-out infinite; }
        @keyframes mesh-2 { 0%, 100% { transform: translate(0, 0) scale(1.1); } 33% { transform: translate(-15%, -10%) scale(0.9); } 66% { transform: translate(10%, -5%) scale(1.1); } }
        .animate-mesh-2 { animation: mesh-2 18s ease-in-out infinite; }
        @keyframes spin-slow { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .animate-spin-slow { animation: spin-slow 12s linear infinite; }
        @keyframes engine-breath-vibrant { 0%, 100% { transform: scale(1); opacity: 0.1; } 50% { transform: scale(1.15); opacity: 0.35; } }
        
        .node-group { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
        .node-glow-vibrant { opacity: 0.08; transition: opacity 0.5s ease, r 0.5s ease; filter: blur(12px); }
        .node-core { transition: r 0.3s ease, stroke-width 0.3s ease, fill 0.3s ease; }
        .node-icon { transition: transform 0.3s ease; transform-origin: center; }
        .node-label { opacity: 0.7; transition: opacity 0.3s ease, fill 0.3s ease; }

        .node-group:hover .node-glow-vibrant { opacity: 0.5; r: 40; }
        .node-group:hover .node-core { r: 18; stroke-width: 4px; fill: #f8fafc; }
        .node-group:hover .node-icon { transform: scale(1.15); }
        .node-group:hover .node-label { opacity: 1; fill: #0055A4; font-weight: 900; }

        .engine-node .node-core { stroke-dasharray: 5,2; animation: spin-slow 5s linear infinite; }
        .engine-node .node-glow-vibrant { animation: engine-breath-vibrant 3s ease-in-out infinite; opacity: 0.2; }
      ` }} />
    </div>
  );
};

export default LandingPage;
