import { useEffect, useState } from 'react';
import './App.css';
import './index.css';
import { fetchAppHealth, fetchCanStatus, fetchLights, fetchDeviceMapping, fetchRvcSpec } from './api';

const VIEWS = [
  'dashboard',
  'lights',
  'mapping',
  'spec',
  'unmapped',
  'unknownPgns',
  'canSniffer',
  'networkMap',
];

type View = typeof VIEWS[number];

function App() {
  const [view, setView] = useState<View>('dashboard');
  // Dashboard data state
  const [appHealth, setAppHealth] = useState<any>(null);
  const [canStatus, setCanStatus] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Lights view state
  const [lights, setLights] = useState<any[]>([]);
  const [lightsLoading, setLightsLoading] = useState(false);
  const [lightsError, setLightsError] = useState<string | null>(null);

  // Mapping view state
  const [mapping, setMapping] = useState<any>(null);
  const [mappingLoading, setMappingLoading] = useState(false);
  const [mappingError, setMappingError] = useState<string | null>(null);

  // Spec view state
  const [spec, setSpec] = useState<any>(null);
  const [specLoading, setSpecLoading] = useState(false);
  const [specError, setSpecError] = useState<string | null>(null);

  // Unmapped view state
  const [unmapped, setUnmapped] = useState<any[]>([]);
  const [unmappedLoading, setUnmappedLoading] = useState(false);
  const [unmappedError, setUnmappedError] = useState<string | null>(null);

  // Unknown PGNs view state
  const [unknownPgns, setUnknownPgns] = useState<any[]>([]);
  const [unknownPgnsLoading, setUnknownPgnsLoading] = useState(false);
  const [unknownPgnsError, setUnknownPgnsError] = useState<string | null>(null);

  // CAN Sniffer view state
  const [sniffer, setSniffer] = useState<any[]>([]);
  const [snifferLoading, setSnifferLoading] = useState(false);
  const [snifferError, setSnifferError] = useState<string | null>(null);

  useEffect(() => {
    if (view === 'dashboard') {
      setLoading(true);
      setError(null);
      Promise.all([fetchAppHealth(), fetchCanStatus()])
        .then(([health, can]) => {
          setAppHealth(health);
          setCanStatus(can);
        })
        .catch((e) => setError(e.message))
        .finally(() => setLoading(false));
    }
    if (view === 'lights') {
      setLightsLoading(true);
      setLightsError(null);
      fetchLights()
        .then((data) => setLights(data))
        .catch((e) => setLightsError(e.message))
        .finally(() => setLightsLoading(false));
    }
    if (view === 'mapping') {
      setMappingLoading(true);
      setMappingError(null);
      fetchDeviceMapping()
        .then((data) => setMapping(data))
        .catch((e) => setMappingError(e.message))
        .finally(() => setMappingLoading(false));
    }
    if (view === 'spec') {
      setSpecLoading(true);
      setSpecError(null);
      fetchRvcSpec()
        .then((data) => setSpec(data))
        .catch((e) => setSpecError(e.message))
        .finally(() => setSpecLoading(false));
    }
    if (view === 'unmapped') {
      setUnmappedLoading(true);
      setUnmappedError(null);
      fetch('/api/can/unmapped')
        .then((res) => {
          if (!res.ok) throw new Error('Failed to fetch unmapped entries');
          return res.json();
        })
        .then((data) => setUnmapped(data))
        .catch((e) => setUnmappedError(e.message))
        .finally(() => setUnmappedLoading(false));
    }
    if (view === 'unknownPgns') {
      setUnknownPgnsLoading(true);
      setUnknownPgnsError(null);
      fetch('/api/can/unknown-pgns')
        .then((res) => {
          if (!res.ok) throw new Error('Failed to fetch unknown PGNs');
          return res.json();
        })
        .then((data) => setUnknownPgns(data))
        .catch((e) => setUnknownPgnsError(e.message))
        .finally(() => setUnknownPgnsLoading(false));
    }
    if (view === 'canSniffer') {
      setSnifferLoading(true);
      setSnifferError(null);
      fetch('/api/can/sniffer')
        .then((res) => {
          if (!res.ok) throw new Error('Failed to fetch CAN sniffer data');
          return res.json();
        })
        .then((data) => setSniffer(data))
        .catch((e) => setSnifferError(e.message))
        .finally(() => setSnifferLoading(false));
    }
  }, [view]);

  return (
    <div className="min-h-screen flex flex-col bg-gray-900 text-white">
      {/* Header */}
      <header className="bg-gray-800 shadow p-4 text-xl font-semibold flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center">
          <span>rvc2api Dashboard</span>
          <span className="text-xs text-gray-400 ml-2">React</span>
        </div>
        <div>
          {/* Theme dropdown placeholder */}
          <span className="text-sm text-gray-400">Theme</span>
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden min-h-0">
        {/* Sidebar */}
        <aside className="hidden md:flex flex-col w-64 bg-gray-800 border-r border-gray-700 p-4 space-y-2">
          <span className="text-lg font-semibold mb-4">Navigation</span>
          <nav className="flex flex-col gap-2">
            <button className={`nav-link text-left px-3 py-2 rounded-md text-sm font-medium ${view==='dashboard' ? 'bg-gray-700 text-white' : 'text-gray-300 hover:text-white hover:bg-gray-700'}`} onClick={() => setView('dashboard')}>Dashboard</button>
            <button className={`nav-link text-left px-3 py-2 rounded-md text-sm font-medium ${view==='lights' ? 'bg-gray-700 text-white' : 'text-gray-300 hover:text-white hover:bg-gray-700'}`} onClick={() => setView('lights')}>Lights</button>
            <button className={`nav-link text-left px-3 py-2 rounded-md text-sm font-medium ${view==='mapping' ? 'bg-gray-700 text-white' : 'text-gray-300 hover:text-white hover:bg-gray-700'}`} onClick={() => setView('mapping')}>Device Mapping</button>
            <button className={`nav-link text-left px-3 py-2 rounded-md text-sm font-medium ${view==='spec' ? 'bg-gray-700 text-white' : 'text-gray-300 hover:text-white hover:bg-gray-700'}`} onClick={() => setView('spec')}>RVC Spec</button>
            <button className={`nav-link text-left px-3 py-2 rounded-md text-sm font-medium ${view==='unmapped' ? 'bg-gray-700 text-white' : 'text-gray-300 hover:text-white hover:bg-gray-700'}`} onClick={() => setView('unmapped')}>Unmapped Entries</button>
            <button className={`nav-link text-left px-3 py-2 rounded-md text-sm font-medium ${view==='unknownPgns' ? 'bg-gray-700 text-white' : 'text-gray-300 hover:text-white hover:bg-gray-700'}`} onClick={() => setView('unknownPgns')}>Unknown PGNs</button>
            <button className={`nav-link text-left px-3 py-2 rounded-md text-sm font-medium ${view==='canSniffer' ? 'bg-gray-700 text-white' : 'text-gray-300 hover:text-white hover:bg-gray-700'}`} onClick={() => setView('canSniffer')}>CAN Sniffer</button>
            <button className={`nav-link text-left px-3 py-2 rounded-md text-sm font-medium ${view==='networkMap' ? 'bg-gray-700 text-white' : 'text-gray-300 hover:text-white hover:bg-gray-700'}`} onClick={() => setView('networkMap')}>Network Map</button>
          </nav>
        </aside>
        {/* Main Content */}
        <main className="flex-1 min-w-0 overflow-y-auto p-6">
          {view === 'dashboard' && (
            <section>
              <h1 className="text-3xl font-bold mb-8">Dashboard</h1>
              <div className="mb-10">
                <h2 className="text-2xl font-semibold mb-4">Quick Light Controls</h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-x-6 gap-y-4">
                  <button className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-4 rounded-lg shadow hover:shadow-md transition-transform transform hover:scale-105">All Lights On</button>
                  <button className="w-full bg-gray-700 hover:bg-gray-600 text-white font-semibold py-3 px-4 rounded-lg shadow hover:shadow-md transition-transform transform hover:scale-105">All Lights Off</button>
                  <button className="w-full bg-yellow-500 hover:bg-yellow-600 text-black font-semibold py-3 px-4 rounded-lg shadow hover:shadow-md transition-transform transform hover:scale-105">Exterior On</button>
                  <button className="w-full bg-gray-700 hover:bg-gray-600 text-white font-semibold py-3 px-4 rounded-lg shadow hover:shadow-md transition-transform transform hover:scale-105">Exterior Off</button>
                  <button className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-3 px-4 rounded-lg shadow hover:shadow-md transition-transform transform hover:scale-105">Interior On</button>
                  <button className="w-full bg-gray-700 hover:bg-gray-600 text-white font-semibold py-3 px-4 rounded-lg shadow hover:shadow-md transition-transform transform hover:scale-105">Interior Off</button>
                </div>
              </div>
              <div>
                <h2 className="text-2xl font-semibold mb-4">Scenes</h2>
                <div className="bg-gray-800 p-6 rounded-lg shadow">
                  <p className="text-gray-400 mb-4">Scene management and definition coming soon.</p>
                  <button className="bg-blue-500 text-white font-semibold py-2 px-4 rounded-lg shadow hover:bg-blue-600">Create New Scene</button>
                </div>
              </div>
              <div className="mt-10">
                <h2 className="text-2xl font-semibold mb-6">System Status</h2>
                {loading && <p className="text-gray-400">Loading...</p>}
                {error && <p className="text-red-400">{error}</p>}
                <div className="mb-6">
                  <h3 className="text-xl font-semibold mb-3">Application Health</h3>
                  <div className="bg-gray-800 p-6 rounded-lg shadow">
                    {appHealth ? (
                      <pre className="text-green-300 text-sm whitespace-pre-wrap">{JSON.stringify(appHealth, null, 2)}</pre>
                    ) : (
                      <p className="text-gray-400">Loading application health...</p>
                    )}
                  </div>
                </div>
                <div>
                  <h3 className="text-xl font-semibold mb-3">CAN Bus Interfaces</h3>
                  <div className="bg-gray-800 p-6 rounded-lg shadow">
                    {canStatus ? (
                      <pre className="text-blue-300 text-sm whitespace-pre-wrap">{JSON.stringify(canStatus, null, 2)}</pre>
                    ) : (
                      <p className="text-gray-400">Loading CAN status...</p>
                    )}
                  </div>
                </div>
              </div>
            </section>
          )}
          {view === 'lights' && (
            <section>
              <h1 className="text-3xl font-bold mb-6">RV-C Lights</h1>
              {lightsLoading && <p>Loading lights...</p>}
              {lightsError && <p className="text-red-400">{lightsError}</p>}
              {!lightsLoading && !lightsError && (
                <div className="space-y-4">
                  {lights.length === 0 ? (
                    <p className="text-gray-400">No lights found.</p>
                  ) : (
                    <ul className="divide-y divide-gray-700">
                      {lights.map((light) => (
                        <li key={light.id} className="py-3 flex items-center justify-between">
                          <span className="font-medium">{light.name || light.id}</span>
                          <span className="ml-4">{light.state ? 'On' : 'Off'}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </section>
          )}
          {view === 'mapping' && (
            <section>
              <h1 className="text-3xl font-bold mb-6">Current Device Mapping</h1>
              {mappingLoading && <p>Loading device mapping...</p>}
              {mappingError && <p className="text-red-400">{mappingError}</p>}
              {mapping && (
                <pre className="bg-gray-800 text-green-300 p-4 rounded overflow-auto max-h-[70vh] font-mono text-sm whitespace-pre-wrap">{JSON.stringify(mapping, null, 2)}</pre>
              )}
            </section>
          )}
          {view === 'spec' && (
            <section>
              <h1 className="text-3xl font-bold mb-2">Current RVC Spec</h1>
              {specLoading && <p>Loading RVC spec...</p>}
              {specError && <p className="text-red-400">{specError}</p>}
              {spec && (
                <pre className="bg-gray-800 text-blue-300 p-4 rounded overflow-auto max-h-[70vh] font-mono text-sm whitespace-pre-wrap">{JSON.stringify(spec, null, 2)}</pre>
              )}
            </section>
          )}
          {view === 'unmapped' && (
            <section>
              <h1 className="text-3xl font-bold mb-6">Unmapped CAN Bus Entries</h1>
              <p className="mb-4 text-gray-400">These are CAN messages received by the system that could not be mapped to a known device based on your <code>Device Mapping</code>. Use this information to help build out your configuration.</p>
              {unmappedLoading && <p>Loading unmapped entries...</p>}
              {unmappedError && <p className="text-red-400">{unmappedError}</p>}
              {!unmappedLoading && !unmappedError && (
                <div className="space-y-4">
                  {unmapped.length === 0 ? (
                    <p className="text-gray-400">No unmapped entries found.</p>
                  ) : (
                    <ul className="divide-y divide-gray-700">
                      {unmapped.map((entry, idx) => (
                        <li key={idx} className="py-3 flex flex-col">
                          <span className="font-mono text-xs">{JSON.stringify(entry)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </section>
          )}
          {view === 'unknownPgns' && (
            <section>
              <h1 className="text-3xl font-bold mb-6">Unknown PGNs</h1>
              <p className="mb-4">These are PGNs (Parameter Group Numbers) observed on the CAN bus that are not defined in the loaded RVC specification (<code>RVC Spec</code>). This might indicate a newer or custom device.</p>
              {unknownPgnsLoading && <p>Loading unknown PGNs...</p>}
              {unknownPgnsError && <p className="text-red-400">{unknownPgnsError}</p>}
              {!unknownPgnsLoading && !unknownPgnsError && (
                <div className="space-y-4">
                  {unknownPgns.length === 0 ? (
                    <p className="text-gray-400">No unknown PGNs found.</p>
                  ) : (
                    <ul className="divide-y divide-gray-700">
                      {unknownPgns.map((pgn, idx) => (
                        <li key={idx} className="py-3 flex flex-col">
                          <span className="font-mono text-xs">{JSON.stringify(pgn)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </section>
          )}
          {view === 'canSniffer' && (
            <section>
              <h1 className="text-3xl font-bold mb-6">CAN Command/Control Sniffer</h1>
              <p className="mb-4 text-gray-400">This view shows command and control messages observed on the CAN bus, including both outgoing (TX) and incoming (RX) messages. Use this to help build out <code>device_mapping.yml</code>.</p>
              {snifferLoading && <p>Loading CAN sniffer data...</p>}
              {snifferError && <p className="text-red-400">{snifferError}</p>}
              {!snifferLoading && !snifferError && (
                <div className="overflow-x-auto">
                  {sniffer.length === 0 ? (
                    <p className="text-gray-400">No CAN sniffer data found.</p>
                  ) : (
                    <table className="min-w-full text-xs text-left">
                      <thead>
                        <tr className="bg-gray-700">
                          <th className="px-2 py-1">Time</th>
                          <th className="px-2 py-1">Dir</th>
                          <th className="px-2 py-1">PGN</th>
                          <th className="px-2 py-1">DGN</th>
                          <th className="px-2 py-1">Name</th>
                          <th className="px-2 py-1">Arb ID</th>
                          <th className="px-2 py-1">Data</th>
                          <th className="px-2 py-1">Decoded</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sniffer.map((row, idx) => (
                          <tr key={idx} className="border-b border-gray-700">
                            <td className="px-2 py-1 font-mono">{row.time}</td>
                            <td className="px-2 py-1">{row.dir}</td>
                            <td className="px-2 py-1">{row.pgn}</td>
                            <td className="px-2 py-1">{row.dgn}</td>
                            <td className="px-2 py-1">{row.name}</td>
                            <td className="px-2 py-1">{row.arb_id}</td>
                            <td className="px-2 py-1 font-mono">{row.data}</td>
                            <td className="px-2 py-1 font-mono">{row.decoded}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </section>
          )}
          {view === 'networkMap' && (
            <section>
              <h1 className="text-3xl font-bold mb-6">CAN Network Map</h1>
              <p>Network map view coming soon.</p>
            </section>
          )}
        </main>
      </div>
      {/* Footer */}
      <footer className="bg-gray-800 text-gray-400 text-xs p-3 flex justify-between items-center">
        <span>rvc2api React UI</span>
        <span>API server: <span className="text-green-400">/api</span></span>
      </footer>
    </div>
  );
}

export default App;
