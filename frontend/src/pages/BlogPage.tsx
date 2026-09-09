import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, getErrorMessage } from '../services/api'
import {
  PlusIcon,
  MagnifyingGlassIcon,
  SparklesIcon,
  ClockIcon,
  TagIcon,
  UserIcon,
  ChartBarIcon,
  ExclamationTriangleIcon
} from '@heroicons/react/24/outline'
import { useAuth } from '../hooks/useAuth'

interface BlogPost {
  id: number
  title: string
  content: string
  author: string
  category: string
  is_published: boolean
  featured: boolean
  created_at: string
  updated_at?: string
  tags: string
  perspectives_count?: number
  consensus_score?: number
}

interface ContentTemplate {
  name: string
  description: string
  parameters: Record<string, { type: string; description: string; default?: string | number }>
}

export function BlogPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [blogPosts, setBlogPosts] = useState<BlogPost[]>([])
  const [templates, setTemplates] = useState<Record<string, ContentTemplate>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('all')
  const [generatingContent, setGeneratingContent] = useState<string | null>(null)

  useEffect(() => {
    loadBlogPosts()
    loadTemplates()
  }, [])

  const loadBlogPosts = async () => {
    try {
      setLoading(true)
      const response = await api.get('/content/blog-posts/?limit=20&published_only=false')
      setBlogPosts(response.data.blog_posts || [])
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load blog posts'))
    } finally {
      setLoading(false)
    }
  }

  const loadTemplates = async () => {
    try {
      const response = await api.get('/content/templates')
      setTemplates(response.data.templates || {})
    } catch (err) {
      console.error('Failed to load templates:', err)
    }
  }

  const generateContent = async (templateKey: string, templateName: string) => {
    if (!user) return
    
    try {
      setGeneratingContent(templateKey)
      setError('')
      
      // Use general generate-and-save endpoint for all content types for consistency
      const requestData = {
        content_type: templateKey,
        topic: `Generated ${templateName}`,
        parameters: getDefaultParameters(templateKey)
      }
      
      await api.post('/content/generate-and-save', requestData)
      
      // Reload blog posts to show new content
      await loadBlogPosts()
      
    } catch (err) {
      setError(getErrorMessage(err, `Failed to generate ${templateName}`))
    } finally {
      setGeneratingContent(null)
    }
  }

  const getDefaultParameters = (templateKey: string) => {
    switch (templateKey) {
      case 'weekly_rankings':
        return { week: 1, position: 'ALL' }
      case 'waiver_wire':
        return { week: 1 }
      case 'start_sit':
        return { week: 1, position: 'ALL' }
      case 'breakout_candidates':
        return { timeframe: 'weekly' }
      case 'draft_strategy':
        return { draft_type: 'redraft', league_size: 12 }
      case 'player_analysis':
        return { player_name: 'Sample Player Analysis' }
      case 'injury_report':
        return {}
      default:
        return {}
    }
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    const now = new Date()
    const diffTime = Math.abs(now.getTime() - date.getTime())
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24))
    
    if (diffDays === 1) return '1 day ago'
    if (diffDays < 7) return `${diffDays} days ago`
    return date.toLocaleDateString()
  }

  const getCategoryColor = (category: string) => {
    // Content categories are a decorative label, not a status signal -- so
    // this deliberately does NOT borrow the success/warning/danger ramp
    // (reserved for real status meaning per STYLE_GUIDE.md §1). Injury
    // reports are the one genuine exception: injury status is real
    // categorical status elsewhere in the app too.
    if (category === 'injury_report') return 'bg-danger-100 text-danger-800'
    return 'bg-surface-2 text-body'
  }

  const getCategoryName = (category: string) => {
    const names: Record<string, string> = {
      waiver_wire: 'Waiver Wire',
      weekly_rankings: 'Rankings',
      player_analysis: 'Player Analysis',
      injury_report: 'Injury Report',
      start_sit: 'Start/Sit',
      breakout_candidates: 'Breakouts',
      draft_strategy: 'Draft Strategy'
    }
    return names[category] || category.replace('_', ' ')
  }

  const filteredPosts = blogPosts.filter(post => {
    const matchesSearch = post.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         post.content.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesCategory = selectedCategory === 'all' || post.category === selectedCategory
    return matchesSearch && matchesCategory
  })

  const categories = ['all', ...Array.from(new Set(blogPosts.map(post => post.category)))]

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-display font-bold uppercase tracking-tight text-3xl text-body">Analysis &amp; Rankings</h1>
          <p className="text-muted mt-2">
            Player deep-dives and injury reports are AI-written. Rankings and waiver targets are
            computed from live usage data. Every piece is dated.
          </p>
        </div>

        {user && (
          <div className="flex items-center space-x-2">
            <SparklesIcon className="h-5 w-5 text-accent-ink" />
            <span className="text-sm text-muted">Generation on</span>
          </div>
        )}
      </div>

      {/* Error Display */}
      {error && (
        <div className="bg-danger-50 border border-danger-100 rounded-md p-4">
          <div className="flex">
            <ExclamationTriangleIcon className="h-5 w-5 text-danger-500" />
            <div className="ml-3">
              <h3 className="text-sm font-medium text-danger-800">Error</h3>
              <div className="mt-2 text-sm text-danger-700">{error}</div>
            </div>
          </div>
        </div>
      )}

      {/* Filters and Search */}
      <div className="flex flex-col sm:flex-row space-y-4 sm:space-y-0 sm:space-x-4">
        <select
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
          className="rounded-md border-line focus:border-accent-ink focus:ring-volt"
        >
          {categories.map(category => (
            <option key={category} value={category}>
              {category === 'all' ? 'All Categories' : getCategoryName(category)}
            </option>
          ))}
        </select>

        <div className="relative flex-1">
          <MagnifyingGlassIcon className="absolute left-3 top-3 h-4 w-4 text-faint" />
          <input
            type="text"
            placeholder="Search articles..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-line rounded-md focus:border-accent-ink focus:ring-volt"
          />
        </div>
      </div>

      {/* Content Generation Templates */}
      {user && Object.keys(templates).length > 0 && (
        <div className="bg-highlight rounded-lg p-4 sm:p-6">
          <div className="flex items-center mb-4">
            <SparklesIcon className="h-6 w-6 text-accent-ink mr-2" />
            <h2 className="font-display text-lg font-bold uppercase tracking-tight text-body">Generate a piece</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(templates).map(([key, template]) => (
              <button
                key={key}
                onClick={() => generateContent(key, template.name)}
                disabled={generatingContent === key}
                className="text-left p-4 bg-surface rounded-lg border border-hairline hover:border-accent-ink transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-medium text-body">{template.name}</h3>
                  {generatingContent === key ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-accent-ink"></div>
                  ) : (
                    <PlusIcon className="h-4 w-4 text-faint" />
                  )}
                </div>
                <p className="text-sm text-muted">{template.description}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Blog Posts */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-ink"></div>
          <span className="ml-2 text-muted">Loading articles...</span>
        </div>
      ) : filteredPosts.length === 0 ? (
        <div className="text-center py-12">
          <ChartBarIcon className="mx-auto h-12 w-12 text-faint" />
          <h3 className="mt-2 text-sm font-medium text-body">Nothing here yet</h3>
          <p className="mt-1 text-sm text-muted">
            {searchQuery || selectedCategory !== 'all'
              ? 'No pieces match those filters.'
              : 'Generate one above to get started.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {filteredPosts.map((post) => (
            <article key={post.id} className="bg-surface rounded-lg border border-hairline p-6 hover:border-accent-ink transition-all">
              <div className="flex items-center justify-between mb-3">
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getCategoryColor(post.category)}`}>
                  <TagIcon className="h-3 w-3 mr-1" />
                  {getCategoryName(post.category)}
                </span>
                <div className="flex items-center text-sm text-muted">
                  <ClockIcon className="h-4 w-4 mr-1" />
                  {formatDate(post.created_at)}
                </div>
              </div>

              <h2 className="text-xl font-semibold mb-3 text-body line-clamp-2">
                {post.title}
              </h2>

              <p className="text-muted mb-4 line-clamp-3">
                {post.content.replace(/#{1,6}\s/g, '').substring(0, 150)}...
              </p>

              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-4 text-xs text-muted">
                  <div className="flex items-center">
                    <UserIcon className="h-3 w-3 mr-1" />
                    {post.author}
                  </div>
                  {post.perspectives_count && (
                    <div className="flex items-center">
                      <span>Perspectives: {post.perspectives_count}</span>
                    </div>
                  )}
                  {post.consensus_score && (
                    <div className="flex items-center">
                      <span className="font-stat tabular-nums text-body font-medium">
                        Score: {post.consensus_score.toFixed(1)}/10
                      </span>
                    </div>
                  )}
                </div>

                <button
                  onClick={() => navigate(`/blog/${post.id}`)}
                  className="text-accent-ink hover:text-accent-ink text-sm font-medium transition-colors"
                >
                  Read More →
                </button>
              </div>

              {post.featured && (
                <div className="mt-3 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-highlight text-accent-ink">
                  Featured
                </div>
              )}
            </article>
          ))}
        </div>
      )}

      {/* Insights Sidebar */}
      <div className="bg-surface rounded-lg border border-hairline p-4 sm:p-6">
        <div className="flex items-center mb-4">
          <SparklesIcon className="h-6 w-6 text-accent-ink mr-2" />
          <h2 className="text-xl font-semibold text-body">Quick Hits</h2>
        </div>
        <div className="space-y-4">
          <div className="border-l-4 border-success-500 pl-4">
            <p className="text-sm text-muted">
              <strong className="text-success-700">Trending Up:</strong> Rookie WRs showing increased target share in recent weeks
            </p>
          </div>
          <div className="border-l-4 border-warning-500 pl-4">
            <p className="text-sm text-muted">
              <strong className="text-warning-700">Injury Alert:</strong> Monitor RB depth chart changes after practice reports
            </p>
          </div>
          <div className="border-l-4 border-accent-ink pl-4">
            <p className="text-sm text-muted">
              <strong className="text-accent-ink">Value Pick:</strong> Streaming defenses against high-turnover offenses
            </p>
          </div>
          <div className="border-l-4 border-ink-400 pl-4">
            <p className="text-sm text-muted">
              <strong className="text-body">Data Insight:</strong> Historical performance suggests key breakout candidates
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}