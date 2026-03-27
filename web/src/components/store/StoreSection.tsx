import { useCallback, useEffect, useState } from 'react'
import { fetchJSON, type StoreNamespace, type StoreKey, type StoreValue } from '../../api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  ChevronDown,
  ChevronRight,
  Database,
  Trash2,
  ChevronLeft,
  Copy,
  Check,
} from 'lucide-react'

export default function StoreSection() {
  const [expanded, setExpanded] = useState(false)
  const [namespaces, setNamespaces] = useState<StoreNamespace[]>([])
  const [selectedNs, setSelectedNs] = useState<string | null>(null)
  const [keys, setKeys] = useState<StoreKey[]>([])
  const [selectedKey, setSelectedKey] = useState<{ ns: string; key: string } | null>(null)
  const [valueData, setValueData] = useState<unknown>(null)
  const [copied, setCopied] = useState(false)

  const loadNamespaces = useCallback(() => {
    fetchJSON<StoreNamespace[]>('/store').then(setNamespaces).catch(() => {})
  }, [])

  useEffect(() => {
    if (expanded) loadNamespaces()
  }, [expanded, loadNamespaces])

  function openNamespace(ns: string) {
    setSelectedNs(ns)
    setSelectedKey(null)
    setValueData(null)
    fetchJSON<StoreKey[]>(`/store/${encodeURIComponent(ns)}`).then(setKeys).catch(() => {})
  }

  function openKey(ns: string, key: string) {
    setSelectedKey({ ns, key })
    fetchJSON<StoreValue>(`/store/${encodeURIComponent(ns)}/${encodeURIComponent(key)}`)
      .then(v => setValueData(v.data))
      .catch(() => setValueData(null))
  }

  async function deleteKey(ns: string, key: string) {
    await fetchJSON(`/store/${encodeURIComponent(ns)}/${encodeURIComponent(key)}`, { method: 'DELETE' })
    // If we were viewing this key, go back to key list
    if (selectedKey?.ns === ns && selectedKey?.key === key) {
      setSelectedKey(null)
      setValueData(null)
    }
    // Refresh keys
    const updated = await fetchJSON<StoreKey[]>(`/store/${encodeURIComponent(ns)}`)
    setKeys(updated)
    // If namespace is now empty, go back to namespace list
    if (updated.length === 0) {
      setSelectedNs(null)
      loadNamespaces()
    }
  }

  function goBack() {
    if (selectedKey) {
      setSelectedKey(null)
      setValueData(null)
    } else if (selectedNs) {
      setSelectedNs(null)
      loadNamespaces()
    }
  }

  function copyValue() {
    navigator.clipboard.writeText(JSON.stringify(valueData, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const totalKeys = namespaces.reduce((sum, ns) => sum + ns.key_count, 0)

  return (
    <div className="flex flex-col">
      <button
        className="px-3 py-2 flex items-center gap-1.5 hover:bg-sidebar-accent/50 transition-colors"
        onClick={() => setExpanded(e => !e)}
      >
        {expanded
          ? <ChevronDown className="h-3 w-3 text-muted-foreground" />
          : <ChevronRight className="h-3 w-3 text-muted-foreground" />
        }
        <Database className="h-3 w-3 text-muted-foreground" />
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">store</span>
        {totalKeys > 0 && (
          <Badge variant="secondary" className="ml-auto h-4 px-1.5 text-[10px] font-medium">
            {totalKeys}
          </Badge>
        )}
      </button>

      {expanded && (
        <ScrollArea className="max-h-72">
          {/* Value detail view */}
          {selectedKey ? (
            <div className="flex flex-col">
              <button
                className="px-3 py-1.5 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                onClick={goBack}
              >
                <ChevronLeft className="h-3 w-3" />
                {selectedKey.ns} / {selectedKey.key}
              </button>
              <div className="px-3 pb-2 flex items-center justify-between">
                <span className="text-xs font-medium truncate">{selectedKey.key}</span>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={copyValue}>
                    {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-destructive hover:text-destructive"
                    onClick={() => deleteKey(selectedKey.ns, selectedKey.key)}
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              </div>
              <pre className="px-3 pb-2 text-[11px] text-muted-foreground whitespace-pre-wrap break-all font-mono leading-relaxed">
                {JSON.stringify(valueData, null, 2)}
              </pre>
            </div>
          ) : selectedNs ? (
            /* Key list view */
            <div className="flex flex-col">
              <button
                className="px-3 py-1.5 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                onClick={goBack}
              >
                <ChevronLeft className="h-3 w-3" />
                {selectedNs}
              </button>
              <div className="flex flex-col gap-0.5 px-1.5 pb-2">
                {keys.map(k => (
                  <div
                    key={k.key}
                    className="flex items-center group"
                  >
                    <button
                      className="flex-1 text-left px-2 py-1.5 rounded-md text-xs text-sidebar-foreground hover:bg-sidebar-accent/50 transition-colors truncate"
                      onClick={() => openKey(selectedNs, k.key)}
                    >
                      {k.key}
                    </button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity text-destructive hover:text-destructive shrink-0"
                      onClick={() => deleteKey(selectedNs, k.key)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
                {keys.length === 0 && (
                  <p className="text-xs text-muted-foreground px-2 py-1.5">empty namespace</p>
                )}
              </div>
            </div>
          ) : (
            /* Namespace list view */
            <div className="flex flex-col gap-0.5 px-1.5 pb-2">
              {namespaces.map(ns => (
                <button
                  key={ns.namespace}
                  className="w-full text-left px-2 py-1.5 rounded-md text-xs text-sidebar-foreground hover:bg-sidebar-accent/50 transition-colors flex items-center justify-between"
                  onClick={() => openNamespace(ns.namespace)}
                >
                  <span className="truncate">{ns.namespace}</span>
                  <Badge variant="secondary" className="h-4 px-1.5 text-[10px] shrink-0">
                    {ns.key_count}
                  </Badge>
                </button>
              ))}
              {namespaces.length === 0 && (
                <p className="text-xs text-muted-foreground px-2 py-1.5">no store data</p>
              )}
            </div>
          )}
        </ScrollArea>
      )}
    </div>
  )
}
