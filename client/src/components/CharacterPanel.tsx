import React, {useRef, useState} from 'react'

type SectionKey = 'inventory' | 'spells' | 'skills'

export default function CharacterPanel(){
  const [expanded, setExpanded] = useState<SectionKey|null>(null)
  const containerRef = useRef<HTMLDivElement|null>(null)

  function toggle(key:SectionKey){
    setExpanded(prev => prev===key? null : key)
    // after open, ensure the panel scrolls so the expanded section is visible
    setTimeout(()=>{
      const el = document.getElementById('section-'+key)
      if(el) el.scrollIntoView({behavior:'smooth',block:'nearest'})
      if(containerRef.current) containerRef.current.scrollTop = containerRef.current.scrollHeight
    },120)
  }

  return (
    <div className="character-panel" style={{height:'100%',display:'flex',flexDirection:'column'}}>
      <h3 style={{marginTop:0}}>Characters</h3>
      <div style={{flex:1,overflowY:'auto'}} ref={containerRef}>
        <div style={{padding:8,borderRadius:6,background:'#0f0f0f',marginBottom:8}}>
          <strong>Aria the Ranger</strong>
          <div>HP: 12/12 • Level 2</div>
        </div>

        <div style={{padding:8,borderRadius:6,background:'#0f0f0f',marginBottom:8}}>
          <strong>Torin the Fighter</strong>
          <div>HP: 18/18 • Level 3</div>
        </div>

        <div style={{marginTop:6}}>
          <div id="section-inventory" style={{marginBottom:6}}>
            <button style={{width:'100%'}} onClick={()=>toggle('inventory')}>Inventory</button>
            {expanded==='inventory' && (
              <div style={{marginTop:8,padding:8,background:'#0b0b0b',borderRadius:6}}>
                <ul style={{margin:0,paddingLeft:16}}>
                  <li>Rope</li>
                  <li>Lantern</li>
                  <li>Rations</li>
                </ul>
              </div>
            )}
          </div>

          <div id="section-spells" style={{marginBottom:6}}>
            <button style={{width:'100%'}} onClick={()=>toggle('spells')}>Spells</button>
            {expanded==='spells' && (
              <div style={{marginTop:8,padding:8,background:'#0b0b0b',borderRadius:6}}>
                <ul style={{margin:0,paddingLeft:16}}>
                  <li>Magic Missile</li>
                  <li>Heal</li>
                </ul>
              </div>
            )}
          </div>

          <div id="section-skills" style={{marginBottom:6}}>
            <button style={{width:'100%'}} onClick={()=>toggle('skills')}>Skills</button>
            {expanded==='skills' && (
              <div style={{marginTop:8,padding:8,background:'#0b0b0b',borderRadius:6}}>
                <ul style={{margin:0,paddingLeft:16}}>
                  <li>Perception +4</li>
                  <li>Stealth +3</li>
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
      <div style={{marginTop:8}}>
        <button style={{width:'100%'}}>Add Character</button>
      </div>
    </div>
  )
}
