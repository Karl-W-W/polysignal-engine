'use client';
import { useEffect, useState } from 'react';
const API_BASE = 'https://api.polysignal.app'; 

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);

  useEffect(() => {
    const fetchStats = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/system/stats`);
            setStats(await res.json());
        } catch(e) { console.error(e); }
    };
    fetchStats();
    setInterval(fetchStats, 5000);
  }, []);

  return (
    <div style={{background: '#0a0e27', minHeight: '100vh', color: '#fff', padding: '2rem', fontFamily: 'monospace'}}>
      <h1 style={{color: '#00f0ff'}}>POLY SIGNAL // SYSTEM INTEGRITY</h1>
      <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginTop: '2rem'}}>
        <div style={{border: '1px solid #333', padding: '1rem'}}>
          <h3>MARKETS TRACKED</h3>
          <h1 style={{fontSize: '3rem', color: '#00f0ff'}}>{stats?.markets_tracked || 0}</h1>
        </div>
        <div style={{border: '1px solid #333', padding: '1rem'}}>
           <h3>STATUS</h3>
           <h1 style={{color: '#0f0'}}>ONLINE</h1>
        </div>
      </div>
      <div style={{marginTop: '2rem'}}>
        <h3>LIVE EVENT LOG</h3>
        <div style={{background: '#111', padding: '1rem', height: '300px', overflowY: 'scroll', border: '1px solid #333'}}>
            {stats?.recent_events?.map((e:any) => (
                <div key={e.id} style={{borderBottom: '1px solid #222', padding: '0.5rem'}}>
                    <span style={{color: '#666'}}>[{e.ts}]</span> <span style={{color: '#00f0ff'}}>{e.event_type}</span> {e.payload}
                </div>
            ))}
        </div>
      </div>
    </div>
  );
}
