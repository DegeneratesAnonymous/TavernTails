import React, {useState} from 'react'

export default function SiteMenu(){
  const [collapsed, setCollapsed] = useState(false)
  const items = [
    {key:'map', label:'Map'},
    {key:'inventory', label:'Inventory'},
    {key:'journal', label:'Journal'},
    {key:'settings', label:'Settings'},
  ]

  return (
    <div className={"site-menu" + (collapsed? ' collapsed':'' )}>
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:12}}>
        {!collapsed && <div style={{fontWeight:700}}>Menu</div>}
        <button onClick={()=>setCollapsed(v=>!v)} aria-label="Toggle menu">{collapsed? '▶':'◀'}</button>
      </div>
      <ul style={{listStyle:'none',padding:0,margin:0}}>
        {items.map(i=> (
          <li key={i.key} style={{marginBottom:8}}>
            <button style={{display:'flex',alignItems:'center',gap:8}}>
              <span style={{width:28,height:28,background:'#222',borderRadius:6,display:'inline-block'}} />
              {!collapsed && <span>{i.label}</span>}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
