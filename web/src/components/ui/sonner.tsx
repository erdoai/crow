import { Toaster as SonnerToaster } from 'sonner'

export function Toaster() {
  return (
    <SonnerToaster
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast: 'bg-card border-border text-foreground',
          title: 'text-foreground',
          description: 'text-muted-foreground',
          success: 'border-green-500/30',
          error: 'border-destructive/30',
        },
      }}
    />
  )
}
