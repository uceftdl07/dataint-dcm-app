import { 
  CheckCircle, 
  Cpu, 
  Database, 
  Factory, 
  Network, 
  Shield 
} from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '../components/ui/card';

interface ModuleProgress {
  id: string;
  name: string;
  icon: React.ElementType;
  services: string[];
  status: 'pending' | 'loading' | 'completed';
}

const initialModules: ModuleProgress[] = [
  {
    id: 'compute',
    name: 'Neural Compute',
    icon: Cpu,
    status: 'pending',
    services: ['Databricks Clusters', 'EMR Fargate Instances']
  },
  {
    id: 'pipelines',
    name: 'Data Orbis',
    icon: Factory,
    status: 'pending',
    services: ['ADF Runtimes', 'Glue ETL Workers']
  },
  {
    id: 'storage',
    name: 'Lakebase Sync',
    icon: Database,
    status: 'pending',
    services: ['PostgreSQL Serveur', 'S3/Blob Handlers']
  },
  {
    id: 'security',
    name: 'Cyber Sentinel',
    icon: Shield,
    status: 'pending',
    services: ['Entra ID Auth', 'VPC Lattice mTLS']
  }
];

const ENABLE_AUTH = import.meta.env.VITE_ENABLE_AUTH === 'true';

const LoadingPage: React.FC = () => {
  const navigate = useNavigate();
  const [modules, setModules] = useState<ModuleProgress[]>(initialModules);
  const [progress, setProgress] = useState(0);
  const [logs, setLogs] = useState<string[]>(['Initializing DCM core...']);
  const [isComplete, setIsComplete] = useState(false);

  const addLog = (msg: string) => {
    setLogs(prev => [msg, ...prev].slice(0, 5));
  };

  useEffect(() => {
    const runLoading = async () => {
      // Handle MSAL redirect callback first if auth is enabled
      if (ENABLE_AUTH) {
        try {
          console.log('🔐 [LOADING] Handling authentication callback...');
          addLog('Checking authentication...');
          
          const [{ PublicClientApplication }] = await Promise.all([
            import('@azure/msal-browser'),
          ]);

          const { msalConfig } = await import('../config/authConfig');
          const pca = new PublicClientApplication(msalConfig);
          await pca.initialize();

          // Handle the redirect response
          const response = await pca.handleRedirectPromise();
          
          if (response) {
            console.log('✅ [LOADING] Authentication successful:', response.account?.username);
            addLog(`Authenticated: ${response.account?.username}`);
          } else {
            // Check if already authenticated
            const accounts = pca.getAllAccounts();
            if (accounts.length > 0) {
              console.log('✅ [LOADING] Account already authenticated:', accounts[0].username);
              addLog(`Session active: ${accounts[0].username}`);
            } else {
              console.error('❌ [LOADING] No authentication found, returning to the home page');
              addLog('Error: authentication required');
              await new Promise(r => setTimeout(r, 2000));
              navigate('/');
              return;
            }
          }
        } catch (error) {
          console.error('❌ [LOADING] Authentication error:', error);
          addLog('Authentication error');
          await new Promise(r => setTimeout(r, 2000));
          navigate('/');
          return;
        }
      }

      // Continue with loading animation
      for (let i = 0; i < initialModules.length; i++) {
        const mod = initialModules[i];
        setModules(prev => prev.map((m, idx) => idx === i ? { ...m, status: 'loading' } : m));
        addLog(`Synchronisation ${mod.name}...`);
        
        for (const service of mod.services) {
          await new Promise(r => setTimeout(r, 600));
          addLog(`Connected to ${service}`);
          setProgress(prev => prev + (100 / (initialModules.length * 2)));
        }

        setModules(prev => prev.map((m, idx) => idx === i ? { ...m, status: 'completed' } : m));
        setProgress(((i + 1) / initialModules.length) * 100);
      }

      setIsComplete(true);
      addLog('System ready. Redirecting...');
      await new Promise(r => setTimeout(r, 1200));
      navigate('/dashboard');
    };

    runLoading();
  }, [navigate]);

  return (
    <div className="h-screen bg-[#020202] text-white flex flex-col items-center justify-center p-6 font-mono overflow-hidden relative">
      
      {/* 🌌 Cyber Background */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-blue-600/5 rounded-full blur-[120px]"></div>
      </div>

      {/* Main Content Container with refined spacing */}
      <div className="max-w-xl w-full flex flex-col items-center justify-between h-full max-h-[850px] py-8 relative z-10">
        
        {/* 💠 Central Core - Back to Majestic Size */}
        <div className="relative flex flex-col items-center">
          <div className="relative w-40 h-40">
            <div className="absolute inset-0 border-2 border-blue-500/20 rounded-full animate-spin-slow"></div>
            <div className="absolute inset-2 border border-indigo-500/40 rounded-full animate-reverse-spin"></div>
            
            <div className="absolute inset-0 flex items-center justify-center">
              <div className={`w-20 h-20 rounded-full bg-gradient-to-br from-blue-600 to-indigo-700 flex items-center justify-center shadow-[0_0_50px_rgba(37,99,235,0.5)] transition-all duration-1000 ${isComplete ? 'scale-125' : 'animate-pulse'}`}>
                <Network className="w-10 h-10 text-white" />
              </div>
            </div>

            {[0, 72, 144, 216, 288].map((deg, i) => (
              <div 
                key={i}
                className="absolute top-1/2 left-1/2 w-2 h-2 bg-blue-400 rounded-full blur-[1px] animate-orbit"
                style={{ '--deg': `${deg}deg` } as React.CSSProperties}
              ></div>
            ))}
          </div>

          <div className="mt-8 text-center space-y-2">
            <h1 className="text-2xl font-black tracking-[0.3em] uppercase italic">
              Data <span className="text-blue-400">connect</span>
            </h1>
            <div className="flex items-center justify-center gap-3">
              <div className="h-px w-12 bg-gradient-to-r from-transparent to-blue-500/50"></div>
              <span className="text-[10px] text-blue-400 font-bold uppercase tracking-widest animate-pulse">
                Phase {Math.min(modules.filter(m => m.status === 'completed').length + 1, 4)} / 4
              </span>
              <div className="h-px w-12 bg-gradient-to-l from-transparent to-blue-500/50"></div>
            </div>
          </div>
        </div>

        {/* 📊 Progress Visualizer - Balanced Spacing */}
        <Card className="w-full relative overflow-hidden my-4">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-blue-500 to-transparent opacity-50"></div>
          
          <CardContent className="space-y-6">
            <div className="space-y-4">
              {modules.map((m) => (
                <div key={m.id} className={`flex items-center gap-4 transition-all duration-500 ${m.status === 'pending' ? 'grayscale' : ''}`}>
                  <div className={`p-2 rounded-lg ${m.status === 'completed' ? 'bg-emerald-100 text-emerald-700' : m.status === 'loading' ? 'bg-blue-600 text-white shadow-[0_0_15px_rgba(37,99,235,0.5)]' : 'bg-white/5 text-slate-500'}`}>
                    {m.status === 'completed' ? <CheckCircle size={16} /> : <m.icon size={16} className={m.status === 'loading' ? 'animate-spin' : ''} />}
                  </div>
                  <div className="flex-1">
                    <div className="flex justify-between items-end">
                      <span className="text-[10px] font-black uppercase tracking-widest">{m.name}</span>
                      <span className="text-[9px] text-slate-500 font-bold">{m.status.toUpperCase()}</span>
                    </div>
                    <div className="h-1 w-full bg-white/5 rounded-full mt-2 overflow-hidden">
                      <div 
                        className={`h-full transition-all duration-1000 ${m.status === 'completed' ? 'bg-emerald-600' : 'bg-blue-600 animate-pulse'}`}
                        style={{ width: m.status === 'completed' ? '100%' : m.status === 'loading' ? '60%' : '0%' }}
                      ></div>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="pt-6 border-t border-white/10 space-y-2">
              {logs.map((log, i) => (
                <div key={i} className={`text-[9px] flex items-center gap-2 ${i === 0 ? 'text-blue-700 font-bold' : 'text-slate-600'}`}>
                  <span className="text-slate-600">[{new Date().toLocaleTimeString()}]</span>
                  <span className="font-bold">{i === 0 ? '> ' : '  '}{log}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Global Percentage Area - Guaranteed Visibility */}
        <div className="text-center mt-auto">
          <div className="text-5xl font-black italic tracking-tighter tabular-nums leading-none">
            {Math.round(progress)}<span className="text-blue-400 text-2xl ml-1">%</span>
          </div>
          <p className="text-[9px] text-slate-500 uppercase font-black tracking-[0.4em] mt-3">Data Integrity Check</p>
        </div>
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes spin-slow { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes reverse-spin { from { transform: rotate(360deg); } to { transform: rotate(0deg); } }
        @keyframes orbit {
          from { transform: translate(-50%, -50%) rotate(var(--deg)) translateY(-80px) rotate(calc(-1 * var(--deg))); }
          to { transform: translate(-50%, -50%) rotate(calc(var(--deg) + 360deg)) translateY(-80px) rotate(calc(-1 * (var(--deg) + 360deg))); }
        }
        .animate-spin-slow { animation: spin-slow 12s linear infinite; }
        .animate-reverse-spin { animation: reverse-spin 8s linear infinite; }
        .animate-orbit { animation: orbit 6s linear infinite; }
      ` }} />
    </div>
  );
};

export default LoadingPage;
