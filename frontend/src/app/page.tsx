'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useToast } from '@/hooks/use-toast'
import { connectionsApi, authApi } from '@/lib/api'
import { useAuthStore } from '@/lib/auth'
import { cn, formatDateTime } from '@/lib/utils'
import { Database, Plus, LogOut, RefreshCw, Loader2, AlertCircle, CheckCircle2, Clock, Zap } from 'lucide-react'
import { ThemeToggle } from '@/components/theme-toggle'

type ConnectionStatus = 'pending' | 'analyzing' | 'indexing' | 'ready' | 'error' | 'updating'

interface Connection {
    id: number
    name: string
    description: string | null
    database: string
    status: ConnectionStatus
    analysis_progress: number
    last_analyzed_at: string | null
    is_owner: boolean
    can_edit: boolean
}

const statusConfig: Record<ConnectionStatus, { icon: React.ElementType; color: string; label: string }> = {
    pending: { icon: Clock, color: 'text-yellow-500', label: 'Pending' },
    analyzing: { icon: RefreshCw, color: 'text-blue-500', label: 'Analyzing' },
    indexing: { icon: Zap, color: 'text-emerald-500', label: 'Indexing' },
    ready: { icon: CheckCircle2, color: 'text-emerald-500', label: 'Ready' },
    error: { icon: AlertCircle, color: 'text-red-500', label: 'Error' },
    updating: { icon: RefreshCw, color: 'text-blue-500', label: 'Updating' },
}

export default function HomePage() {
    const router = useRouter()
    const { toast } = useToast()
    const queryClient = useQueryClient()
    const { isAuthenticated, user, logout, setUser } = useAuthStore()
    const [addDialogOpen, setAddDialogOpen] = useState(false)
    const [loading, setLoading] = useState(false)
    const [formData, setFormData] = useState({
        name: '',
        description: '',
        host: '',
        port: '5432',
        database: '',
        username: '',
        password: '',
    })

    // Check auth and fetch user
    useEffect(() => {
        const checkAuth = async () => {
            if (!isAuthenticated) {
                router.push('/login')
                return
            }
            try {
                const response = await authApi.me()
                setUser(response.data)
            } catch {
                logout()
                router.push('/login')
            }
        }
        checkAuth()
    }, [isAuthenticated, router, logout, setUser])

    // Fetch connections
    const { data: connections, isLoading } = useQuery<Connection[]>({
        queryKey: ['connections'],
        queryFn: async () => {
            const response = await connectionsApi.list()
            return response.data
        },
        enabled: isAuthenticated,
        refetchInterval: 5000, // Poll for status updates
    })

    // Add connection mutation
    const addMutation = useMutation({
        mutationFn: (data: typeof formData) =>
            connectionsApi.create({
                ...data,
                port: parseInt(data.port),
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['connections'] })
            setAddDialogOpen(false)
            setFormData({
                name: '', description: '', host: '', port: '5432',
                database: '', username: '', password: '',
            })
            toast({
                title: 'Database added!',
                description: 'Analysis will begin shortly.',
            })
        },
        onError: (error: any) => {
            toast({
                title: 'Failed to add database',
                description: error.response?.data?.detail || 'Please check your connection details.',
                variant: 'destructive',
            })
        },
    })

    const handleAddSubmit = async (e: React.FormEvent) => {
        e.preventDefault()
        addMutation.mutate(formData)
    }

    const handleLogout = () => {
        logout()
        router.push('/login')
    }

    if (!isAuthenticated || !user) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-background">
            {/* Header */}
            <header className="border-b bg-card">
                <div className="container mx-auto px-4 py-4 flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                        <div className="h-10 w-10 rounded-xl bg-primary/10 flex items-center justify-center">
                            <Database className="h-5 w-5 text-primary" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold">SQL Index</h1>
                            <p className="text-sm text-muted-foreground">Database RAG Platform</p>
                        </div>
                    </div>
                    <div className="flex items-center space-x-4">
                        <span className="text-sm text-muted-foreground">
                            Welcome, <span className="text-foreground font-medium">{user.username}</span>
                        </span>
                        <ThemeToggle />
                        <Button variant="ghost" size="sm" onClick={handleLogout}>
                            <LogOut className="h-4 w-4 mr-2" />
                            Logout
                        </Button>
                    </div>
                </div>
            </header>

            {/* Main Content */}
            <main className="container mx-auto px-4 py-8">
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h2 className="text-2xl font-bold">Your Databases</h2>
                        <p className="text-muted-foreground">Connect and analyze PostgreSQL databases</p>
                    </div>
                    <Dialog open={addDialogOpen} onOpenChange={setAddDialogOpen}>
                        <DialogTrigger asChild>
                            <Button>
                                <Plus className="h-4 w-4 mr-2" />
                                Add Database
                            </Button>
                        </DialogTrigger>
                        <DialogContent className="sm:max-w-[500px]">
                            <form onSubmit={handleAddSubmit}>
                                <DialogHeader>
                                    <DialogTitle>Add Database Connection</DialogTitle>
                                    <DialogDescription>
                                        Enter your PostgreSQL connection details
                                    </DialogDescription>
                                </DialogHeader>
                                <div className="grid gap-4 py-4">
                                    <div className="grid gap-2">
                                        <Label htmlFor="name">Connection Name</Label>
                                        <Input
                                            id="name"
                                            placeholder="My Database"
                                            value={formData.name}
                                            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                            required
                                        />
                                    </div>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="grid gap-2">
                                            <Label htmlFor="host">Host</Label>
                                            <Input
                                                id="host"
                                                placeholder="localhost"
                                                value={formData.host}
                                                onChange={(e) => setFormData({ ...formData, host: e.target.value })}
                                                required
                                            />
                                        </div>
                                        <div className="grid gap-2">
                                            <Label htmlFor="port">Port</Label>
                                            <Input
                                                id="port"
                                                type="number"
                                                placeholder="5432"
                                                value={formData.port}
                                                onChange={(e) => setFormData({ ...formData, port: e.target.value })}
                                                required
                                            />
                                        </div>
                                    </div>
                                    <div className="grid gap-2">
                                        <Label htmlFor="database">Database</Label>
                                        <Input
                                            id="database"
                                            placeholder="mydb"
                                            value={formData.database}
                                            onChange={(e) => setFormData({ ...formData, database: e.target.value })}
                                            required
                                        />
                                    </div>
                                    <div className="grid grid-cols-2 gap-4">
                                        <div className="grid gap-2">
                                            <Label htmlFor="username">Username</Label>
                                            <Input
                                                id="username"
                                                placeholder="postgres"
                                                value={formData.username}
                                                onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                                                required
                                            />
                                        </div>
                                        <div className="grid gap-2">
                                            <Label htmlFor="password">Password</Label>
                                            <Input
                                                id="password"
                                                type="password"
                                                placeholder="••••••••"
                                                value={formData.password}
                                                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                                                required
                                            />
                                        </div>
                                    </div>
                                </div>
                                <DialogFooter>
                                    <Button type="button" variant="outline" onClick={() => setAddDialogOpen(false)}>
                                        Cancel
                                    </Button>
                                    <Button type="submit" disabled={addMutation.isPending}>
                                        {addMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                                        Add Database
                                    </Button>
                                </DialogFooter>
                            </form>
                        </DialogContent>
                    </Dialog>
                </div>

                {/* Connections Grid */}
                {isLoading ? (
                    <div className="flex items-center justify-center py-12">
                        <Loader2 className="h-8 w-8 animate-spin text-primary" />
                    </div>
                ) : connections?.length === 0 ? (
                    <Card className="border-dashed">
                        <CardContent className="flex flex-col items-center justify-center py-12">
                            <Database className="h-12 w-12 text-muted-foreground mb-4" />
                            <h3 className="text-lg font-medium mb-2">No databases connected</h3>
                            <p className="text-muted-foreground mb-4">
                                Add your first PostgreSQL database to get started
                            </p>
                            <Button onClick={() => setAddDialogOpen(true)}>
                                <Plus className="h-4 w-4 mr-2" />
                                Add Database
                            </Button>
                        </CardContent>
                    </Card>
                ) : (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {connections?.map((conn) => {
                            const status = statusConfig[conn.status]
                            const StatusIcon = status.icon
                            const isProcessing = ['analyzing', 'indexing', 'updating'].includes(conn.status)

                            return (
                                <Card
                                    key={conn.id}
                                    className="cursor-pointer hover:border-primary/50 transition-colors"
                                    onClick={() => router.push(`/databases/${conn.id}`)}
                                >
                                    <CardHeader className="pb-3">
                                        <div className="flex items-start justify-between">
                                            <div>
                                                <CardTitle className="text-lg">{conn.name}</CardTitle>
                                                <CardDescription className="text-sm">
                                                    {conn.database}
                                                </CardDescription>
                                            </div>
                                            <div className={cn('flex items-center space-x-1 text-sm', status.color)}>
                                                <StatusIcon className={cn('h-4 w-4', isProcessing && 'animate-spin')} />
                                                <span>{status.label}</span>
                                            </div>
                                        </div>
                                    </CardHeader>
                                    <CardContent>
                                        {isProcessing && (
                                            <div className="mb-3">
                                                <div className="h-2 bg-muted rounded-full overflow-hidden">
                                                    <div
                                                        className="h-full bg-primary transition-all"
                                                        style={{ width: `${conn.analysis_progress}%` }}
                                                    />
                                                </div>
                                                <p className="text-xs text-muted-foreground mt-1">
                                                    {Math.round(conn.analysis_progress)}% complete
                                                </p>
                                            </div>
                                        )}
                                        <div className="flex items-center justify-between text-sm text-muted-foreground">
                                            <span>{conn.is_owner ? 'Owner' : 'Shared'}</span>
                                            {conn.last_analyzed_at && (
                                                <span>Analyzed {formatDateTime(conn.last_analyzed_at)}</span>
                                            )}
                                        </div>
                                    </CardContent>
                                </Card>
                            )
                        })}
                    </div>
                )}
            </main>
        </div>
    )
}
