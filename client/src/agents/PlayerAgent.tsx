// PlayerAgent: Handles player profiles and character sheet integration
import React, { useState } from 'react';

const PlayerAgent: React.FC = () => {
  const [name, setName] = useState('');
  const [character, setCharacter] = useState('');
  const [dndbeyondUrl, setDnDBeyondUrl] = useState('');
  const [result, setResult] = useState<any>(null);

  const handleProfileSubmit = async () => {
    const res = await fetch('/player/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, character: { details: character } })
    });
    setResult(await res.json());
  };

  const handleDnDBeyondImport = async () => {
    const res = await fetch('/player/dndbeyond', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: dndbeyondUrl })
    });
    setResult(await res.json());
  };

  return (
    <div>
      <h2>Player Agent</h2>
      <div>
        <label>Player Name:</label>
        <input value={name} onChange={e => setName(e.target.value)} />
      </div>
      <div>
        <label>Character Details:</label>
        <textarea value={character} onChange={e => setCharacter(e.target.value)} />
      </div>
      <button onClick={handleProfileSubmit}>Save Profile</button>
      <div>
        <label>DnDBeyond Character URL:</label>
        <input value={dndbeyondUrl} onChange={e => setDnDBeyondUrl(e.target.value)} />
        <button onClick={handleDnDBeyondImport}>Import DnDBeyond Character</button>
      </div>
      {result && (
        <pre>{JSON.stringify(result, null, 2)}</pre>
      )}
    </div>
  );
};

export default PlayerAgent;
