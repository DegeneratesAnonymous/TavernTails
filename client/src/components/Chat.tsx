import React, {useRef, useState, useEffect} from 'react'

type Msg = {id:number, who:'gm'|'you'|'system', text:string, time?:string}

export default function Chat(){
  const [messages, setMessages] = useState<Msg[]>(()=>[
    {id:1, who:'system', text:'Session started.'},
    {id:2, who:'gm', text:'Welcome, adventurer.'},
  ])
  const [value, setValue] = useState('')
  const listRef = useRef<HTMLDivElement|null>(null)

  useEffect(()=>{ // auto-scroll to bottom when messages change
    if(listRef.current){
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  },[messages])

  useEffect(()=>{
    function onAdvance(e: CustomEvent){
      const detail = e.detail
      if(!detail) return
      const text = detail.narration || detail.text || JSON.stringify(detail)
      setMessages(m=>[...m,{id:Date.now(),who:'gm',text}])
    }
    // @ts-ignore
    window.addEventListener('narrative:advance', onAdvance as EventListener)
    return ()=>{
      // @ts-ignore
      window.removeEventListener('narrative:advance', onAdvance as EventListener)
    }
  },[])

  function send(){
    if(!value.trim()) return
    const id = Date.now()
    setMessages(m=>[...m,{id,who:'you',text:value}])
    setValue('')
    // mock GM reply after a short delay
    setTimeout(()=>{
      setMessages(m=>[...m,{id:Date.now()+1,who:'gm',text:'(GM) The world reacts to your choice.'}])
    },600)
  }

  return (
    <div className="chat-root" style={{height:'100%',display:'flex',flexDirection:'column'}}>
      <div ref={listRef} style={{flex:1,overflowY:'auto',padding:8,background:'#0b0b0b',borderRadius:6}}>
        {messages.map(m=> (
          <div key={m.id} style={{marginBottom:8,opacity:m.who==='system'?0.8:1}}>
            <div style={{fontSize:12,color:'#999'}}>{m.who.toUpperCase()}</div>
            <div style={{padding:6,background:m.who==='you'? '#122':'#111',borderRadius:6}}>{m.text}</div>
          </div>
        ))}
      </div>
      <form style={{display:'flex',marginTop:8}} onSubmit={(e)=>{e.preventDefault(); send()}}>
        <input value={value} onChange={e=>setValue(e.target.value)} style={{flex:1,padding:8,borderRadius:6,border:'1px solid rgba(255,255,255,0.06)'}} placeholder="Type a message, or roll (e.g. 1d20+3)" />
        <button style={{marginLeft:8}} type="submit">Send</button>
      </form>
    </div>
  )
}
