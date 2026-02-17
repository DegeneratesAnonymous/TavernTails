import React from 'react'

type Msg = {
  id: number | string
  who: 'gm' | 'you' | 'system' | 'ally'
  text: string
  mentions?: string[]
}

type Props = {
  loading: boolean
  messages: Msg[]
}

const MessageList = React.forwardRef<HTMLDivElement, Props>(function MessageList({ loading, messages }, ref) {
  return (
    <div className="chat-messages" ref={ref}>
      {loading ? <div className="chat-loading">Loading chat…</div> : null}
      {messages.map((m) => (
        <div key={m.id} className={`chat-message ${m.who === 'system' ? 'chat-message-system' : ''}`}>
          <div className="chat-message-who">{m.who.toUpperCase()}</div>
          <div className={`chat-message-bubble ${m.who === 'you' ? 'chat-message-you' : ''}`}>{m.text}</div>
          {!!m.mentions?.length ? <div className="chat-message-mentions">Mentions: {m.mentions.join(', ')}</div> : null}
        </div>
      ))}
    </div>
  )
})

export default MessageList
