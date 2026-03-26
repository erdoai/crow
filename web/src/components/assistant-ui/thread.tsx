import { useState, useEffect } from 'react'
import {
  ThreadPrimitive,
  ComposerPrimitive,
  MessagePrimitive,
  useMessage,
  useThreadRuntime,
} from '@assistant-ui/react'
import { MarkdownTextPrimitive } from '@assistant-ui/react-markdown'
import { ArrowUp, ArrowDown, Cpu } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export function Thread() {
  return (
    <ThreadPrimitive.Root className="flex flex-col h-full relative">
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto px-6 py-4">
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
      <p>send a message to get started</p>
    </div>
  )
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="flex flex-col max-w-[70%] self-end items-end">
      <div className="px-4 py-2.5 rounded-2xl rounded-br-sm text-sm leading-relaxed bg-primary text-primary-foreground">
        <MessagePrimitive.Content
          components={{ Text: ({ text }) => <>{text}</> }}
        />
      </div>
    </MessagePrimitive.Root>
  )
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="flex flex-col max-w-[70%] self-start items-start">
      <AgentLabel />
      <div className="px-4 py-2.5 rounded-2xl rounded-bl-sm text-sm leading-relaxed bg-card border border-border prose prose-sm prose-neutral dark:prose-invert max-w-none">
        <MessagePrimitive.Content
          components={{
            Text: AssistantMessageText,
            tools: { Fallback: ToolCallDisplay },
          }}
        />
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
  return (
    <details className="my-1.5 rounded-lg border border-border bg-muted/30 text-xs">
      <summary className="px-3 py-1.5 cursor-pointer text-muted-foreground flex items-center gap-1.5">
        <span>{result !== undefined ? '✓' : '⏳'}</span>
        <span className="font-medium">{toolName}</span>
        {args && Object.keys(args).length > 0 && (
          <span className="opacity-50 truncate max-w-[200px]">{JSON.stringify(args)}</span>
        )}
      </summary>
      {result !== undefined && (
        <pre className="px-3 py-2 overflow-x-auto whitespace-pre-wrap text-muted-foreground border-t border-border">
          {typeof result === 'string' ? result : JSON.stringify(result, null, 2)}
        </pre>
      )}
    </details>
  )
}

function Composer() {
  return (
    <ComposerPrimitive.Root className="px-6 py-3 border-t bg-card flex gap-2 items-end">
      <ComposerPrimitive.Input
        placeholder="Message..."
        autoFocus
        className={cn(
          'flex-1 rounded-full border border-input bg-background px-4 py-2 text-sm',
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
  const [isRunning, setIsRunning] = useState(false)

  useEffect(() => {
    const update = () => {
      const state = runtime.getState()
      const msgs = state.messages
      const lastIsUser = msgs.length > 0 && msgs[msgs.length - 1].role === 'user'
      setIsRunning(state.isRunning || lastIsUser)
    }
    update()
    return runtime.subscribe(update)
  }, [runtime])

  if (!isRunning) return null

  return (
    <div className="flex flex-col max-w-[70%] self-start items-start">
      <div className="flex items-center gap-1 text-xs text-muted-foreground mb-0.5 pl-3">
        <Cpu className="h-3 w-3" />
        thinking...
      </div>
      <div className="px-4 py-3 rounded-2xl rounded-bl-sm bg-card border border-border">
        <div className="flex gap-1">
          <span className="w-2 h-2 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:0ms]" />
          <span className="w-2 h-2 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:150ms]" />
          <span className="w-2 h-2 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:300ms]" />
        </div>
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
        className="absolute bottom-16 right-6 rounded-full shadow-md z-10"
      >
        <ArrowDown className="h-4 w-4" />
      </Button>
    </ThreadPrimitive.ScrollToBottom>
  )
}
