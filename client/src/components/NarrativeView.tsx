import React, {useEffect, useState} from 'react'
import { buildApiUrl } from '../api'

type Scene = {
  id: string
  title: string
  image?: string
  text: string
  choices: Array<{id:string,label:string}>
}

type Props = { sessionId?: string | null }

export default function NarrativeView({sessionId}: Props){
  const [scene, setScene] = useState<Scene|null>(null)

  useEffect(()=>{
    let mounted = true
    const token = localStorage.getItem('access_token')
    const headers: any = { 'Content-Type': 'application/json' }
    if(token) headers['Authorization'] = `Bearer ${token}`
    const seedUrl = sessionId ? buildApiUrl(`/sessions/${sessionId}/file/story.json`) : buildApiUrl('/content/campaigns/seed')
    fetch(seedUrl, { headers })
      .then(r=>r.ok? r.json() : Promise.reject('no'))
      .then((data:Scene)=>{
        if(mounted){
          const normalized: Scene = {
            ...data,
            choices: Array.isArray(data?.choices) ? data.choices : []
          }
          setScene(normalized)
        }
      })
      .catch(()=>{
        setScene({
          id:'seed',
          title:'The Abandoned Mill',
          image:'',
          text:'The wind howls as you step into the mill. Broken gears and faded banners tell a story of a sudden evacuation...',
          choices:[{id:'search',label:'Search the sacks'},{id:'listen',label:'Listen at the door'}]
        })
      })
    return ()=>{ mounted=false }
  },[sessionId])

  async function choose(id:string){
    try{
      const token = localStorage.getItem('access_token')
      const headers: any = { 'Content-Type': 'application/json' }
      if(token) headers['Authorization'] = `Bearer ${token}`
      const res = await fetch(buildApiUrl('/content/advance'),{
          method:'POST',headers,
          body: JSON.stringify({sceneId: scene?.id, choiceId: id, sessionId})
        })
      const data = await res.json()
      window.dispatchEvent(new CustomEvent('narrative:advance',{detail:data}))
      if(data.nextScene) setScene(data.nextScene)
    }catch(e){
      console.error('choice failed',e)
    }
  }

  if(!scene) return <div style={{padding:12}}>Loading scene…</div>

  return (
    <div className="narrative-view" style={{padding:12,height:'100%',boxSizing:'border-box',display:'flex',flexDirection:'column'}}>
      <div className="scene-image-area" style={{position:'relative',height:'48%',background:'#111',borderRadius:8,display:'flex',alignItems:'center',justifyContent:'center',overflow:'hidden'}}>
        {scene.image ? (
          <img src={scene.image} alt="scene" style={{width:'100%',height:'100%',objectFit:'cover',borderRadius:8,filter:'brightness(0.85)'}}/>
        ) : (
          <div style={{color:'#888',width:'100%',height:'100%',display:'flex',alignItems:'center',justifyContent:'center'}}>Scene image</div>
        )}
        <div className="narration-overlay">
          <div className="narration-card">
            <h2 style={{margin:'0 0 12px 0',fontWeight:700}}>{scene.title}</h2>
            <p style={{margin:0}}>{scene.text}</p>
          </div>
        </div>
      </div>
      <div style={{marginTop:12,flex:1,overflow:'auto'}}>
        <div style={{marginTop:8}}>
          {(scene.choices && scene.choices.length ? scene.choices : []).map(c=> (
            <button key={c.id} className="narrative-choice-btn" onClick={()=>choose(c.id)}>{c.label}</button>
          ))}
          {(!scene.choices || scene.choices.length === 0) && (
            <div style={{fontSize:12,color:'#888'}}>No choices available yet.</div>
          )}
        </div>
      </div>
    </div>
  )
}
