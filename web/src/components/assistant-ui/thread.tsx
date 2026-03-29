import { useState, useEffect, createContext, useContext } from 'react'
import {
  ThreadPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  useMessage,
  useThreadRuntime,
} from '@assistant-ui/react'
import { MarkdownTextPrimitive } from '@assistant-ui/react-markdown'
import { ArrowUp, ArrowDown, Cpu, MessageSquare } from 'lucide-react'
import { getRenderer } from '@/renderers/registry'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { CurrentActivity } from '@/hooks/useCrowRuntime'

// Context to pass currentActivity into the thread tree
const ActivityContext = createContext<CurrentActivity | null>(null)

// Context for background mode toggle
const BackgroundModeContext = createContext<{ enabled: boolean; toggle: () => void }>({
  enabled: false,
  toggle: () => {},
})

export function ActivityProvider({
  activity,
  backgroundMode,
  onToggleBackground,
  children,
}: {
  activity: CurrentActivity | null
  backgroundMode?: boolean
  onToggleBackground?: () => void
  children: React.ReactNode
}) {
  return (
    <ActivityContext.Provider value={activity}>
      <BackgroundModeContext.Provider value={{
        enabled: backgroundMode ?? false,
        toggle: onToggleBackground ?? (() => {}),
      }}>
        {children}
      </BackgroundModeContext.Provider>
    </ActivityContext.Provider>
  )
}

export function Thread() {
  return (
    <ThreadPrimitive.Root className="flex flex-col h-full relative">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto px-3 py-4 sm:px-6">
        <div className="max-w-3xl mx-auto flex flex-col gap-1">
          <ThreadPrimitive.Empty>
            <EmptyState />
          </ThreadPrimitive.Empty>
          <ThreadPrimitive.Messages
            components={{
              UserMessage,
              AssistantMessage,
            }}
          />
          <TypingIndicator />
        </div>
      </ThreadPrimitive.Viewport>

      <ThreadScrollToBottom />
      <Composer />
    </ThreadPrimitive.Root>
  )
}

function EmptyState() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-3 text-muted-foreground py-20">
      <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center">
        <MessageSquare className="h-6 w-6 text-primary/60" />
      </div>
      <p className="text-sm">what can I help you with?</p>
    </div>
  )
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="flex flex-col max-w-[85%] sm:max-w-[70%] self-end items-end">
      <div className="px-3 py-2 sm:px-4 sm:py-2.5 rounded-2xl rounded-br-sm text-sm leading-relaxed bg-primary text-primary-foreground">
        <MessagePrimitive.Content
          components={{ Text: ({ text }) => <>{text}</> }}
        />
      </div>
    </MessagePrimitive.Root>
  )
}

function AssistantMessage() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const richParts = useMessage(
    (m) => (m.metadata?.custom as Record<string, unknown> | undefined)?.richParts as Record<string, any>[] | undefined,
  )

  // Hide the empty placeholder bubble that assistant-ui creates while
  // isRunning is true — the TypingIndicator already covers this state.
  const isEmpty = useMessage((m) => {
    if (m.content.length === 0) return true
    return m.content.every(
      (p) => p.type === 'text' && ('text' in p ? (p.text as string).trim() === '' : true),
    )
  })
  if (isEmpty) return null

  return (
    <MessagePrimitive.Root className="flex flex-col max-w-[85%] sm:max-w-[70%] self-start items-start">
      <AgentLabel />
      <div className="px-3 py-2 sm:px-4 sm:py-2.5 rounded-2xl rounded-bl-sm text-sm leading-relaxed bg-card border border-border prose prose-sm prose-neutral dark:prose-invert max-w-none">
        <MessagePrimitive.Content
          components={{
            Text: AssistantMessageText,
            tools: { Fallback: ToolCallDisplay },
          }}
        />
        {richParts?.map((part, i) => {
          const Renderer = getRenderer(part.type as string)
          return Renderer ? <Renderer key={i} data={part} /> : null
        })}
      </div>
    </MessagePrimitive.Root>
  )
}

function AgentLabel() {
  const agentName = useMessage(
    (m) => (m.metadata?.custom as Record<string, unknown> | undefined)?.agentName as string | undefined,
  )
  if (!agentName) return null

  return (
    <div className="flex items-center gap-1 text-xs text-muted-foreground mb-0.5 pl-3">
      <Cpu className="h-3 w-3" />
      {agentName}
    </div>
  )
}

function AssistantMessageText() {
  return <MarkdownTextPrimitive />
}

function ToolCallDisplay({ toolName, args, result }: { toolName: string; args: Record<string, unknown>; result?: unknown }) {
  const isDone = result !== undefined
  return (
    <div className="my-2 rounded-xl border border-border bg-muted/20 overflow-hidden">
      <div className="px-3 py-2 flex items-center gap-2 text-xs">
        <span className={cn(
          'flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-medium',
          isDone ? 'bg-primary/15 text-primary' : 'bg-muted text-muted-foreground',
        )}>
          {isDone ? '✓' : '…'}
        </span>
        <span className="font-medium text-foreground">{toolName}</span>
        {args && Object.keys(args).length > 0 && (
          <span className="text-muted-foreground truncate max-w-[250px]">{JSON.stringify(args)}</span>
        )}
      </div>
      {isDone && (
        <pre className="px-3 py-2 text-xs overflow-x-auto whitespace-pre-wrap text-muted-foreground border-t border-border/50 bg-muted/10 max-h-40 overflow-y-auto">
          {typeof result === 'string' ? result : JSON.stringify(result, null, 2)}
        </pre>
      )}
    </div>
  )
}

function Composer() {
  return (
    <ComposerPrimitive.Root className="px-3 py-3 sm:px-6 sm:py-4 border-t bg-card/80 backdrop-blur-sm flex gap-2 items-end">
      <ComposerPrimitive.Input
        placeholder="Message..."
        autoFocus
        className={cn(
          'flex-1 rounded-xl border border-input bg-background px-4 py-3 text-sm min-h-[3.5rem] resize-none',
          'placeholder:text-muted-foreground',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          'disabled:cursor-not-allowed disabled:opacity-50',
        )}
      />
      <ComposerPrimitive.Send asChild>
        <Button size="icon" className="rounded-full shrink-0">
          <ArrowUp className="h-4 w-4" />
        </Button>
      </ComposerPrimitive.Send>
    </ComposerPrimitive.Root>
  )
}

function TypingIndicator() {
  const runtime = useThreadRuntime()
  const activity = useContext(ActivityContext)
  const [isRunning, setIsRunning] = useState(false)

  useEffect(() => {
    const update = () => {
      setIsRunning(runtime.getState().isRunning)
    }
    update()
    return runtime.subscribe(update)
  }, [runtime])

  if (!isRunning) return null

  const activityText = activity
    ? activity.type === 'tool'
      ? `calling ${activity.text}...`
      : activity.type === 'progress'
        ? activity.text
        : activity.text
    : 'thinking...'

  const agentName = activity?.agentName

  return (
    <div className="flex flex-col max-w-[85%] sm:max-w-[70%] self-start items-start">
      <div className="flex items-center gap-1 text-xs text-muted-foreground mb-0.5 pl-3">
        <Cpu className="h-3 w-3" />
        {agentName || 'agent'}
      </div>
      <div className="px-4 py-2.5 rounded-2xl rounded-bl-sm bg-card border border-border flex items-center gap-2">
        {/* Pulse ring */}
        <span className="relative flex h-2 w-2 shrink-0">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
        </span>
        <span className="text-xs text-muted-foreground">
          {activityText}
        </span>
      </div>
    </div>
  )
}

function ThreadScrollToBottom() {
  return (
    <ThreadPrimitive.ScrollToBottom asChild>
      <Button
        variant="outline"
        size="icon"
        className="absolute bottom-14 right-3 sm:bottom-16 sm:right-6 rounded-full shadow-md z-10"
      >
        <ArrowDown className="h-4 w-4" />
      </Button>
    </ThreadPrimitive.ScrollToBottom>
  )
}
